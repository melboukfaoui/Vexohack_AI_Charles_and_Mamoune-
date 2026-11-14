"""The band's ears: band microphone -> Deepgram -> each finished sentence -> the backend.

    python3 bridge.py <your band number>      your band over Bluetooth (double-tap it first)
    python3 bridge.py <number> --usb          the USB cable
    python3 bridge.py --sim                   pretend band: plays the kit's sample recording
    python3 bridge.py --say "okay, locking up"    typed words, no band and no Deepgram key

A tap on the band answers the latest nudge, so it stops escalating to the family.
It runs until Ctrl+C: a dropped link comes back by itself, a closed Deepgram connection is
opened again, and a band out of range is looked for until it is double-tapped again.

Needs: python3 -m pip install bleak   (Bluetooth), and DEEPGRAM_API_KEY in .env or the
environment. Start the backend first: uvicorn main:app --app-dir Backend --port 8000
Everything the microphone hears is sent to Deepgram: tell the people near the band.
"""
import json
import os
import queue
import signal
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vexo-open-kit" / "examples" / "python"))
import kit      # finds the library and reads the command line  # noqa: E402
import speech   # sound -> Deepgram                               # noqa: E402
from vexo_open.sync import Band, VexoError  # noqa: E402

import argparse  # noqa: E402

p = argparse.ArgumentParser(description="Band microphone -> Deepgram -> Memory Band backend")
p.add_argument("number", nargs="?", type=kit.band_number, help="the number on your band's bag")
p.add_argument("--sim", dest="transport", action="store_const", const="sim", default="ble", help="pretend band")
p.add_argument("--usb", dest="transport", action="store_const", const="serial", help="USB cable, not Bluetooth")
p.add_argument("--seconds", type=float, default=None, help="stop after this long (default: until Ctrl+C)")
p.add_argument("--say", help='typed words instead of the microphone, e.g. --say "okay, locking up"')
p.add_argument("--server", default="http://127.0.0.1:8000", help="where the Memory Band backend runs")
opts = p.parse_args()
if opts.number is None and opts.transport == "ble" and not opts.say:
    p.error("add your band number (on the bag), or --sim, or --say \"some words\"")
SERVER = opts.server.rstrip("/")

outbox = queue.Queue()


def post(path, body):
    req = urllib.request.Request(SERVER + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as answer:
        return json.loads(answer.read().decode("utf-8"))


def sender():
    """Posts in its own thread, so a slow backend never holds up the sound."""
    while True:
        path, body = outbox.get()
        try:
            got = post(path, body)
            for e in got.get("events", []):
                print("   event:", e["type"], e.get("item") or "")
            if got.get("answer"):
                print("   answer:", got["answer"]["text"])
        except Exception as error:
            print("   backend not reached (%s). Is uvicorn running at %s?" % (error, SERVER))
        finally:
            outbox.task_done()


threading.Thread(target=sender, daemon=True).start()


sys.path.insert(0, str(Path(__file__).resolve().parent / "Backend"))
import detector  # noqa: E402  (the backend's own patterns: the same words trigger here)

early = {"sent": None}      # the sentence already sent early, while it was still being spoken


def heard(text, final):
    """Deepgram calls this with a guess while someone speaks (final=False) and the settled
    sentence after a pause (final=True). A guess that already holds a trigger ("get the
    check", "taking my pill") is sent at once, so the reminder does not wait for the pause."""
    text = text.strip()
    if not text:
        return
    if not final:
        if early["sent"] is None and detector.keywords(text) and not detector.is_question(text):
            early["sent"] = text
            print("heard (early):", kit.plain(text), flush=True)
            outbox.put(("/transcripts", {"text": text, "source": "band"}))
        return
    sent, early["sent"] = early["sent"], None
    if sent is not None:
        before = {e[:2] for e in detector.keywords(sent)}
        if not ({e[:2] for e in detector.keywords(text)} - before):
            return                              # the full sentence adds nothing to what was sent early
    print("heard:", kit.plain(text), flush=True)
    outbox.put(("/transcripts", {"text": text, "source": "band"}))


if opts.say:                                    # typed words: no band needed
    heard(opts.say, True)
    outbox.join()
    sys.exit(0)

if opts.transport == "sim" and opts.seconds is None:
    opts.seconds = 60                           # kit.voice() cuts this to the length of the sample recording

live = {"band": None, "ears": None, "gone": threading.Event()}
stopping = threading.Event()


def on_ctrl_c(signum, frame):
    # The band library ends band.wait() quietly on Ctrl+C, so remember it here too.
    stopping.set()
    raise KeyboardInterrupt


signal.signal(signal.SIGINT, on_ctrl_c)


def feed(a):
    """Sound to whichever Deepgram connection is open right now."""
    ears = live["ears"]
    if ears is not None:
        try:
            ears.feed(a)
        except Exception:
            pass                                # it closed: the loop below opens a new one


def open_ears():
    """A Deepgram connection. If the network is down, keep trying every 5 seconds."""
    while not stopping.is_set():
        try:
            live["ears"] = speech.create(keyterm="pill").start(heard)   # helps it hear "pill", not "appeal"
            return
        except Exception as error:
            print("Deepgram not reachable (%s). Trying again in 5 s." % error, flush=True)
            stopping.wait(5)


def connect():
    """Connects to the band, and keeps asking for a double-tap until it is found."""
    while not stopping.is_set():
        try:
            band = Band.connect(opts.number, transport=opts.transport, auto_reconnect=opts.transport != "sim",
                                reconnect_seconds=120, **kit.voice(opts))
        except VexoError as error:
            print("Band not found (%s). Double-tap the band; trying again in 5 s." % error.code, flush=True)
            stopping.wait(5)
            continue
        live["gone"].clear()
        band.on("tap", lambda e: outbox.put(("/ack", {})))
        band.on("reconnecting", lambda e: print("Link lost. Getting it back (up to %d s, no tap needed)..." % e.seconds, flush=True))
        band.on("reconnected", lambda e: print("Link back after %.0f s. Listening again." % e.seconds, flush=True))
        band.on("disconnect", lambda e: live["gone"].set())
        band.on("battery", lambda e: e.percent is not None and e.percent <= 20 and not e.charging and
                print("Battery low: %d%%. Plug the band in soon." % e.percent, flush=True))
        band.on("audio", feed)
        band.configure(audio=True, events=True, battery=True)   # the light goes solid blue: the microphone is on
        live["band"] = band
        print("Connected to", kit.plain(band.name), "- listening. Tap the band to answer a nudge. Ctrl+C to stop.",
              flush=True)
        return band


try:
    open_ears()
    connect()
    left = (opts.seconds + 2) if opts.seconds else float("inf")
    while left > 0 and not stopping.is_set():   # short waits, so Ctrl+C stops it within a second
        band = live["band"]
        band.wait(min(1, left))
        left -= 1
        ears = live["ears"]
        if ears is not None and ears._done.is_set():          # Deepgram hung up: open a new connection
            print("Deepgram connection closed. Opening a new one...", flush=True)
            open_ears()
        if stopping.is_set():
            break
        if live["gone"].is_set():               # the band gave up reconnecting (out of range, switched off)
            if opts.transport == "sim":
                break
            print("Band disconnected. Bring it close and double-tap it.", flush=True)
            connect()
except KeyboardInterrupt:
    pass
finally:
    stopping.set()
    print("Stopping...", flush=True)

    def close():
        band, ears = live["band"], live["ears"]
        steps = []
        if band is not None:
            steps += [lambda: band.configure(audio=False), lambda: band.off("audio", feed)]
        if ears is not None:
            steps.append(lambda: ears.stop(wait=2))
        if band is not None:
            steps.append(band.disconnect)
        for step in steps:
            try:
                step()
            except BaseException:
                pass

    closer = threading.Thread(target=close, daemon=True)
    closer.start()
    closer.join(8)                              # never hang on the way out
    print("Stopped. The band's light turns off." if not closer.is_alive() else
          "Stopped (the band did not answer; restart it if the light stays blue).")
    sys.stdout.flush()
    os._exit(0)
