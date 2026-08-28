"""Insert 3 sample cases if the table is empty. Safe to re-run."""
from datetime import datetime, timezone

from app import db

SAMPLES = [
    ("Maria Lopez", "5551234567", "missed_pickup", "Trash not collected on Elm St Tuesday"),
    ("James Carter", "5559876543", "pothole", "Large pothole on Main St near 4th Ave, hit it twice this week"),
    ("Priya Nair", "5555550123", "streetlight", "Streetlight out at Oak St and Pine Ave, dark corner at night"),
]

def seed() -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db.connect() as conn:
        if conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]:
            print("cases table not empty, skipping seed")
        else:
            for sample in SAMPLES:
                cur = conn.execute(
                    "INSERT INTO cases (name, phone, issue_type, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (*sample, ts, ts),
                )
                # seeded cases get a 'created' audit row too, so their History isn't empty
                conn.execute(
                    "INSERT INTO case_events (case_id, field, old_value, new_value, source, ts) "
                    "VALUES (?, 'created', NULL, ?, 'seed', ?)",
                    (db.case_id(cur.lastrowid), db.case_id(cur.lastrowid), ts),
                )
            print(f"seeded {len(SAMPLES)} cases")


if __name__ == "__main__":
    db.init_db()
    seed()
