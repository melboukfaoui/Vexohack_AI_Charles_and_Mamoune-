"""The band's ears: band microphone -> Deepgram -> each finished sentence -> the backend.

    python3 bridge.py <your band number>      your band over Bluetooth (double-tap it first)
    python3 bridge.py <number> --usb          the USB cable
    python3 bridge.py --sim                   pretend band: plays the kit's sample recording
    python3 bridge.py --say "okay, locking up"    typed words, no band and no Deepgram key

A tap on the band answers the latest nudge, so it stops escalating to the family.

Needs: python3 -m pip install bleak   (Bluetooth), and DEEPGRAM_API_KEY in .env or the
environment. Start the backend first: uvicorn main:app --app-dir Backend --port 8000
Everything the microphone hears is sent to Deepgram: tell the people near the band.
"""
import json
import queue
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vexo-open-kit" / "examples" / "python"))
import kit      # finds the library and reads the command line  # noqa: E402
import speech   # sound -> Deepgram                               # noqa: E402
from vexo_open.sync import Band  # noqa: E402

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


def heard(text, final):
    if final and text.strip():
        print("heard:", kit.plain(text))
        outbox.put(("/transcripts", {"text": text.strip(), "source": "band"}))


if opts.say:                                    # typed words: no band needed
    heard(opts.say, True)
    outbox.join()
    sys.exit(0)

band = Band.connect(opts.number, transport=opts.transport, **kit.voice(opts))
print("Connected to", kit.plain(band.name), "- listening. Tap the band to answer a nudge. Ctrl+C to stop.")
band.on("tap", lambda e: outbox.put(("/ack", {})))

ears = speech.create().start(heard)
band.on("audio", ears.feed)
band.configure(audio=True, events=True)         # the light goes solid blue: the microphone is on
try:
    if opts.seconds:
        band.wait(opts.seconds + 2)
    else:
        while True:
            band.wait(1)
except KeyboardInterrupt:
    pass
finally:
    band.configure(audio=False)
    band.off("audio", ears.feed)
    ears.stop()
    outbox.join()
    band.disconnect()
