"""The memory timeline: what was heard, what it meant, and what we said back.

SQLite in one file (Backend/memory.db). Every row is also pushed to the live screen
through `hub`, so the page updates the moment something happens.
"""
import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "memory.db"


def now() -> datetime:
    """Local time with a timezone, so "9 AM" means 9 AM where the wearer is."""
    return datetime.now().astimezone()


def clock(ts) -> str:
    """12:40 style time for spoken sentences."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    return ts.strftime("%-I:%M %p")


class Hub:
    """Fans every new row out to the open live screens (Server-Sent Events).
    Rules and the AI detector run in threads, so publish() is thread safe."""

    def __init__(self):
        self.loop = None
        self.queues = set()

    def publish(self, kind: str, row: dict):
        if self.loop is None:
            return
        message = json.dumps({"kind": kind, "row": row})
        for q in list(self.queues):
            self.loop.call_soon_threadsafe(q.put_nowait, message)


hub = Hub()


class Store:
    def __init__(self, path=DB_PATH):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, text TEXT NOT NULL, source TEXT);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, type TEXT NOT NULL,
                item TEXT, place TEXT, quote TEXT, transcript_id INTEGER, detector TEXT);
            CREATE TABLE IF NOT EXISTS nudges (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, rule TEXT NOT NULL,
                audience TEXT NOT NULL, text TEXT NOT NULL, key TEXT, resolved INTEGER DEFAULT 0);
            """
        )
        self.db.commit()

    # -- writing -------------------------------------------------------------------------
    def _insert(self, table: str, kind: str, **fields) -> dict:
        with self.lock:
            fields.setdefault("ts", now().isoformat())
            cols = ", ".join(fields)
            marks = ", ".join("?" for _ in fields)
            cur = self.db.execute("INSERT INTO %s (%s) VALUES (%s)" % (table, cols, marks), list(fields.values()))
            self.db.commit()
            row = dict(self.db.execute("SELECT * FROM %s WHERE id = ?" % table, (cur.lastrowid,)).fetchone())
        hub.publish(kind, row)
        return row

    def add_transcript(self, text: str, source: str = "band") -> dict:
        return self._insert("transcripts", "transcript", text=text, source=source)

    def add_event(self, type_: str, quote: str, transcript_id=None, item=None, place=None, detector="keywords") -> dict:
        return self._insert("events", "event", type=type_, quote=quote, transcript_id=transcript_id,
                            item=item, place=place, detector=detector)

    def add_nudge(self, rule: str, audience: str, text: str, key: str = None) -> dict:
        return self._insert("nudges", "nudge", rule=rule, audience=audience, text=text, key=key)

    def resolve(self, rule: str = None, nudge_id: int = None):
        """Marks open nudges as answered (the wearer did the thing, or tapped the band)."""
        with self.lock:
            if nudge_id is not None:
                self.db.execute("UPDATE nudges SET resolved = 1 WHERE id = ?", (nudge_id,))
            elif rule is not None:
                self.db.execute("UPDATE nudges SET resolved = 1 WHERE rule = ? AND resolved = 0", (rule,))
            else:
                self.db.execute("UPDATE nudges SET resolved = 1 WHERE resolved = 0")
            self.db.commit()
        hub.publish("resolved", {"rule": rule, "id": nudge_id})

    def retype_event(self, event_id: int, type_: str):
        with self.lock:
            self.db.execute("UPDATE events SET type = ? WHERE id = ?", (type_, event_id))
            self.db.commit()
            row = dict(self.db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone())
        hub.publish("event_changed", row)

    def open_nudge(self, rule: str, audience: str):
        with self.lock:
            row = self.db.execute("SELECT * FROM nudges WHERE rule = ? AND audience = ? AND resolved = 0 "
                                  "ORDER BY id DESC LIMIT 1", (rule, audience)).fetchone()
        return dict(row) if row else None

    def reset(self):
        with self.lock:
            self.db.executescript("DELETE FROM transcripts; DELETE FROM events; DELETE FROM nudges;")
            self.db.commit()
        hub.publish("reset", {})

    # -- reading -------------------------------------------------------------------------
    def rows(self, table: str, limit: int = 200) -> list:
        with self.lock:
            got = self.db.execute("SELECT * FROM %s ORDER BY id DESC LIMIT ?" % table, (limit,)).fetchall()
        return [dict(r) for r in reversed(got)]

    def last_event(self, types, since: datetime = None, item: str = None, before_id: int = None):
        types = [types] if isinstance(types, str) else list(types)
        sql = "SELECT * FROM events WHERE type IN (%s)" % ",".join("?" for _ in types)
        args = list(types)
        if since is not None:
            sql += " AND ts >= ?"
            args.append(since.isoformat())
        if item is not None:
            sql += " AND item = ?"
            args.append(item)
        if before_id is not None:
            sql += " AND id < ?"
            args.append(before_id)
        sql += " ORDER BY id DESC LIMIT 1"
        with self.lock:
            row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def count_events(self, type_: str, since: datetime, item: str = None) -> int:
        sql, args = "SELECT COUNT(*) FROM events WHERE type = ? AND ts >= ?", [type_, since.isoformat()]
        if item is not None:
            sql += " AND item = ?"
            args.append(item)
        with self.lock:
            return self.db.execute(sql, args).fetchone()[0]

    def nudged(self, key: str, since: datetime = None) -> dict:
        """The latest nudge with this key (so a rule fires once, not every tick)."""
        sql, args = "SELECT * FROM nudges WHERE key = ?", [key]
        if since is not None:
            sql += " AND ts >= ?"
            args.append(since.isoformat())
        with self.lock:
            row = self.db.execute(sql + " ORDER BY id DESC LIMIT 1", args).fetchone()
        return dict(row) if row else None

    def get_nudge(self, nudge_id: int):
        with self.lock:
            row = self.db.execute("SELECT * FROM nudges WHERE id = ?", (nudge_id,)).fetchone()
        return dict(row) if row else None


store = Store()


def minutes_ago(n: float) -> datetime:
    return now() - timedelta(minutes=n)
