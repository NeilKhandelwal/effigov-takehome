import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # fresh DB per test so ids always start at C-1001 / CALL-1
    monkeypatch.setenv("CASES_DB", str(tmp_path / "test.db"))
    from app import db, main
    monkeypatch.setattr(db, "DB_PATH", os.environ["CASES_DB"])
    with TestClient(main.app) as c:
        yield c
