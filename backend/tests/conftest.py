import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


def wipe(url: str) -> None:
    """Postgres runs are against one shared database, so each test starts from nothing —
    schema and all, so alembic runs again and the id sequences restart at C-1001 / CALL-1."""
    from sqlalchemy import create_engine

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # DATABASE_URL set in the environment (CI's postgres job) runs the same suite there;
    # unset, every test gets its own SQLite file so ids always start at C-1001 / CALL-1
    url = os.environ.get("DATABASE_URL")
    from app import db

    if url:
        wipe(url)
    else:
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    db.reset_engine()
    with TestClient(main_app()) as c:  # TestClient's lifespan runs the migrations
        yield c
    db.reset_engine()


def main_app():
    from app import main

    return main.app
