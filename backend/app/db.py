import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("CASES_DB", str(Path(__file__).resolve().parent.parent / "cases.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    issue_type TEXT,  -- NULL = not classified yet (the agent fills it in mid-call)
    description TEXT NOT NULL,
    lookup_code TEXT,  -- NULL = filed before codes existed; that case can't be looked up by voice
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT,  -- the case the agent is working right now; every link lives in call_cases
    status TEXT NOT NULL DEFAULT 'active',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    room TEXT,
    summary TEXT,
    transfer_reason TEXT
);
-- a call can create or look up several cases; this is the truth about which,
-- while calls.case_id is only the cursor (the case the agent is working right now)
CREATE TABLE IF NOT EXISTS call_cases (
    call_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    how TEXT NOT NULL,  -- 'created' | 'looked_up'
    linked_at TEXT NOT NULL,
    PRIMARY KEY (call_id, case_id)
);
CREATE INDEX IF NOT EXISTS call_cases_case ON call_cases (case_id);
CREATE TABLE IF NOT EXISTS transcript (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    source TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        # CREATE TABLE IF NOT EXISTS won't add these to a table that already exists
        add_column(conn, "calls", "room", "TEXT")
        add_column(conn, "calls", "summary", "TEXT")
        add_column(conn, "calls", "transfer_reason", "TEXT")
        add_column(conn, "cases", "lookup_code", "TEXT")
        # DBs written before call_cases existed hold their one link in calls.case_id only
        conn.execute(
            "INSERT OR IGNORE INTO call_cases (call_id, case_id, how, linked_at) "
            "SELECT 'CALL-' || rowid, case_id, 'created', started_at FROM calls WHERE case_id IS NOT NULL"
        )


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
