import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("CASES_DB", str(Path(__file__).resolve().parent.parent / "cases.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    room TEXT,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS transcript (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_events (
    id INTEGER PRIMARY KEY,
    case_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""

# Run after the ALTER TABLEs below, not inside SCHEMA: on a cases.db predating the
# `room` column, indexing calls(room) has to wait until the column exists.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_cases_phone ON cases(phone);
CREATE INDEX IF NOT EXISTS idx_calls_case_id ON calls(case_id);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
CREATE INDEX IF NOT EXISTS idx_calls_room ON calls(room);
CREATE INDEX IF NOT EXISTS idx_transcript_call_id ON transcript(call_id);
CREATE INDEX IF NOT EXISTS idx_case_events_case_id ON case_events(case_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        try:
            # CREATE TABLE IF NOT EXISTS won't add `room` to a calls table that already exists
            conn.execute("ALTER TABLE calls ADD COLUMN room TEXT")
        except sqlite3.OperationalError:
            pass  # duplicate column: already migrated
        try:
            conn.execute("ALTER TABLE calls ADD COLUMN summary TEXT")
        except sqlite3.OperationalError:
            pass  # duplicate column: already migrated
        conn.executescript(INDEXES)


def case_id(rowid: int) -> str:
    return f"C-{1000 + rowid}"


def rowid_of(case_id: str) -> int | None:
    # "C-1001" -> 1; anything malformed -> None (so lookups 404 instead of 500)
    try:
        return int(case_id.removeprefix("C-")) - 1000
    except ValueError:
        return None


def row_to_case(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["id"] = case_id(d.pop("rowid"))
    return d


def call_id(rowid: int) -> str:
    return f"CALL-{rowid}"


def call_rowid_of(call_id: str) -> int | None:
    try:
        return int(call_id.removeprefix("CALL-"))
    except ValueError:
        return None


def row_to_call(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["id"] = call_id(d.pop("rowid"))
    return d
