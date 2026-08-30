# EffiGov — voice intake → cases → dashboard

A voice intake line for local-government service requests, with a live case desk.

## What it is

A resident calls the City services line. A LiveKit voice agent answers, takes their name and
phone number, opens a service request while they are still explaining it, classifies the issue,
and reads back a case ID plus a three-word lookup code. A second, unrelated problem on the same
call opens its own case, with its own ID and code. When the resident calls back and says their
three words, the agent reads the current status. The phone number is discovery; the code is
authentication, so knowing a number or a case ID gets you nothing.

Staff watch the same call in a Next.js dashboard: the call appears the moment it starts, the
transcript streams line by line, the case fields fill in mid-call, and the new case lands at the
top of the list — no refresh. Staff change status, add notes, and see an audit trail of every
change with who made it (`staff` vs `voice`). A caller who asks for a person flags the call
`needs_person` and the line stays open.

## Architecture

```
 mic ──► agent/  (LiveKit Agents, dev mode)            dashboard/ (Next.js) ◄── Chrome
            │  httpx: POST /cases, /calls, /calls/{id}/transcript      ▲  fetch + WS /ws
            ▼                                                          │
         backend/  (FastAPI + stdlib sqlite3)  ──── broadcast {type,id} ┘
         tables: cases · calls · call_cases · transcript · case_events
```

Three processes, one HTTP contract between them ([docs/CONTRACT.md](docs/CONTRACT.md)). The agent
only ever talks to the backend over HTTP, so the dashboard and the agent were built in parallel
and neither imports the other.

**Real-time.** After every write the backend pushes `{"type": "case"|"call"|"transcript", "id": ...}`
on `WS /ws`. The socket carries no payload; clients refetch what they are showing. Refetch is
idempotent, so duplicate or out-of-order frames cannot corrupt UI state. A 2-second poll stays on
as a fallback (see Phase 1 of the roadmap).

**Voice.** LiveKit Inference for STT (AssemblyAI), LLM (`openai/gpt-4.1-mini`, chosen for reliable
tool calls against a strict `issue_type` enum), and TTS (Fish Audio) — one LiveKit Cloud key, no
other provider accounts. Six function tools: `create_case`, `update_case`, `lookup_case`,
`add_note`, `transfer_to_staff` (flags the call `needs_person` and keeps the line open for staff),
`end_call`. Every tool swallows backend errors and says so to the caller instead of crashing the
call; if the backend is down at call start, the call still works, just without the dashboard.

## Data model

**Cases** (`cases`). One service request. The row id is an `AUTOINCREMENT` integer; the public id
is `"C-" + (1000 + rowid)`, so the first case is `C-1001` and the agent has a short number to read
aloud. `phone` is stored digits-only. `issue_type` is one of `missed_pickup`, `pothole`,
`streetlight`, `water`, `animal`, `other` — and is **null until classified**, because the agent
opens the case before it knows the type. `status` is `open | in_progress | resolved` and only staff
set it. `notes` is a single free-text field that a PATCH replaces wholesale.

**Calls** (`calls`). One voice session, public id `"CALL-" + rowid`. A call is not a case: one case
collects many calls (the report, then the follow-up), and a lookup-only call should not create a
junk case. A call carries `status` (`active | needs_person | ended`), `room` (the LiveKit room, so
the browser page can find its own call), `summary` (written by the agent at hang-up), and
`transfer_reason`. `case_id` is only a **cursor** — the case the agent is working right now.
Ending a call stamps `ended_at`; a PATCH that tries to revive an ended call gets a 409.

**Call ↔ case links** (`call_cases`). The join table is the truth about every case a call touched:
`(call_id, case_id)` primary key, `how` = `created | looked_up`, and `linked_at`. Call JSON exposes
`case_ids` in link order alongside the `case_id` cursor. Linking is idempotent — `POST
/calls/{id}/cases` returns 201 for a new link, 200 when it already existed — so a retry after a
transient failure cannot duplicate anything.

**Audit** (`case_events`). Append-only. `POST /cases` writes a `created` row; a PATCH writes one row
per field that actually changed (re-sending the same value writes nothing); linking writes
`call_linked`; a successful code lookup writes `looked_up`. `source` comes from the `X-Source`
header — `staff` by default, `voice` from the agent, `seed` for the seeded rows. Timestamps are
second-resolution, so ordering relies on `ORDER BY id`.

**Lookup codes.** Three words drawn from a 300-word list (27 million combinations), generated on
case creation and checked for collisions against the table. `POST /cases` is the only response that
carries `lookup_code`; the `Case` model has no such field, so it can never leak from a read.
`GET /cases/lookup?code=` normalizes what the caller said — lowercase, split on spaces, commas and
dashes, drop the fillers `and` and `dash` — so "Blue and River dash Maple" matches `blue-river-maple`.
Unknown and malformed codes get the same 404 (`no case for that code`) so the endpoint is not an
oracle, and five wrong codes on one `X-Call-Id` returns 429.

## Run locally

Docker Compose is coming in Phase 1; today it is three terminals.

**Prereqs:** [uv](https://docs.astral.sh/uv/) (installs Python 3.13 itself), Node 20.9+, and a
LiveKit Cloud project for the `LIVEKIT_*` keys (Settings → Keys). Without the keys, everything
except the voice call works.

```sh
# 1. backend (http://localhost:8000, SQLite file backend/cases.db — override with CASES_DB=<path>)
cd backend && cp .env.example .env    # LIVEKIT_* (needed only for the browser call's /token)
uv sync && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000
# 2. dashboard (http://localhost:3000 — open it at localhost, not 127.0.0.1, for CORS; backend URL from NEXT_PUBLIC_API_URL, default http://localhost:8000)
cd dashboard && npm install && npm run dev
# 3. voice agent worker — joins every browser call (LiveKit Cloud dispatch)
cd agent && cp .env.example .env      # LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
uv sync && uv run python src/agent.py download-files   # once: turn-detector / VAD models
uv run python src/agent.py dev
```
- Env vars: `NEXT_PUBLIC_API_URL` (dashboard → backend, default `http://localhost:8000`) and `CORS_ORIGINS` (backend, comma-separated, default `http://localhost:3000`) — both listed in the matching `.env.example`.

Then open http://localhost:3000/call and press **Start call** (Chrome asks for the mic once).

Terminal-only alternative for the voice side: `uv run python src/agent.py console` talks through
your mic with no browser.

Reset to a clean state at any time: `cd backend && uv run python -m scripts.reset_demo` — wipes all
tables and reseeds the 3 sample cases, printing each case's lookup code.

## Testing

Two kinds, and only one of them costs money.

**Unit** — offline, no keys, no LLM. `cd backend && uv run pytest` (34 tests over the endpoints, the
audit log, call/case linking, and code lookup) and `cd agent && uv run pytest` (12 tests over the
agent's pure helpers — phone validation, code normalization, the filed/second-case gates, summary
assembly). These are what CI runs.

**Evals** — `cd agent && uv run pytest -m eval` runs 21 hand-labelled scenarios through the real
`Assistant` and the real backend in-process, and checks which tools it called with what, what the
caller would hear, and what landed in the database. They make live LLM calls and need `LIVEKIT_*`
in `agent/.env`, so they are deselected by default. Results across three runs are recorded in
[agent/evals/RESULTS.md](agent/evals/RESULTS.md): **12/15** on the first prompt, **14/15** after
fixing the two misses it found, **19/19** after adding scenarios for warm transfer, `end_call`, and
null-until-classified. Single runs, not re-rolled; the two multi-case scenarios added afterwards
have not been run yet.

## API

FastAPI, [`backend/app/main.py`](backend/app/main.py). The full contract, including the shape of
every payload, is in [docs/CONTRACT.md](docs/CONTRACT.md).

| Method | Path | Notes |
|---|---|---|
| `POST` | `/cases` | body `{name, phone, issue_type?, description}`; `issue_type` is null until classified. The only response that carries `lookup_code` |
| `GET` | `/cases[?phone=]` | newest first; `phone` matches digits only |
| `GET` / `PATCH` | `/cases/{id}` | PATCH any of `status`, `notes`, `issue_type`, `description`; header `X-Source` (`staff` default, agent sends `voice`) |
| `GET` | `/cases/lookup?code=` | three spoken words (`blue river maple`, `Blue and River dash Maple`) → the case; 404 `no case for that code` for unknown *and* malformed; 5th wrong code on one `X-Call-Id` → 429 |
| `GET` | `/cases/{id}/events` | audit log, oldest first |
| `GET` | `/cases/{id}/calls` | that case's calls with transcripts |
| `POST` / `GET` | `/calls[?status=&room=]` | a call record per voice session |
| `GET` / `PATCH` | `/calls/{id}` | PATCH `status` (`active` \| `needs_person` \| `ended`), `case_id`, `summary`, `transfer_reason`; a call reads back `case_id` (the case being worked now) and `case_ids` (every case it touched, in link order) |
| `POST` | `/calls/{id}/cases` | body `{case_id, how}` (`created` \| `looked_up`); links the case and makes it the current one. 201 new link, 200 already linked, 404 unknown call or case. One `call_linked` event per (case, call) |
| `POST` | `/calls/{id}/transcript` | `{role: user\|agent, text}` |
| `GET` | `/token?identity=` | LiveKit join token + a fresh room name for the browser call |
| `GET` | `/health` | `{"ok": true}`; the dashboard uses it to show "Backend unreachable" |
| `WS` | `/ws` | one `{type, id}` frame after every write; clients refetch |

Agent tools ([`agent/src/agent.py`](agent/src/agent.py)): `create_case(name, phone)` ·
`update_case(issue_type?, description?)` · `lookup_case(code)` · `add_note(note)` ·
`transfer_to_staff(reason)` · `end_call()`.

## Roadmap

[docs/ROADMAP.md](docs/ROADMAP.md) — five phases, each item with a "done when", plus the working
agreement the repo runs on.

## Decisions

[docs/DECISIONS.md](docs/DECISIONS.md) — one line per decision worth defending: what, why, and what
it cost. [docs/CONTRACT.md](docs/CONTRACT.md) is the API contract every feature is agreed against
before it is built.

## Known limitations

- Notes are a mutable blob beside an append-only event log — two storage models for one history.
  The agent appends client-side (GET then PATCH), so two simultaneous note-writers would race. A
  note should be a `case_events` row (Phase 2).
- Lookup codes are stored in plaintext, so anyone with database or dashboard access can read one. A
  caller who has lost their code has no self-service path: staff verify them another way and read it
  out of the database.
- Cases whose `lookup_code` is NULL — rows written before the column existed — cannot be reached by
  voice at all.
- The wrong-code counter is a module-level dict keyed by call id: single process, cleared on
  restart, and a caller who guesses wrong five times can still get in with the right code
  afterwards. It slows guessing on one call; it is not a real rate limiter.
- A second case is refused until the current one has both an issue type and a description, so a
  caller who raises two problems must finish describing the first. The agent's read-back of two IDs
  and two codes is only as reliable as the LLM.
- Foreign keys are public-ID strings (`calls.case_id` = `"C-1001"`) and `PRAGMA foreign_keys` is
  off; integrity is app-enforced by 404-before-write in `main.py`.
- `calls.case_id` moves to whichever case the agent is working; the full list lives in `call_cases`,
  and a client that only reads the cursor sees the last one.
- `case_events` only covers case writes: a call's status or summary changing leaves no audit row.
- The issue-type enum is written out in three places (backend `Literal`, agent prompt, dashboard
  array) — deliberate under "hardcode it twice"; the third copy is the signal to centralise it.
- `db.connect()` connections are released by CPython refcounting, not closed explicitly. Fine for
  one process.
- The home page does one `GET /calls/{id}` per active call on every refresh (N+1).
- The 2-second poll runs on every page even when the socket is healthy, and the nav opens a second
  socket on every page just to drive the Live/Polling dot (Phase 1).
- A call whose worker dies mid-call stays `active` forever — there is no heartbeat or timeout;
  `reset_demo` is the only fix.
- The `/call` page finds its call by the room name it just generated, so a console-mode call only
  shows up under `/calls`.

## Credits

Scaffolding: `agent/` from LiveKit's
[`agent-starter-python`](https://github.com/livekit-examples/agent-starter-python), `dashboard/`
from `create-next-app`, `backend/` from a personal FastAPI + uv project template (layout and
tooling only).
