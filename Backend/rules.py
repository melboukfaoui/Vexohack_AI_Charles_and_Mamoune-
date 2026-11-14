"""The rules engine: decides when to speak up.

on_event() runs the moment something is heard (double dose, leaving a restaurant, leaving
home with the door unlocked). tick() runs every few seconds for things that are about time
passing (a pill not taken, the stove left on, nobody answering a nudge).

Every nudge has a `key`, so a rule speaks once per situation, not on every tick.
"""
from datetime import datetime, timedelta

from store import clock, minutes_ago, now, store

WEARER = "Margaret"
FAMILY_NAME = "Mom"

CONFIG = {
    "pills": [{"name": "blood pressure pill", "due": "09:00"}],   # "HH:MM", local time
    "pill_grace_min": 30,        # wearer reminder this long after the due time
    "pill_escalate_min": 60,     # family alert this long after the due time
    "door_window_min": 15,       # a lock this recent counts when leaving home
    "no_reply_min": 10,          # family alert when a nudge gets no answer
    "stove_min": 45,             # ask about the stove after this long
    "restaurant_items": ["phone", "wallet", "glasses"],
    "item_window_min": 15,       # "got my phone" this recent counts at the table
    "double_dose_hours": 12,     # a second dose inside this window is a double dose
}


def nudge(rule, text, key=None, family=None):
    """Speaks to the wearer and, if given, tells the family too."""
    row = store.add_nudge(rule, "wearer", text, key)
    if family:
        store.add_nudge(rule, "family", family, key and key + ":family")
    return row


def due_today(hhmm: str) -> datetime:
    if len(hhmm) > 5:                      # a full ISO time (the demo sets one to the second)
        return datetime.fromisoformat(hhmm)
    h, m = (int(x) for x in hhmm.split(":"))
    return now().replace(hour=h, minute=m, second=0, microsecond=0)


# -- instant rules ----------------------------------------------------------------------------
def on_event(event: dict):
    kind = event["type"]

    if kind in ("pill_taken", "pill_intent"):
        since = now() - timedelta(hours=CONFIG["double_dose_hours"])
        earlier = store.last_event("pill_taken", since=since, before_id=event["id"])
        if earlier:
            first = datetime.fromisoformat(earlier["ts"])
            when = clock(first) + (" this morning" if first.hour < 12 <= now().hour else "")
            nudge("double_dose", "Wait, you already took it at %s. You said: \"%s\"." % (when, earlier["quote"]),
                  key="double_dose:%d" % event["id"],
                  family="%s almost took a second dose. She was reminded." % FAMILY_NAME)
            if kind == "pill_taken":
                store.retype_event(event["id"], "pill_repeat")   # a warned second dose is not a fresh dose
        elif kind == "pill_taken":
            store.resolve("missed_pill")

    elif kind == "door_locked":
        store.resolve("door")

    elif kind == "stove_off":
        store.resolve("stove")

    elif kind == "leaving_home":
        locked = store.last_event("door_locked", since=minutes_ago(CONFIG["door_window_min"]))
        if not locked and not store.nudged("door", since=minutes_ago(CONFIG["door_window_min"])):
            nudge("door", "You haven't locked the front door yet.", key="door")
        stove = store.last_event("stove_on", since=minutes_ago(180))
        if stove and not store.last_event("stove_off", since=datetime.fromisoformat(stove["ts"])):
            nudge("stove", "Is the stove still on? You put the kettle on at %s." % clock(stove["ts"]),
                  key="stove:%d" % stove["id"])

    elif kind in ("check_requested", "goodbye"):
        if kind == "goodbye" and not store.last_event("check_requested", since=minutes_ago(30)):
            return     # a goodbye at home is not leaving a restaurant
        if store.nudged("restaurant", since=minutes_ago(30)):
            return     # already reminded at this meal
        window = minutes_ago(CONFIG["item_window_min"])
        missing = [i for i in CONFIG["restaurant_items"] if not store.last_event("item_confirmed", since=window, item=i)]
        if missing:
            nudge("restaurant", "Before you go, do you have your %s?" % spoken_list(missing), key="restaurant")


def spoken_list(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# -- rules about time passing -----------------------------------------------------------------
def tick():
    t = now()
    for pill in CONFIG["pills"]:
        due = due_today(pill["due"])
        if t < due:
            continue
        taken = store.last_event("pill_taken", since=due - timedelta(hours=2))   # an early dose counts too
        if taken:
            continue
        key = "missed_pill:%s:%s" % (pill["name"], due.date())
        late = (t - due).total_seconds() / 60
        if late >= CONFIG["pill_grace_min"] and not store.nudged(key):
            nudge("missed_pill", "%s, you haven't taken your %s yet. It was due at %s." % (
                greeting(t), pill["name"], clock(due)), key=key)
        if late >= CONFIG["pill_escalate_min"] and not store.nudged(key + ":family"):
            store.add_nudge("missed_pill", "family", "%s hasn't taken her %s %s." % (
                FAMILY_NAME, clock(due), pill["name"]), key + ":family")

    stove = store.last_event("stove_on", since=minutes_ago(240))
    if stove and not store.last_event("stove_off", since=datetime.fromisoformat(stove["ts"])):
        on_for = (t - datetime.fromisoformat(stove["ts"])).total_seconds() / 60
        key = "stove:%d" % stove["id"]
        if on_for >= CONFIG["stove_min"] and not store.nudged(key):
            nudge("stove", "Is the stove still on? You put the kettle on at %s." % clock(stove["ts"]), key=key)

    escalate_unanswered(t)


ESCALATE = {
    "door": "%s left home and the door may be unlocked." % FAMILY_NAME,
    "stove": "%s may have left the stove on." % FAMILY_NAME,
}


def escalate_unanswered(t):
    """A door or stove nudge nobody answered: tell the family."""
    for rule, text in ESCALATE.items():
        open_nudge = store.open_nudge(rule, "wearer")
        if not open_nudge:
            continue
        waited = (t - datetime.fromisoformat(open_nudge["ts"])).total_seconds() / 60
        key = "%s:%d:family" % (rule, open_nudge["id"])
        if waited >= CONFIG["no_reply_min"] and not store.nudged(key):
            store.add_nudge(rule, "family", text, key)


def greeting(t):
    return "Good morning" if t.hour < 12 else "Good afternoon" if t.hour < 18 else "Good evening"
