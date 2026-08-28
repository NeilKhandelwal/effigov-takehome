# EffiGov take-home — voice intake → cases → dashboard

Three local processes: a LiveKit voice agent that takes service requests, a FastAPI + SQLite backend, and a Next.js staff dashboard.

## Run (three terminals)
```sh
# 1. backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
# 2. dashboard
cd dashboard && npm install && npm run dev        # http://localhost:3000
# 3. voice agent (needs LIVEKIT_* in agent/.env)
cd agent && uv sync && uv run python src/agent.py console
```

See `CONTRACT.md` for the API and `DECISIONS.md` for the tradeoff log.

## What I cut and why
TODO
## Known limitations
TODO
## What I'd do next
TODO
