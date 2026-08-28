# EffiGov take-home — voice intake → cases → dashboard

A resident calls the City services line, a LiveKit voice agent files a service request, and staff watch the call and triage the case in a dashboard — live.

## What it does

One narrow workflow, end to end:

1. Caller says "I want to report a pothole." The agent collects name, phone (confirmed by reading digits back), issue type, and a one-sentence description, then calls `create_case` and reads the case ID back.
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

**Voice.** LiveKit Inference for STT (AssemblyAI), LLM (`openai/gpt-4.1-mini`, for reliable tool calls with a strict `issue_type` enum), and TTS (Fish Audio) — one LiveKit Cloud key, no other provider accounts. Three function tools: `create_case`, `lookup_case`, `add_note`. Every tool swallows backend errors and says so to the caller instead of crashing the call; if the backend is down at call start, the call still works, just without the dashboard.

## Run (three terminals)

**Prereqs:** [uv](https://docs.astral.sh/uv/) (installs Python 3.13 itself), Node 20+, and a LiveKit Cloud project for the `LIVEKIT_*` keys (Settings → Keys). Without the keys, everything except the voice call works.

```sh
# 1. backend (http://localhost:8000, SQLite file backend/cases.db)
cd backend && cp .env.example .env    # LIVEKIT_* (needed only for the browser call's /token)
uv sync && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000
# 2. dashboard (http://localhost:3000 — open it at localhost, not 127.0.0.1, for CORS; backend URL is hardcoded in src/lib/api.ts)
cd dashboard && npm install && npm run dev
# 3. voice agent worker — joins every browser call (LiveKit Cloud dispatch)
cd agent && cp .env.example .env      # LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
uv sync && uv run python src/agent.py download-files   # once: turn-detector / VAD models
uv run python src/agent.py dev
```
Then open http://localhost:3000/call and press **Start call** (Chrome asks for the mic once).

Terminal-only alternative for the voice side: `uv run python src/agent.py console` talks through your mic with no browser.

Reset to a clean demo state at any time (do it right before a demo): `cd backend && uv run python -m scripts.reset_demo` — wipes all tables, reseeds the 3 cases.

Built in the 3-hour window with Claude Code as pair: I set the contract, data model, and every design decision (see `DECISIONS.md`); agents executed lanes against `CONTRACT.md` in parallel and I reviewed, tested, and committed each one. Scaffolding came from outside the window: `agent/` from LiveKit's [`agent-starter-python`](https://github.com/livekit-examples/agent-starter-python), `dashboard/` from `create-next-app`, and `backend/` from my own FastAPI + uv project template (layout and tooling only). All application code — endpoints, data model, WebSocket, agent tools and prompt, every dashboard page — was written during the 3 hours.

`CONTRACT.md` is the API contract all three parts were built against; `DECISIONS.md` is the timestamped tradeoff log.

## What I cut and why

The rule was one narrow workflow, working, over surface area. Timestamped log in `DECISIONS.md`. The big ones:

- **No deployment, no Docker.** The brief says localhost three times. Three processes plus cross-origin WebSockets is exactly where a demo breaks at the last minute.
- **One case table, stdlib `sqlite3`, no ORM.** ~12 SQL statements in the whole project; an ORM would be the third abstraction before the second use.
- **Calls are not cases.** One case gets many calls (the report, the follow-up); a lookup-only call shouldn't create a junk case. Costs a join in two places.
- **WebSocket frames carry `{type, id}` only.** Clients refetch. Idempotent, so repeated or out-of-order frames can't corrupt UI state. Costs one extra GET per event, trivial here.
- **Summary is written by the agent at hang-up, not by a backend job.** The agent already holds the chat history and an LLM; the backend stays LLM-free. Calls that don't end cleanly get no summary.
- **Not built:** supervisory/misinformation agent (a second AI system to defend in a 45-minute call), multilingual, transfer-to-human, auth, pagination.

## Known limitations

- **STT mishears names** (Khandelwal → "Kendall Wall"). The agent applies a spelled name, but the first attempt will often be wrong on the transcript.
- `notes` is replace-on-write; the agent appends client-side (GET then PATCH). Two simultaneous note-writers would race. One agent, one staff user — acceptable here.
- `PATCH /calls/{id}` re-links silently if `lookup_case` then `create_case` both run on one call; one call → one case is the model.
- `case_events` has no rows for cases created before the table existed (the three seeded ones).
- `db.connect()` connections are released by CPython refcounting, not closed explicitly. Fine for one process.
- The home page does one `GET /calls/{id}` per active call on every refresh (N+1). N is 1 during a demo.
- Console-mode transcripts have `room: "console"`; the `/call` page only shows browser calls.
- A call whose worker dies mid-call stays `active` forever — there's no heartbeat or timeout; `reset_demo` is the only fix.
- The nav opens its own WebSocket on every page just to drive the Live/Polling dot, so each page holds two sockets.
- The dashboard's 2-second poll is still on as a fallback; the socket makes updates instant, the poll makes them certain.

## What I'd do next

1. **Progressive case fields** — create the case as soon as name + phone + type are known and update description/status as the call goes on, so staff see fields change mid-call (their "issue type updates once confident" behaviour).
2. **Warm transfer** — a `transfer_to_staff` tool that flips the call to `needs_person`, pushes it to the top of the live strip with the transcript, and tells the caller someone is picking up.
3. **Evaluate the agent, not just run it** — hand-label 20 calls for issue type and "should have escalated", run them through the agent, and report **containment** (calls resolved with no human handoff) alongside issue-type accuracy, including where it's wrong. Containment is the number a city actually asks for.
4. Replace the 2s poll with WS-only once reconnect handling is proven; add a `since` cursor so refetches after reconnect are cheap.
5. Real telephony (Twilio SIP into the same LiveKit room) — the agent code doesn't change.
