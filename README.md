# EffiGov take-home — voice intake → cases → dashboard

A resident calls the City services line, a LiveKit voice agent files a service request, and staff watch the call and triage the case in a dashboard — live.

## What it does

One narrow workflow, end to end:

1. Caller says "I want to report a pothole." The agent collects name, phone (confirmed by reading digits back), issue type, and a one-sentence description, then calls `create_case` and reads the case ID back.
2. The dashboard shows the call the moment it starts, streams the transcript line by line, and shows the new case at the top of the list — no refresh.
3. Staff open the case, change its status, and see an audit trail of every change and who made it (`staff` vs `voice`).
4. The caller rings back, gives their phone number, and the agent reads the current status from `lookup_case`.

```
 mic ──► agent/  (LiveKit Agents, console mode)          dashboard/ (Next.js) ◄── Chrome
            │  httpx: POST /cases, /calls, /transcript          ▲  fetch + WS /ws
            ▼                                                    │
         backend/  (FastAPI + stdlib sqlite3)  ──── broadcast {type,id} ────┘
         tables: cases · calls · transcript · case_events
```

**Data model.** A *call* is not a *case*: one case can have many calls (the report, then the follow-up), and a lookup-only call shouldn't create a junk case. Transcript lines hang off the call; the call links to a case once the agent creates or finds one. Every case write appends a `case_events` row.

**Real-time.** After every write the backend pushes `{"type": "case"|"call"|"transcript", "id": ...}` on `WS /ws`. The socket carries no payload; clients refetch what they're showing. Refetch is idempotent, so duplicate or out-of-order frames can't corrupt UI state. A 2-second poll stays on as a fallback.

**Voice.** LiveKit Inference for STT (AssemblyAI), LLM (`openai/gpt-4.1-mini`, for reliable tool calls with a strict `issue_type` enum), and TTS (Fish Audio) — one LiveKit Cloud key, no other provider accounts. Three function tools: `create_case`, `lookup_case`, `add_note`. Every tool swallows backend errors and says so to the caller instead of crashing the call; if the backend is down at call start, the call still works, just without the dashboard.

## Run (three terminals)
```sh
# 1. backend (http://localhost:8000, SQLite file backend/cases.db)
cd backend && uv sync && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000
# 2. dashboard
cd dashboard && npm install && npm run dev        # http://localhost:3000
# 3. voice agent — talk to it from your terminal mic (LiveKit console mode)
cd agent && cp .env.example .env   # fill LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET
uv sync && uv run python src/agent.py console
```

Before a demo: `cd backend && uv run python -m scripts.reset_demo` (wipes all tables, reseeds 3 cases). Reset to a clean demo state at any time: `cd backend && uv run python -m scripts.reset_demo`.

Built in the 3-hour window with Claude Code as pair: I set the contract, data model, and every design decision (see `DECISIONS.md`); agents executed lanes against `CONTRACT.md` in parallel and I reviewed, tested, and committed each one.

`CONTRACT.md` is the API contract all three parts were built against; `DECISIONS.md` is the timestamped tradeoff log.

## What I cut and why
TODO
## Known limitations
TODO
## What I'd do next
TODO
