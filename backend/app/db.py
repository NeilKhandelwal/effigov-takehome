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
)
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)


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
