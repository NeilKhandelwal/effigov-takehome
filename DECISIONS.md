# Decisions

Format: `HH:MM | decision | why | what I gave up`  (T0 = 12:53 PDT)

0:05 | no deploy, no Docker | assignment says localhost only | nothing
0:05 | LiveKit Inference for STT/LLM/TTS, not Gemini | one account, no provider keys, matches their starter | my verified Gemini setup
0:06 | one `cases` table, stdlib sqlite3, no ORM | one clean model; nothing to defend | migrations, relations
0:06 | dashboard polls every 2s; WebSocket only as stretch | "updates without DB edits" in 5 lines | instant updates (until stretch)
0:06 | voice via `agent.py console` (terminal mic) | zero frontend for voice | browser call UI
0:15 | LLM = openai/gpt-4.1-mini via LiveKit Inference (starter default was gemma-4-31b) | flow hinges on tool calls with a strict issue_type enum | one line to flip back
0:16 | all three lanes scaffolded in parallel against CONTRACT.md | contract first made backend/dashboard/agent independent | -
