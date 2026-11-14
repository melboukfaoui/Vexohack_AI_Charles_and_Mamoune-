# Memory Band

A memory helper for older adults, built on the Vexo Open band (VexoHacks, Nov 14 2026).
The band listens; we catch the moments that matter and speak up before something goes wrong.

```
band mic --Bluetooth--> bridge.py --Deepgram--> POST /transcripts
   -> detector (keywords, then OpenAI)  -> timeline (SQLite)
   -> rules (instant + every 2 s)       -> nudges -> live screen + ElevenLabs voice
```

| File | What it does |
|---|---|
| `bridge.py` | Band microphone → Deepgram → each finished sentence to the backend. A tap on the band answers the latest nudge. |
| `Backend/main.py` | FastAPI: `/transcripts`, `/state`, `/stream` (live events), `/nudges/{id}/audio`, `/ack`, `/demo/start`, `/config` |
| `Backend/detector.py` | Sentence → events (pill taken, door locked, leaving, check, items…) |
| `Backend/rules.py` | Double dose, missed pill, restaurant items, door, stove, family escalation. Pill times live in `CONFIG`. |
| `Backend/qa.py` | "Did I lock the door?", "Where are my glasses?", repeated-question alerts |
| `Backend/voice.py` | ElevenLabs text to speech |
| `Backend/static/index.html` | Live screen for the judges and the family view |

## Run it

```bash
git clone https://github.com/VexoAI-Org/vexo-open-kit.git   # once; it is in .gitignore
python3 -m pip install -r Backend/requirements.txt
cp env.example .env                                          # then paste the team's keys
python3 -m uvicorn main:app --app-dir Backend --port 8000    # from this folder
```

Open http://127.0.0.1:8000, then in a second terminal (double-tap the band first):

```bash
python3 bridge.py <band number from the bag>
```

No band, or no Deepgram key: type sentences on the live screen, or
`python3 bridge.py --say "okay, locking up"`. Keys that are missing just switch features
off: no OpenAI key means keywords only, no ElevenLabs key means the browser's voice.

## Demo (2 minutes)

Press **Start demo** on the live screen (clears the timeline, voice on, pill due in 2 min).

1. "can we get the check?" → *Before you go, do you have your phone, wallet and glasses?*
2. "I'm heading out to the store" → *You haven't locked the front door yet.* No answer for 1 min → family alert.
3. Wait for minute 2 → *You haven't taken your blood pressure pill yet.* One more minute → family alert.
4. "taking my blood pressure pill", then "time for my pill" → *Wait, you already took it at …*
5. "okay, locking up", then "did I lock the door?" → the time, plus what they said.

Say the pill line **after** the reminder in step 3, or the missed-pill rule has nothing to catch.
Only one program can hold the band: close the kit's dashboard before running `bridge.py`.
