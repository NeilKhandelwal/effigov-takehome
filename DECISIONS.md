# Decisions

Format: `HH:MM | decision | why | what I gave up`  (T0 = 12:53 PDT)

0:05 | no deploy, no Docker | assignment says localhost only | nothing
0:05 | LiveKit Inference for STT/LLM/TTS, not Gemini | one account, no provider keys, matches their starter | my verified Gemini setup
0:06 | one `cases` table, stdlib sqlite3, no ORM | one clean model; nothing to defend | migrations, relations
0:06 | dashboard polls every 2s; WebSocket only as stretch | "updates without DB edits" in 5 lines | instant updates (until stretch)
0:06 | voice via `agent.py console` (terminal mic) | zero frontend for voice | browser call UI
