import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.models import Case, CaseCreate, CaseUpdate

@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="EffiGov cases", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def fetch_case(conn, rowid: int | None) -> Case:
    row = conn.execute("SELECT * FROM cases WHERE rowid = ?", (rowid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="case not found")
    return Case(**db.row_to_case(row))


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/cases", status_code=201)
def create_case(body: CaseCreate) -> Case:
    ts = now()
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO cases (name, phone, issue_type, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (body.name, digits(body.phone), body.issue_type, body.description, ts, ts),
        )
        return fetch_case(conn, cur.lastrowid)


@app.get("/cases")
def list_cases(phone: str | None = None) -> list[Case]:
    sql = "SELECT * FROM cases"
    params: tuple = ()
    if phone is not None:
        sql += " WHERE phone = ?"
        params = (digits(phone),)
    sql += " ORDER BY rowid DESC"
    with db.connect() as conn:
        return [Case(**db.row_to_case(r)) for r in conn.execute(sql, params)]


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> Case:
    with db.connect() as conn:
        return fetch_case(conn, db.rowid_of(case_id))


@app.patch("/cases/{case_id}")
def update_case(case_id: str, body: CaseUpdate) -> Case:
    rowid = db.rowid_of(case_id)
    changes = body.model_dump(exclude_none=True)
    with db.connect() as conn:
        fetch_case(conn, rowid)  # 404 before touching anything
        if changes:
            changes["updated_at"] = now()
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE cases SET {sets} WHERE rowid = ?", (*changes.values(), rowid))
        return fetch_case(conn, rowid)
