"""Phone notifications through ntfy (https://ntfy.sh): the only way reminders reach people.

Install the free "ntfy" app on the phone and subscribe to the channel names in .env:
    NTFY_TOPIC          the wearer's phone: reminders and answers
    NTFY_FAMILY_TOPIC   the family's phones: alerts
Anyone who knows a channel name can read it, so keep the names long and private.
Works with the screen locked. Sending happens in a thread: a slow network never
holds up the rules.
"""
import os
import threading
import urllib.request

SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")

TITLES = {
    "double_dose": ("Wait - already taken", "5", "pill,warning"),
    "missed_pill": ("Pill reminder", "4", "pill"),
    "restaurant": ("Before you go", "4", "handbag"),
    "door": ("Front door", "4", "door"),
    "stove": ("Stove check", "5", "fire"),
    "answer": ("Memory Band", "3", "speech_balloon"),
    "repeat_question": ("Repeated question", "3", "repeat"),
}


def setting(name: str) -> str:
    found = os.environ.get(name, "").strip()
    if not found:
        try:
            with open(os.path.join(os.getcwd(), ".env"), encoding="utf-8") as f:
                for line in f:
                    key, _, value = line.strip().replace("export ", "", 1).partition("=")
                    if key.strip() == name:
                        found = value.strip().strip("'\"")
        except OSError:
            pass
    return found


def topics() -> dict:
    return {"wearer": setting("NTFY_TOPIC"), "family": setting("NTFY_FAMILY_TOPIC")}


def _post(topic: str, title: str, text: str, priority: str, tags: str):
    req = urllib.request.Request(
        "%s/%s" % (SERVER, topic), data=text.encode("utf-8"), method="POST",
        headers={"Title": title, "Priority": priority, "Tags": tags})
    try:
        with urllib.request.urlopen(req, timeout=10) as answer:
            answer.read()
    except Exception as error:
        print("Phone notification not sent:", getattr(error, "code", error))


def send(nudge: dict):
    """Pushes one nudge row to the wearer's or the family's phone."""
    topic = topics().get(nudge["audience"])
    if not topic:
        return
    title, priority, tags = TITLES.get(nudge["rule"], ("Memory Band", "3", "bell"))
    if nudge["audience"] == "family":
        title = "Family alert: " + title
    threading.Thread(target=_post, args=(topic, title, nudge["text"], priority, tags), daemon=True).start()
