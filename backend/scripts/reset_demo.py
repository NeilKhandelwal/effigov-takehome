"""Wipe every table and reseed the 3 sample cases, so each demo run starts at C-1004 / CALL-1.

Run with the server up or down: `uv run python -m scripts.reset_demo`.
"""
from app import db
from scripts.seed import SAMPLES, seed

if __name__ == "__main__":
    db.init_db()
    with db.connect() as conn:
        for table in ("transcript", "call_cases", "calls", "case_events", "cases"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence")  # restart AUTOINCREMENT so ids are C-1001.. again
    seed()
    print(f"reset: {len(SAMPLES)} cases, 0 calls")
