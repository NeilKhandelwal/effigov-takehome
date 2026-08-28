# Decisions

Format: `HH:MM | decision | why | what I gave up`  (T0 = 12:53 PDT)

0:05 | no deploy, no Docker | assignment says localhost only | nothing
0:05 | LiveKit Inference for STT/LLM/TTS, not Gemini | one account, no provider keys, matches their starter | my verified Gemini setup
0:06 | one `cases` table, stdlib sqlite3, no ORM | one clean model; nothing to defend | migrations, relations
0:06 | dashboard polls every 2s; WebSocket only as stretch | "updates without DB edits" in 5 lines | instant updates (until stretch)
0:06 | voice via `agent.py console` (terminal mic) | zero frontend for voice | browser call UI
0:15 | LLM = openai/gpt-4.1-mini via LiveKit Inference (starter default was gemma-4-31b) | flow hinges on tool calls with a strict issue_type enum | one line to flip back
0:16 | all three lanes scaffolded in parallel against CONTRACT.md | contract first made backend/dashboard/agent independent | -
0:18 | core loop verified live: voice -> create_case -> C-1007 in dashboard | - | -
0:19 | stretch = separate calls + transcript tables, WS pushes {type,id} only, client refetches | a call is not a case; refetch-on-event is idempotent so repeated/out-of-order frames can't corrupt state | payload-carrying WS, one fewer round trip
0:27 | audit log = case_events table + X-Source header, not app-level middleware | assignment lists it; ~40 lines, no deps; header is the simplest honest provenance | no events for rows created before the table existed
0:26 | scripts/reset_demo wipes + reseeds | every rehearsal and the live demo start from the same 3 cases | -
0:28 | dashboard grew search/filter + triage panel (user-directed, second session) | search/filter is a listed extra; ~15 min | more UI to defend live
0:31 | transcript = one line per committed turn (conversation_item_added for both roles), not per STT segment | "925." / "915-7062." were two bubbles; the transcript is what the CTO looks at | ~1s later per user line
0:38 | demo from the browser: /token endpoint + dashboard /call page, agent in dev mode | screen-share one Chrome tab with audio instead of a terminal | 3 npm deps + livekit-api; console mode kept as fallback
0:39 | no Docker / hosting | brief says localhost three times; 3 processes + CORS + wss is where a demo breaks at 15:50 | a link the CTO could click
0:45 | update flow verified live: lookup by phone -> note added by voice -> audit shows source=voice -> ended on hang-up | - | -
0:46 | dashboard polish pass (transcript auto-scroll, typing bubble, row flash) in a separate Opus session — user's call over my hold | user judged demo feel worth it | ~20 min, more UI to defend
