"""Answers "did I...?" and "where is my...?" out loud, from the timeline.

The common questions are answered straight from the events (fast, and always quotes what
the wearer said). Anything else goes to OpenAI with today's transcript, when a key is set.
"""
import re
from datetime import datetime

import detector
from rules import FAMILY_NAME
from store import clock, minutes_ago, now, store

PLURAL = {"glasses", "keys"}


def start_of_day():
    return now().replace(hour=0, minute=0, second=0, microsecond=0)


def said(event):
    return "You said: \"%s\"." % event["quote"]


TOPICS = [
    ("door", re.compile(r"\block(ed)?\b.*\bdoor\b|\bdoor\b.*\block(ed)?\b|\block(ed)? up\b")),
    ("pill", re.compile(r"\b(pills?|meds?|medication|medicine|tablets?)\b")),
    ("stove", re.compile(r"\b(stove|oven|kettle|burner|hob)\b")),
    ("where", re.compile(r"\bwhere\b.*\b" + detector.ITEM_RE + r"\b")),
    ("appointment", re.compile(r"\b(appointment|doctor|dentist)\b")),
]


def topic_of(text: str) -> str:
    """door, pill, stove, appointment, where:glasses ... or other."""
    t = detector.normalise(text)
    for name, pattern in TOPICS:
        found = pattern.search(t)
        if found:
            return "where:" + found.group(found.lastindex) if name == "where" else name
    return "other"


def topic_words(topic: str) -> str:
    if topic.startswith("where:"):
        return "where her %s %s" % (topic[6:], "are" if topic[6:] in PLURAL else "is")
    return {"door": "whether she locked the door", "pill": "her pill", "stove": "the stove",
            "appointment": "her appointment"}.get(topic, topic)


def answer(text: str) -> str:
    t = detector.normalise(text)
    topic = topic_of(text)
    today = start_of_day()

    if topic == "door":
        e = store.last_event("door_locked", since=today)
        if e:
            return "Yes. You locked the door at %s. %s" % (clock(e["ts"]), said(e))
        return "I didn't hear you lock the door today. You may want to check it."

    if topic == "pill":
        e = store.last_event("pill_taken", since=today)
        if e:
            return "Yes. You took your pill at %s. %s" % (clock(e["ts"]), said(e))
        return "I haven't heard you take your pill today."

    if topic == "stove":
        on = store.last_event("stove_on", since=today)
        off = store.last_event("stove_off", since=today)
        if off and (not on or off["id"] > on["id"]):
            return "Yes. You turned it off at %s. %s" % (clock(off["ts"]), said(off))
        if on:
            return "I didn't hear you turn it off. You put it on at %s." % clock(on["ts"])
        return "I didn't hear you use the stove today."

    if topic.startswith("where:"):
        item = re.search(detector.ITEM_RE, t).group(1)
        e = store.last_event("item_placed", item=item)
        if e:
            them = "them" if item in PLURAL else "it"
            day = "" if datetime.fromisoformat(e["ts"]) >= today else " yesterday or earlier"
            return "You put %s on the %s at %s%s. %s" % (them, e["place"], clock(e["ts"]), day, said(e))
        return "I didn't hear where you put your %s." % item

    return ask_ai(text)


def ask_ai(question: str) -> str:
    if not detector.ai_available():
        return "I'm not sure. I didn't hear anything about that today."
    heard = "\n".join("[%s] %s" % (clock(r["ts"]), r["text"]) for r in store.rows("transcripts", 150))
    try:
        return detector.ai.ask(
            "What the band heard today:\n%s\n\nQuestion: %s" % (heard, question),
            "You are a calm memory helper for an older adult. Answer their question in one or two short, kind "
            "sentences, using only what the band heard. Say the time when you can. If it was not heard, say so "
            "gently. Never guess.")
    except Exception as error:
        print("AI answer skipped:", error)
        return "I'm not sure. I didn't hear anything about that today."


def handle(text: str, transcript_id: int):
    """Logs the question, answers the wearer, and quietly tells the family on the third repeat."""
    topic = topic_of(text)
    store.add_event("question", text, transcript_id, item=topic, detector="question")
    reply = store.add_nudge("answer", "wearer", answer(text), "answer:%d" % transcript_id)
    if topic != "other":
        asked = store.count_events("question", minutes_ago(60), item=topic)
        key = "repeat:%s" % topic
        if asked >= 3 and not store.nudged(key, since=minutes_ago(60)):
            store.add_nudge("repeat_question", "family",
                            "%s asked about %s %d times this hour." % (FAMILY_NAME, topic_words(topic), asked), key)
    return reply
