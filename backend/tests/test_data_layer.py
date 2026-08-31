"""What the data layer itself has to guarantee: migrations, foreign keys, ids, ?since=."""
import os

import pytest
from sqlalchemy import inspect, insert, select
from sqlalchemy.exc import IntegrityError

from app import db
from tests.conftest import wipe
from tests.test_cases import BODY


def test_migration_builds_the_whole_schema_from_an_empty_database(tmp_path, monkeypatch):
    """A clean clone has no cases.db at all, so `alembic upgrade head` is the only thing
    standing between a fresh checkout and a working desk. Running it twice is a boot."""
    url = os.environ.get("DATABASE_URL")
    if url:
        wipe(url)  # the postgres run tests the same thing on the engine compose and CI use
    else:
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'fresh.db'}")
    db.reset_engine()
    try:
        db.init_db()
        tables = set(inspect(db.engine()).get_table_names())
        assert set(db.metadata.tables) <= tables
        assert "alembic_version" in tables  # the schema's version is recorded, not guessed
        with db.connect() as conn:
            # seeded by the migration: every other table defaults its city_id to this row
            assert [tuple(r) for r in conn.execute(select(db.cities))] == [(1, "Demo City")]
        db.init_db()  # app startup runs it every boot; the second pass must change nothing
    finally:
        db.reset_engine()


@pytest.mark.parametrize("pk", [1, 7, 999, 1234])
def test_public_ids_round_trip(pk):
    """The database stores integers; C-1001 and CALL-7 exist only in the API layer. Every
    endpoint takes the public form, so the two directions have to agree exactly."""
    assert db.case_pk(db.case_id(pk)) == pk
    assert db.call_pk(db.call_id(pk)) == pk
    assert db.case_id(1) == "C-1001" and db.call_id(7) == "CALL-7"


@pytest.mark.parametrize("bad", ["garbage", "C-", "CALL-x", "", "C-nine"])
def test_malformed_public_ids_are_none_so_endpoints_404(bad):
    """A caller reading a mangled id back to the agent must get "no such case", not a 500."""
    assert db.case_pk(bad) is None
    assert db.call_pk(bad) is None


def test_database_rejects_a_link_to_a_case_that_does_not_exist(client):
    """The point of row-id foreign keys: the constraint lives in the database, so a bug that
    slips past main.py's check still cannot orphan a call on a case page."""
    client.post("/calls")
    with pytest.raises(IntegrityError):
        with db.connect() as conn:
            conn.execute(insert(db.call_cases).values(
                call_id=1, case_id=999, how="created", linked_at="2030-01-01T00:00:00Z"))


def test_database_rejects_a_transcript_line_for_a_call_that_does_not_exist(client):
    """Same rule one table over: a transcript with no call is a line nothing can ever show."""
    with pytest.raises(IntegrityError):
        with db.connect() as conn:
            conn.execute(insert(db.transcript).values(
                call_id=999, role="user", text="hi", ts="2030-01-01T00:00:00Z"))


def test_the_api_still_answers_404_not_500_on_those_paths(client):
    """The agent speaks every backend failure aloud, so the constraint must never be what
    the caller hears: main.py checks first and answers 404 in a shape the tools handle."""
    client.post("/calls")
    client.post("/cases", json=BODY)
    assert client.post("/calls/CALL-1/cases", json={"case_id": "C-9999"}).status_code == 404
    assert client.patch("/calls/CALL-1", json={"case_id": "C-9999"}).status_code == 404
    assert client.post("/calls/CALL-9/transcript", json={"role": "user", "text": "x"}).status_code == 404
    assert client.post("/calls/CALL-9/cases", json={"case_id": "C-1001"}).status_code == 404


def test_cases_since_returns_only_what_changed(client, monkeypatch):
    """A dashboard back from a long disconnect refetches everything it missed. With ?since=
    that costs one small response; without it, the whole table on every reconnect."""
    from app import main

    monkeypatch.setattr(main, "now", lambda: "2030-01-01T00:00:00Z")
    client.post("/cases", json=BODY)
    client.post("/cases", json=BODY)
    monkeypatch.setattr(main, "now", lambda: "2030-01-01T00:05:00Z")
    client.patch("/cases/C-1001", json={"status": "resolved"})
    since = {"since": "2030-01-01T00:00:00Z"}
    assert [c["id"] for c in client.get("/cases", params=since).json()] == ["C-1001"]
    # strictly after: a cursor equal to the newest row must not re-send that row
    assert client.get("/cases", params={"since": "2030-01-01T00:05:00Z"}).json() == []
    assert len(client.get("/cases").json()) == 2  # omitted still means everything


def test_calls_since_follows_every_write_to_the_call(client, monkeypatch):
    """A call changes when it is patched and when a transcript line lands; both have to move
    the cursor, or a reconnecting desk shows a call frozen mid-conversation."""
    from app import main

    monkeypatch.setattr(main, "now", lambda: "2030-01-01T00:00:00Z")
    client.post("/calls")
    client.post("/calls")
    monkeypatch.setattr(main, "now", lambda: "2030-01-01T00:05:00Z")
    client.patch("/calls/CALL-1", json={"status": "ended"})
    assert [c["id"] for c in client.get("/calls", params={"since": "2030-01-01T00:00:00Z"}).json()] == ["CALL-1"]
    monkeypatch.setattr(main, "now", lambda: "2030-01-01T00:09:00Z")
    client.post("/calls/CALL-2/transcript", json={"role": "user", "text": "hi"})
    assert [c["id"] for c in client.get("/calls", params={"since": "2030-01-01T00:05:00Z"}).json()] == ["CALL-2"]
    assert len(client.get("/calls").json()) == 2  # omitted still means everything
