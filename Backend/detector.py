"""Turns one sentence the band heard into events on the timeline.

Two layers:
1. Keyword patterns: instant and free, and they cover every line of the demo script.
2. OpenAI (the kit's ai.py, structured output): only for sentences the patterns did not
   understand, run in the background so the live screen never waits for it.
"""
import re
import sys
import threading
from pathlib import Path

ITEMS = ["phone", "wallet", "glasses", "keys", "cane", "purse", "bag", "hearing aid"]
ITEM_RE = r"(phone|wallet|glasses|keys|cane|purse|bag|hearing aid)"

EVENT_TYPES = [
    "pill_taken",       # "taking my blood pressure pill", "pills done"
    "pill_intent",      # "time for my pill": about to take one
    "door_locked",      # "okay, locking up"
    "leaving_home",     # "I'm heading out to the store"
    "check_requested",  # "can we get the check?"
    "goodbye",          # "thank you, have a good day"
    "item_confirmed",   # "got my phone"
    "item_placed",      # "I'll leave my glasses on the kitchen table"
    "stove_on",         # "let me put the kettle on"
    "stove_off",        # "kettle's off"
]

NOT = r"(?<!n't )(?<!not )(?<!never )"

PATTERNS = [
    ("pill_intent", re.compile(r"\b(time for|time to take|should take|let me take|gonna take|going to take|need to take)"
                               r" (my |the )?(\w+ ){0,3}(pills?|meds?|medication|medicine|tablets?)\b")),
    ("pill_taken", re.compile(NOT + r"\b(took|taking|taken|had|swallowed) (my |the )?(\w+ ){0,3}"
                              r"(pills?|meds?|medication|medicine|tablets?)\b")),
    ("pill_taken", re.compile(r"\b(pills?|meds?|medication|medicine) (are |is )?(done|taken)\b")),
    ("door_locked", re.compile(NOT + r"\b(lock(ing|ed)? up|lock(ing|ed)? the (front |back )?door|door('s| is) locked)\b")),
    ("leaving_home", re.compile(r"\b(heading out|head(ing)? to the|going out|off to the|leaving (now|the house|home)|"
                                r"going for a walk|on my way out|i'm off)\b")),
    ("check_requested", re.compile(r"\b(get|have|bring( us)?) the (check|bill)\b|\bcheck,? please\b|\bbill,? please\b")),
    ("goodbye", re.compile(r"\b(have a (good|nice|great) (day|night|evening)|goodbye|bye now|see you (later|soon))\b")),
    ("stove_on", re.compile(r"\b(put|putting) the kettle on\b|\bturn(ing|ed)? on the (stove|oven|burner|hob)\b|"
                            r"\b(start|starting) (the )?(soup|dinner|cooking)\b")),
    ("stove_off", re.compile(r"\b(turn(ed|ing)?|switch(ed|ing)?) (off the (stove|oven|kettle|burner|hob)|the (stove|oven|kettle|burner|hob) off)\b|"
                             r"\b(stove|oven|kettle)('s| is) off\b")),
]

CONFIRM_RE = re.compile(NOT + r"\b(got|have|grabbed|grab|take|took|brought|bring) (my |the )?" + ITEM_RE + r"\b")
PLACE_RE = re.compile(r"\b(leave|leaving|left|put|putting|placed|set|setting) (my |the )?" + ITEM_RE +
                      r" (on|in|by|under|next to|beside) (the |my )?([\w ]{2,40}?)(?:[.,!?]|$| and | so )")

QUESTION_RE = re.compile(r"^\s*(did i|have i|where('s| is| are| did i put)|what time|when('s| is)|who is|"
                         r"what did i|do i have)\b")


def normalise(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def is_question(text: str) -> bool:
    t = normalise(text)
    return bool(QUESTION_RE.search(t)) or (t.endswith("?") and re.search(r"\b(i|my)\b", t) is not None
                                           and not any(type_ == "check_requested" and pattern.search(t)
                                                                       for type_, pattern in PATTERNS))


def keywords(text: str) -> list:
    """[(type, item, place)] found by the patterns. Questions add nothing here."""
    t = normalise(text)
    if QUESTION_RE.search(t):
        return []
    found = []
    for type_, pattern in PATTERNS:
        if pattern.search(t) and not any(f[0] == type_ for f in found):
            if type_ == "pill_taken" and any(f[0] == "pill_intent" for f in found):
                continue          # "time to take my pill" is an intent, not a dose
            found.append((type_, None, None))
    first = CONFIRM_RE.search(t)
    if first:   # "got my phone, my wallet and my glasses": every item after the verb, in that clause
        clause = re.split(r"[.!?;]| but ", t[first.start():])[0]
        for item in dict.fromkeys(re.findall(ITEM_RE, clause)):
            found.append(("item_confirmed", item, None))
    for m in PLACE_RE.finditer(t):
        found.append(("item_placed", m.group(3), m.group(6).strip()))
    return found


# -- the AI layer ---------------------------------------------------------------------------
KIT = Path(__file__).resolve().parent.parent / "vexo-open-kit" / "examples" / "python"
try:
    sys.path.insert(0, str(KIT))
    import ai  # the kit's OpenAI helper (plain HTTPS, reads OPENAI_API_KEY or .env)
except Exception:  # kit missing: the keyword layer still works
    ai = None

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "item", "place"],
                "properties": {
                    "type": {"type": "string", "enum": EVENT_TYPES},
                    "item": {"type": ["string", "null"], "enum": ITEMS + [None]},
                    "place": {"type": ["string", "null"]},
                },
            },
        }
    },
}

INSTRUCTIONS = (
    "You listen to one sentence spoken near an older adult who wears a memory band. "
    "List the everyday actions the WEARER just did or is about to do, using only the given types. "
    "pill_taken = they took or are taking medicine now. pill_intent = they say it is time to take it. "
    "door_locked = they locked the door. leaving_home = they are leaving the house. "
    "check_requested = asking for the bill at a restaurant. goodbye = saying goodbye to leave a place. "
    "item_confirmed = they say they have an item with them. item_placed = they put an item somewhere (give the place). "
    "stove_on / stove_off = stove, oven or kettle switched on or off. "
    "If nothing fits, or it is a question, return an empty list. Never guess."
)


def ai_available() -> bool:
    if ai is None:
        return False
    try:
        ai.key()
        return True
    except Exception:
        return False


def ai_events(text: str) -> list:
    answer = ai.extract(text, SCHEMA, INSTRUCTIONS)
    out = []
    for e in answer.get("events", []):
        if e.get("type") in EVENT_TYPES:
            out.append((e["type"], e.get("item"), e.get("place")))
    return out


def detect(text: str, on_found) -> list:
    """Runs the keyword layer now and returns its events. When it found nothing and an
    OpenAI key is set, asks the model in a thread and calls on_found(events, "ai") later."""
    found = keywords(text)
    if not found and not is_question(text) and len(text.split()) >= 3 and ai_available():
        def work():
            try:
                events = ai_events(text)
            except Exception as error:  # a slow or failing network never breaks the demo
                print("AI detector skipped:", error)
                return
            if events:
                on_found(events, "ai")
        threading.Thread(target=work, daemon=True).start()
    return found
