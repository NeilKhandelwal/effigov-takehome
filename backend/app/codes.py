"""Three-word lookup codes: the phone number finds nothing, the code is what proves it's you."""
import re
import secrets
import sqlite3

from app.words import WORDS

FILLERS = {"and", "dash"}  # callers glue the words together: "blue and river dash maple"


def normalize(spoken: str) -> str:
    words = [w for w in re.split(r"[\s,-]+", spoken.strip().lower()) if w and w not in FILLERS]
    return "-".join(words)


def new_code(conn: sqlite3.Connection) -> str:
    # 27M combinations, so the retry almost never runs; checking beats an index we'd never use
    while True:
        code = "-".join(secrets.choice(WORDS) for _ in range(3))
        if conn.execute("SELECT 1 FROM cases WHERE lookup_code = ?", (code,)).fetchone() is None:
            return code
