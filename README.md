# EffiGov take-home — voice intake → cases → dashboard

A resident calls the City services line, a LiveKit voice agent files a service request, and staff watch the call and triage the case in a dashboard — live.

## What it does

One narrow workflow, end to end:

1. Caller says "I want to report a pothole." The agent collects name and phone (confirmed by reading the digits back; partial numbers are refused) and opens the case right then. As it learns the issue type and a one-sentence description it fills them in with `update_case` — staff watch the fields change mid-call — and only then reads the case ID back.
2. The dashboard shows the call the moment it starts, streams the transcript line by line, and shows the new case at the top of the list — no refresh.
3. Staff open the case, change its status, and see an audit trail of every change and who made it (`staff` vs `voice`).
4. The caller rings back, gives their phone number, and the agent reads the current status from `lookup_case`.

```
 mic ──► agent/  (LiveKit Agents, dev mode)            dashboard/ (Next.js) ◄── Chrome
            │  httpx: POST /cases, /calls, /calls/{id}/transcript          ▲  fetch + WS /ws
            ▼                                                    │
         backend/  (FastAPI + stdlib sqlite3)  ──── broadcast {type,id} ────┘
         tables: cases · calls · transcript · case_events
```

**Data model.** A *call* is not a *case*: one case can have many calls (the report, then the follow-up), and a lookup-only call shouldn't create a junk case. Transcript lines hang off the call; the call links to a case once the agent creates or finds one. Every case *change* appends a `case_events` row (a PATCH that re-sends the same value writes nothing).

**Real-time.** After every write the backend pushes `{"type": "case"|"call"|"transcript", "id": ...}` on `WS /ws`. The socket carries no payload; clients refetch what they're showing. Refetch is idempotent, so duplicate or out-of-order frames can't corrupt UI state. A 2-second poll stays on as a fallback.

**Voice.** LiveKit Inference for STT (AssemblyAI), LLM (`openai/gpt-4.1-mini`, for reliable tool calls with a strict `issue_type` enum), and TTS (Fish Audio) — one LiveKit Cloud key, no other provider accounts. Six function tools: `create_case`, `update_case`, `lookup_case`, `add_note`, `transfer_to_staff` (flags the call `needs_person` and keeps the line open for staff), `end_call`. Every tool swallows backend errors and says so to the caller instead of crashing the call; if the backend is down at call start, the call still works, just without the dashboard.

**Does the agent actually work?** `agent/tests/test_scenarios.py` runs 19 hand-labelled scenarios through the real agent and backend and checks which tools it called with what — and, where it matters, what the caller would hear and what landed in the DB. Three runs, all recorded in [agent/evals/RESULTS.md](agent/evals/RESULTS.md): **12/15** on the first prompt, **14/15** after fixing the two misses it found, **19/19** after adding scenarios for warm transfer, `end_call`, and null-until-classified. Single runs, not re-rolled. `cd agent && uv run pytest -m eval` (LLM calls; deselected by default).

## Run (three terminals — each block starts at the repo root)

**Prereqs:** [uv](https://docs.astral.sh/uv/) (installs Python 3.13 itself), Node 20.9+, and a LiveKit Cloud project for the `LIVEKIT_*` keys (Settings → Keys). Without the keys, everything except the voice call works.

```sh
# 1. backend (http://localhost:8000, SQLite file backend/cases.db — override with CASES_DB=<path>)
cd backend && cp .env.example .env    # LIVEKIT_* (needed only for the browser call's /token)
uv sync && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000
# 2. dashboard (http://localhost:3000 — open it at localhost, not 127.0.0.1, for CORS; backend URL is hardcoded in src/lib/api.ts)
cd dashboard && npm install && npm run dev
# 3. voice agent worker — joins every browser call (LiveKit Cloud dispatch)
cd agent && cp .env.example .env      # LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
uv sync && uv run python src/agent.py download-files   # once: turn-detector / VAD models
uv run python src/agent.py dev
```
Tests: `cd backend && uv run pytest` (21) and `cd agent && uv run pytest` (8; the LLM evals are deselected by default).

Then open http://localhost:3000/call and press **Start call** (Chrome asks for the mic once).

Terminal-only alternative for the voice side: `uv run python src/agent.py console` talks through your mic with no browser.

Reset to a clean demo state at any time (do it right before a demo): `cd backend && uv run python -m scripts.reset_demo` — wipes all tables, reseeds the 3 cases.

Built in the 3-hour window with Claude Code as pair: I set the API contract, data model, and every design decision; agents executed lanes against a written API contract in parallel and I reviewed, tested, and committed each one. Scaffolding came from outside the window: `agent/` from LiveKit's [`agent-starter-python`](https://github.com/livekit-examples/agent-starter-python), `dashboard/` from `create-next-app`, and `backend/` from my own FastAPI + uv project template (layout and tooling only). All application code — endpoints, data model, WebSocket, agent tools and prompt, every dashboard page — was written during the 3 hours.

## API (FastAPI, `backend/app/main.py`)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/cases` | body `{name, phone, issue_type?, description}`; `issue_type` is null until classified |
| `GET` | `/cases[?phone=]` | newest first; `phone` matches digits only |
| `GET` / `PATCH` | `/cases/{id}` | PATCH any of `status`, `notes`, `issue_type`, `description`; header `X-Source` (`staff` default, agent sends `voice`) |
| `GET` | `/cases/{id}/events` | audit log, oldest first |
| `GET` | `/cases/{id}/calls` | that case's calls with transcripts |
| `POST` / `GET` | `/calls[?status=&room=]` | a call record per voice session |
| `GET` / `PATCH` | `/calls/{id}` | PATCH `status` (`active` \| `needs_person` \| `ended`), `case_id`, `summary`, `transfer_reason` |
| `POST` | `/calls/{id}/transcript` | `{role: user\|agent, text}` |
| `GET` | `/token?identity=` | LiveKit join token + a fresh room name for the browser call |
| `GET` | `/health` | `{"ok": true}`; the dashboard uses it to show "Backend unreachable" |
| `WS` | `/ws` | one `{type, id}` frame after every write; clients refetch |

Agent tools (`agent/src/agent.py`): `create_case(name, phone)` · `update_case(issue_type?, description?)` · `lookup_case(phone? | case_id?)` · `add_note(case_id, note)` · `transfer_to_staff(reason)` · `end_call()`.

## What I cut and why

The rule was one narrow workflow, working, over surface area. The big ones:

- **No deployment, no Docker.** The brief says localhost three times. Three processes plus cross-origin WebSockets is exactly where a demo breaks at the last minute.
- **One case table, stdlib `sqlite3`, no ORM.** ~12 SQL statements in the whole project; an ORM would be the third abstraction before the second use.
- **Calls are not cases.** One case gets many calls (the report, the follow-up); a lookup-only call shouldn't create a junk case. Costs a join in two places.
- **WebSocket frames carry `{type, id}` only.** Clients refetch. Idempotent, so repeated or out-of-order frames can't corrupt UI state. Costs one extra GET per event, trivial here.
- **Summary is written by the agent at hang-up, not by a backend job.** The agent already holds the chat history and an LLM; the backend stays LLM-free. Calls that don't end cleanly get no summary.
- **Not built:** supervisory/misinformation agent (a second AI system to defend in a 45-minute call), multilingual, auth, pagination.

## Known limitations

- `notes` is replace-on-write; the agent appends client-side (GET then PATCH). Two simultaneous note-writers would race. One agent, one staff user — acceptable here.
- `PATCH /calls/{id}` re-links silently if `lookup_case` then `create_case` both run on one call; one call → one case is the model.
- `case_events` has no rows for cases created before the table existed (the three seeded ones).
- `db.connect()` connections are released by CPython refcounting, not closed explicitly. Fine for one process.
- The home page does one `GET /calls/{id}` per active call on every refresh (N+1). N is 1 during a demo.
- Console-mode transcripts have `room: "console"`; the `/call` page only shows browser calls.
- A call whose worker dies mid-call stays `active` forever — there's no heartbeat or timeout; `reset_demo` is the only fix.
- The nav opens its own WebSocket on every page just to drive the Live/Polling dot, so each page holds two sockets.
- Notes are a mutable blob beside an append-only event log — two storage models for one history. A note should be a `case_events` row (`field="note"`, with `source` and `ts`).
- A call re-linked from one case to another keeps only the last link in current state; both `call_linked` events survive in the audit log.
- Foreign keys are public-ID strings (`calls.case_id` = `"C-1001"`) and `PRAGMA foreign_keys` is off; integrity is app-enforced by 404-before-write in `main.py`.
- The issue-type enum is written out in three places (backend `Literal`, agent prompt, dashboard array) — deliberate under "hardcode it twice"; the third copy is the signal to centralise it.
- `case_events` only covers case writes: a call's status or summary changing leaves no audit row. Timestamps are second-resolution, so event order relies on `ORDER BY id`.
- The dashboard's 2-second poll is still on as a fallback; the socket makes updates instant, the poll makes them certain — but it runs even when the socket is healthy (see next steps).

## What I'd do next

1. **Transcript tagging and filtering** — after each call, have the summary step also emit tags (topic, sentiment, "resident wants a callback", "wrong department") as structured output onto the call; filter the dashboard by tag, not just status. The pieces exist: the summary already runs an LLM over the transcript, and the filters strip already reads call fields.
2. **Multilingual** — LiveKit's STT/TTS take a language; detect it from the first utterance (or the caller's choice on the greeting), set it on the session, and let the prompt answer in kind while tools keep writing English into the case. EffiGov advertises 30+ languages; this is the cheapest version of that.
3. **Supervisor agent** — a background check on each agent answer against an approved knowledge base (hours, fees, addresses): flag a wrong answer in the transcript, inject the correction, or trigger `transfer_to_staff`. The event hooks and `needs_person` state it needs are already in place; the knowledge base isn't.
4. **Finish the warm transfer** — a staff token and a `/staff/join` page so a person actually enters the room and the agent mutes; today the call is flagged, the transcript is live, but nobody picks up.
5. **Evaluate on real calls** — hand-label 20 recorded calls for issue type and "should have escalated", and report containment (resolved with no human) alongside accuracy. The scenario suite is the offline version of this.
6. **Notes as events** — drop the `notes` column; each note becomes a `case_events` row with its own provenance, killing the GET-then-PATCH race in `add_note`.
7. **Make the 2s poll a real fallback, not a second channel** — `useLiveRefresh` already knows when the socket is up; move the interval into the hook so it polls only while disconnected, and refetch once on every socket `open` so a reconnect catches up immediately. Drops six copies of `setInterval(load, 2000)` and nearly all idle traffic (the home page does 1+N GETs per tick today) with the same guarantees; then a `since` cursor on the list endpoints so a refetch after a long disconnect is cheap. ~15 lines, not done because it touches every page after the freeze. For one-way "something changed" pings, SSE would have been the simpler primitive (native reconnect, no client code); WebSocket was chosen because the brief and their stack say WebSocket.
8. Real telephony (Twilio SIP into the same LiveKit room) — the agent code doesn't change.
