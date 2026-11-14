"""ElevenLabs: turns each nudge into a calm voice clip (mp3).

Needs ELEVENLABS_API_KEY (environment or .env in the folder the server starts in).
Without it, /nudges/{id}/audio answers 404 and the live screen speaks with the
browser's own voice instead, so the demo never goes silent.
"""
import json
import os
import urllib.request

VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")   # a calm premade voice; change freely
MODEL_ID = os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5")         # the low-latency model

_cache = {}


def key() -> str:
    found = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not found:
        try:
            with open(os.path.join(os.getcwd(), ".env"), encoding="utf-8") as f:
                for line in f:
                    name, _, value = line.strip().replace("export ", "", 1).partition("=")
                    if name.strip() == "ELEVENLABS_API_KEY":
                        found = value.strip().strip("'\"")
        except OSError:
            pass
    return found


def speak(nudge_id: int, text: str):
    """mp3 bytes for this nudge, or None when there is no key or the call failed."""
    if nudge_id in _cache:
        return _cache[nudge_id]
    secret = key()
    if not secret:
        return None
    body = {"text": text, "model_id": MODEL_ID,
            "voice_settings": {"stability": 0.7, "similarity_boost": 0.75, "speed": 0.9}}
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128" % VOICE_ID,
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"xi-api-key": secret, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    try:
        with urllib.request.urlopen(req, timeout=15) as answer:
            audio = answer.read()
    except Exception as error:
        print("ElevenLabs skipped (status or network):", getattr(error, "code", error))
        return None
    _cache[nudge_id] = audio
    return audio
