"""Three-word lookup codes: the phone number finds nothing, the code is what proves it's you."""
import re
import secrets

from sqlalchemy import select

from app import db
from app.words import WORDS

FILLERS = {"and", "dash"}  # callers glue the words together: "blue and river dash maple"


def normalize(spoken: str) -> str:
    words = [w for w in re.split(r"[\s,-]+", spoken.strip().lower()) if w and w not in FILLERS]
    return "-".join(words)


def new_code(conn) -> str:
    # 27M combinations, so the retry almost never runs
    while True:
        code = "-".join(secrets.choice(WORDS) for _ in range(3))
        taken = conn.execute(
            select(db.cases.c.id).where(db.cases.c.lookup_code == code)
        ).fetchone()
        if taken is None:
            return code
