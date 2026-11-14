"""Memory Band backend.

    band mic --(Bluetooth)--> bridge.py --(Deepgram text)--> POST /transcripts
        -> detector (keywords, then OpenAI)  -> events timeline (SQLite)
        -> rules engine (instant + every 2 s) -> nudges -> live screen + ElevenLabs voice

Run from the project folder (so .env is found):
    uvicorn main:app --app-dir Backend --reload --port 8000
then open http://127.0.0.1:8000
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

import detector
import qa
import rules
import voice
from store import hub, now, store

STATIC = Path(__file__).resolve().parent / "static"


async def ticker():
    while True:
        try:
            await asyncio.to_thread(rules.tick)
        except Exception as error:      # one bad tick never stops the rules
            print("rules.tick failed:", repr(error))
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app):
    hub.loop = asyncio.get_running_loop()
    task = asyncio.create_task(ticker())
    print("Memory Band: AI detector %s, ElevenLabs voice %s" % (
        "on" if detector.ai_available() else "off (no OPENAI_API_KEY, keywords only)",
        "on" if voice.key() else "off (no ELEVENLABS_API_KEY, browser voice)"))
    yield
    task.cancel()


app = FastAPI(title="Memory Band", lifespan=lifespan)


# -- what the band heard ------------------------------------------------------------------------
class TranscriptInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="band", max_length=40)


def add_events(found, quote, transcript_id, how):
    rows = []
    for type_, item, place in found:
        event = store.add_event(type_, quote, transcript_id, item=item, place=place, detector=how)
        rows.append(event)
        rules.on_event(event)
    return rows


def process(text: str, source: str) -> dict:
    text = text.strip()
    heard = store.add_transcript(text, source)
    if detector.is_question(text):
        return {"transcript": heard, "events": [], "answer": qa.handle(text, heard["id"])}
    found = detector.detect(text, lambda later, how: add_events(later, text, heard["id"], how))
    return {"transcript": heard, "events": add_events(found, text, heard["id"], "keywords")}


@app.post("/transcripts")
def post_transcript(body: TranscriptInput):
    """One finished sentence from the band (bridge.py), or typed on the live screen."""
    return process(body.text, body.source)


# Kept from the first version, so older test calls still work.
@app.post("/memories")
def save_memory(body: TranscriptInput):
    return process(body.text, body.source)


@app.get("/memories")
def get_memories():
    return {"memories": store.rows("transcripts")}


# -- the live screen ------------------------------------------------------------------------------
@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"ok": True, "ai": detector.ai_available(), "voice": bool(voice.key())}


@app.get("/state")
def state():
    return {"transcripts": store.rows("transcripts"), "events": store.rows("events"),
            "nudges": store.rows("nudges"), "config": rules.CONFIG, "now": now().isoformat()}


@app.get("/stream")
async def stream(request: Request):
    """Server-Sent Events: every new transcript, event and nudge, as it happens."""
    q = asyncio.Queue()
    hub.queues.add(q)

    async def events():
        try:
            yield "event: hello\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    message = await asyncio.wait_for(q.get(), timeout=15)
                    yield "data: %s\n\n" % message
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            hub.queues.discard(q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/nudges/{nudge_id}/audio")
def nudge_audio(nudge_id: int):
    row = store.get_nudge(nudge_id)
    if not row:
        raise HTTPException(404, "No such nudge")
    audio = voice.speak(nudge_id, row["text"])
    if audio is None:
        raise HTTPException(404, "No ElevenLabs voice (no key or it failed): use the browser voice")
    return Response(audio, media_type="audio/mpeg")


class AckInput(BaseModel):
    nudge_id: Optional[int] = None


@app.post("/ack")
def ack(body: AckInput):
    """The wearer answered (a tap on the band, or a button): open nudges stop escalating."""
    store.resolve(nudge_id=body.nudge_id)
    return {"ok": True}


# -- demo controls ----------------------------------------------------------------------------------
class DemoInput(BaseModel):
    pill_in_min: float = 2          # the pill is due this many minutes from now
    escalate_after_min: float = 1   # family alerts this long after the wearer's nudge
    reset: bool = True


@app.post("/demo/start")
def demo_start(body: DemoInput):
    if body.reset:
        store.reset()
    due = now() + timedelta(minutes=body.pill_in_min)
    rules.CONFIG["pills"] = [{"name": "blood pressure pill", "due": due.isoformat(timespec="seconds")}]
    rules.CONFIG["pill_grace_min"] = 0
    rules.CONFIG["pill_escalate_min"] = body.escalate_after_min
    rules.CONFIG["no_reply_min"] = body.escalate_after_min
    hub.publish("config", rules.CONFIG)
    return {"pill_due": due.strftime("%H:%M"), "config": rules.CONFIG}


@app.post("/demo/reset")
def demo_reset():
    store.reset()
    return {"ok": True}


class ConfigInput(BaseModel):
    pills: Optional[list] = None
    pill_grace_min: Optional[float] = None
    pill_escalate_min: Optional[float] = None
    door_window_min: Optional[float] = None
    no_reply_min: Optional[float] = None
    stove_min: Optional[float] = None
    restaurant_items: Optional[list] = None


@app.put("/config")
def put_config(body: ConfigInput):
    rules.CONFIG.update({k: v for k, v in body.model_dump().items() if v is not None})
    hub.publish("config", rules.CONFIG)
    return rules.CONFIG
