"""SQLite connection, transactional state and demo fixtures."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = os.getenv("WAITWISE_DB", "./data/waitwise.sqlite3")
TIMEZONE = os.getenv("WAITWISE_TIMEZONE", "Asia/Shanghai")


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def as_dt(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
    return dt.astimezone(timezone.utc)


def connect():
    path = Path(os.getenv("WAITWISE_DB", DB_PATH)).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=15, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def transaction():
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def query(sql, args=()):
    with connect() as con:
        return [dict(x) for x in con.execute(sql, args).fetchall()]


def one(sql, args=()):
    with connect() as con:
        row = con.execute(sql, args).fetchone()
        return dict(row) if row else None


def clock(con=None):
    if con is None:
        with connect() as db:
            value = db.execute("SELECT value FROM settings WHERE key='offset_minutes'").fetchone()
    else:
        value = con.execute("SELECT value FROM settings WHERE key='offset_minutes'").fetchone()
    offset = int(value[0]) if value else 0
    return now_utc() + timedelta(minutes=offset)


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
  day TEXT NOT NULL, prefix TEXT NOT NULL, value INTEGER NOT NULL,
  PRIMARY KEY (day, prefix)
);
CREATE TABLE IF NOT EXISTS tables (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, capacity INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'FREE', ticket_id INTEGER
);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id TEXT UNIQUE NOT NULL,
  number TEXT NOT NULL, name TEXT NOT NULL, party_size INTEGER NOT NULL,
  phone TEXT NOT NULL DEFAULT '', arrival_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'WAITING',
  checked_in_at TEXT, called_at TEXT, seated_at TEXT, finished_at TEXT,
  table_id INTEGER, priority INTEGER NOT NULL DEFAULT 0,
  phone_requested_at TEXT, phone_response TEXT, promise_deadline TEXT,
  promised_missed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  FOREIGN KEY (table_id) REFERENCES tables(id)
);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status,party_size,created_at);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
  ticket_id INTEGER, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
  title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def seed(con):
    """Demo-only sample data. The fixtures are deliberately relative to server time."""
    from uuid import uuid4
    from .events import emit

    if con.execute("SELECT COUNT(*) FROM tables").fetchone()[0] == 0:
        con.executemany("INSERT INTO tables(id,name,capacity,status) VALUES (?,?,?,'FREE')", [
            (1, "A1 · 窗边双人桌", 2), (2, "A2 · 双人桌", 2),
            (3, "B1 · 四人桌", 4), (4, "B2 · 四人桌", 4),
            (5, "C1 · 六人桌", 6)
        ])
    if con.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]:
        return
    base = clock(con)
    demo = [
        ("陈小姐", 2, -15, True),
        ("何先生", 4, -8, True),
        ("林女士", 2, 18, False),
        ("周同学", 2, 28, False),
        ("许先生", 4, 35, False),
        ("许小姐", 6, 52, False),
    ]
    day = base.astimezone(ZoneInfo(TIMEZONE)).strftime("%Y%m%d")
    for index, (name, party, delta, arrived) in enumerate(demo):
        prefix = "A" if party <= 2 else ("B" if party <= 4 else "C")
        row = con.execute("SELECT value FROM counters WHERE day=? AND prefix=?", (day, prefix)).fetchone()
        number = (int(row[0]) if row else 0) + 1
        con.execute("INSERT INTO counters(day,prefix,value) VALUES(?,?,?) ON CONFLICT(day,prefix) DO UPDATE SET value=excluded.value", (day, prefix, number))
        at = iso(base - timedelta(minutes=(len(demo)-index)*2))
        cur = con.execute("""INSERT INTO tickets(request_id,number,name,party_size,phone,arrival_at,status,checked_in_at,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)""", (str(uuid4()), f"{prefix}{number:03d}", name, party, "", iso(base+timedelta(minutes=delta)), "WAITING", iso(base-timedelta(minutes=2)) if arrived else None, at, at))
        emit(con, "TicketCreated", cur.lastrowid, f"{name} 已加入候位", at)
    emit(con, "DemoReady", None, "系统已装载示例候位与餐桌", iso(base))


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)  # schema initialization runs before transactions
    with transaction() as con:
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('offset_minutes','0')")
        seed(con)
