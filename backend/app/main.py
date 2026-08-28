import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

from app import db
from app.models import (Call, CallCreate, CallDetail, CallStatus, CallUpdate, Case, CaseCreate,
                        CaseEvent, CaseUpdate, TranscriptCreate, TranscriptLine)

load_dotenv(".env")  # LIVEKIT_* for /token; python-dotenv ships with uvicorn[standard]

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

# module-level set: single-process demo, so every client is in this one process
clients: set[WebSocket] = set()


async def broadcast(type: str, id: str) -> None:
    frame = json.dumps({"type": type, "id": id})
    for ws in list(clients):
        try:
            await ws.send_text(frame)
        except Exception:
            clients.discard(ws)  # dead socket; drop it and keep going


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # clients never send; this just parks until disconnect
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def fetch_case(conn, rowid: int | None) -> Case:
    row = conn.execute("SELECT * FROM cases WHERE rowid = ?", (rowid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="case not found")
    return Case(**db.row_to_case(row))


def fetch_call(conn, rowid: int | None) -> Call:
    row = conn.execute("SELECT * FROM calls WHERE rowid = ?", (rowid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return Call(**db.row_to_call(row))


def with_transcript(conn, call: Call) -> CallDetail:
    rows = conn.execute("SELECT * FROM transcript WHERE call_id = ? ORDER BY id", (call.id,))
    return CallDetail(**call.model_dump(), transcript=[TranscriptLine(**dict(r)) for r in rows])


def log_event(conn, case_id: str, field: str, old: str | None, new: str | None, source: str) -> None:
    conn.execute(
        "INSERT INTO case_events (case_id, field, old_value, new_value, source, ts) VALUES (?, ?, ?, ?, ?, ?)",
        (case_id, field, old, new, source, now()),
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/token")
def token(identity: str) -> dict:
    """Browser client joins a fresh room; the dev-mode agent is auto-dispatched into it."""
    url = os.environ.get("LIVEKIT_URL")
    key = os.environ.get("LIVEKIT_API_KEY")
    secret = os.environ.get("LIVEKIT_API_SECRET")
    if not (url and key and secret):
        raise HTTPException(status_code=500,
                            detail="LIVEKIT_* env vars not set (see backend/.env.example)")
    room = "call-" + secrets.token_hex(4)
    jwt = (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .to_jwt()
    )
    return {"token": jwt, "url": url, "room": room}


# write endpoints are async so they can await broadcast() after the commit (the `with` exit)
@app.post("/cases", status_code=201)
async def create_case(body: CaseCreate, x_source: str = Header("staff")) -> Case:
    ts = now()
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO cases (name, phone, issue_type, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (body.name, digits(body.phone), body.issue_type, body.description, ts, ts),
        )
        case = fetch_case(conn, cur.lastrowid)
        log_event(conn, case.id, "created", None, case.id, x_source)
    await broadcast("case", case.id)
    return case


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
async def update_case(case_id: str, body: CaseUpdate, x_source: str = Header("staff")) -> Case:
    rowid = db.rowid_of(case_id)
    changes = body.model_dump(exclude_none=True)
    with db.connect() as conn:
        before = fetch_case(conn, rowid)  # 404 before touching anything
        for field, new in changes.items():
            old = getattr(before, field)
            if old != new:  # re-sending the same value is not a change worth auditing
                log_event(conn, before.id, field, old, new, x_source)
        if changes:
            changes["updated_at"] = now()
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE cases SET {sets} WHERE rowid = ?", (*changes.values(), rowid))
        case = fetch_case(conn, rowid)
    await broadcast("case", case.id)
    return case


@app.get("/cases/{case_id}/events")
def list_case_events(case_id: str) -> list[CaseEvent]:
    with db.connect() as conn:
        case = fetch_case(conn, db.rowid_of(case_id))
        rows = conn.execute("SELECT * FROM case_events WHERE case_id = ? ORDER BY id", (case.id,))
        return [CaseEvent(**dict(r)) for r in rows]


@app.get("/cases/{case_id}/calls")
def list_case_calls(case_id: str) -> list[CallDetail]:
    with db.connect() as conn:
        case = fetch_case(conn, db.rowid_of(case_id))
        rows = conn.execute("SELECT * FROM calls WHERE case_id = ? ORDER BY rowid", (case.id,)).fetchall()
        return [with_transcript(conn, Call(**db.row_to_call(r))) for r in rows]


@app.post("/calls", status_code=201)
async def create_call(body: CallCreate = CallCreate()) -> Call:
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO calls (started_at, room) VALUES (?, ?)", (now(), body.room))
        call = fetch_call(conn, cur.lastrowid)
    await broadcast("call", call.id)
    return call


@app.get("/calls")
def list_calls(status: CallStatus | None = None, room: str | None = None) -> list[Call]:
    sql = "SELECT * FROM calls"
    filters = {k: v for k, v in (("status", status), ("room", room)) if v is not None}
    if filters:
        sql += " WHERE " + " AND ".join(f"{k} = ?" for k in filters)
    sql += " ORDER BY rowid DESC"
    with db.connect() as conn:
        return [Call(**db.row_to_call(r)) for r in conn.execute(sql, tuple(filters.values()))]


@app.get("/calls/{call_id}")
def get_call(call_id: str) -> CallDetail:
    with db.connect() as conn:
        return with_transcript(conn, fetch_call(conn, db.call_rowid_of(call_id)))


@app.patch("/calls/{call_id}")
async def update_call(call_id: str, body: CallUpdate, x_source: str = Header("staff")) -> Call:
    rowid = db.call_rowid_of(call_id)
    changes = body.model_dump(exclude_none=True)
    with db.connect() as conn:
        call = fetch_call(conn, rowid)  # 404 before touching anything
        if call.status == "ended" and changes.get("status") in ("active", "needs_person"):
            raise HTTPException(status_code=409, detail="call already ended")
        if "case_id" in changes:
            case = fetch_case(conn, db.rowid_of(changes["case_id"]))  # 404 "case not found"
            log_event(conn, case.id, "call_linked", None, call.id, x_source)
        if changes.get("status") == "ended":
            changes["ended_at"] = now()
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            conn.execute(f"UPDATE calls SET {sets} WHERE rowid = ?", (*changes.values(), rowid))
        call = fetch_call(conn, rowid)
    await broadcast("call", call.id)
    return call


@app.post("/calls/{call_id}/transcript", status_code=201)
async def add_transcript(call_id: str, body: TranscriptCreate) -> TranscriptLine:
    with db.connect() as conn:
        call = fetch_call(conn, db.call_rowid_of(call_id))
        cur = conn.execute(
            "INSERT INTO transcript (call_id, role, text, ts) VALUES (?, ?, ?, ?)",
            (call.id, body.role, body.text, now()),
        )
        row = conn.execute("SELECT * FROM transcript WHERE id = ?", (cur.lastrowid,)).fetchone()
        line = TranscriptLine(**dict(row))
    await broadcast("transcript", call.id)
    return line
