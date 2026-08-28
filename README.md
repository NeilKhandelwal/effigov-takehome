# EffiGov take-home — voice intake → cases → dashboard

Three local processes: a LiveKit voice agent that takes service requests, a FastAPI + SQLite backend, and a Next.js staff dashboard.

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

See `CONTRACT.md` for the API and `DECISIONS.md` for the tradeoff log.

## What I cut and why
TODO
## Known limitations
TODO
## What I'd do next
TODO
