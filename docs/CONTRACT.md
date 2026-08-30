# API contract (fixed 13:00 — all three lanes build against this)

Backend on http://localhost:8000. JSON everywhere. Errors: 404 {"detail": "..."}, 422 on bad body.

## Case
```json
{
  "id": "C-1001",              // string, "C-" + 4-digit autoincrement starting 1001; agent reads it aloud
  "name": "Maria Lopez",
  "phone": "5551234567",       // digits only, stored as given after stripping non-digits
  "issue_type": "missed_pickup", // one of: missed_pickup | pothole | streetlight | water | animal | other
                               // null until classified — the agent opens the case before it knows the type
  "description": "Trash not collected on Elm St Tuesday",
  "status": "open",            // open | in_progress | resolved
  "notes": "",                 // free text, appended to by agent/staff
  "created_at": "2026-08-28T20:01:02Z",
  "updated_at": "2026-08-28T20:01:02Z"
}
```

## Endpoints
- `POST /cases` body {name, phone, description, optional issue_type} -> 201 Case (status=open, notes="", issue_type=null if omitted)
- `GET /cases` -> [Case], newest first. Optional `?phone=` (digits) filters exact match.
- `GET /cases/{id}` -> Case | 404
- `PATCH /cases/{id}` body any of {status, notes, issue_type, description} -> Case | 404
  - `notes` REPLACES. To append, client GETs then PATCHes (agent does this in add_note).
- `GET /health` -> {"ok": true}

## Stretch (locked 13:12) — a call is not a case
```json
Call: {"id": "CALL-7", "case_id": null | "C-1001", "status": "active"|"ended",
       "started_at": "...Z", "ended_at": null | "...Z"}
TranscriptLine: {"id": 12, "call_id": "CALL-7", "role": "user"|"agent", "text": "...", "ts": "...Z"}
```
- `POST /calls` body {} -> 201 Call (status=active). id = "CALL-" + rowid (no offset).
- `GET /calls` -> [Call] newest first; `?status=active` filters.
- `GET /calls/{id}` -> Call + `"transcript": [TranscriptLine]` | 404
- `PATCH /calls/{id}` body any of {status, case_id} -> Call | 404. status=ended sets ended_at.
- `POST /calls/{id}/transcript` body {role, text} -> 201 TranscriptLine | 404
- `GET /cases/{id}/calls` -> [Call + transcript] for that case, oldest first
- `WS /ws` -> after EVERY write (case create/patch, call create/patch, transcript append) server pushes
  one JSON text frame: {"type": "case"|"call"|"transcript", "id": "<case or call id>"}.
  Clients treat any frame as "refetch what you're showing". Never carry payloads on the socket.
- Dashboard: keeps the 2s poll as fallback; on any WS frame, refetch immediately.
  Home page gets a "Live calls" strip (active calls, last transcript line, link to /calls/[id]).
  /calls/[id] shows the transcript streaming; case detail lists its calls + transcripts.
- Agent: POST /calls on session start; final user utterances and agent replies -> POST transcript
  (strip `<expr .../>` tags from agent text); create_case/lookup_case PATCH call.case_id;
  on session close PATCH status=ended.

## Audit (added 13:17)
Every case write is logged; the dashboard shows it on case detail.
```json
CaseEvent: {"id": 3, "case_id": "C-1001", "field": "status", "old_value": "open", "new_value": "in_progress",
            "source": "voice", "ts": "...Z"}
```
- `GET /cases/{id}/events` -> [CaseEvent] oldest first | 404
- Written by: POST /cases (field="created", new_value=case id); PATCH /cases/{id} (one per field that
  actually changed; unchanged fields skipped); PATCH /calls/{id} with case_id (field="call_linked", new_value=call id).
- `source` = request header `X-Source` (default "staff"). Agent sends `X-Source: voice` on every write.

## Agent tools (LiveKit function tools, call backend via httpx)
- create_case(name, phone) -> "Started case C-1001" (opens with issue_type="other", description=""; refuses non-10-digit phones)
- update_case(issue_type?, description?) -> fills fields on the case this call opened, as the caller explains
- lookup_case(phone) -> summary of most recent case for that phone, or "none found"
- add_note(case_id, note) -> appends line to notes
- transfer_to_staff(reason) -> PATCH call status=needs_person + transfer_reason; line stays open (see "## Warm transfer")
- end_call() -> after goodbye has played, ends the session (shutdown callback writes summary + status=ended)

## Ports
backend :8000, dashboard :3000, agent = console process (no port)

## Browser call (added 13:28) — demo from the dashboard, not the terminal
Agent runs in `dev` mode (`uv run python src/agent.py dev`, no `agent_name` → auto-dispatched to every new room).
Console mode keeps working for local testing.
- `GET /token?identity=<string>` -> {"token": "<jwt>", "url": LIVEKIT_URL, "room": "call-<8 hex>"}. Backend signs with
  LIVEKIT_API_KEY/SECRET from backend/.env (dep: livekit-api). Room name is generated per token; grants: roomJoin + publish/subscribe (the browser must publish mic audio).
- `calls` gains nullable `room TEXT`. `POST /calls` accepts optional {"room": "..."}; the agent sends ctx.room.name.
  `GET /calls?room=<name>` -> [Call] (exact match). Call JSON includes "room".
- Dashboard `/call`: "Start call" -> fetch token -> LiveKitRoom (audio only) with RoomAudioRenderer, a voice-assistant
  bar visualizer, "Hang up" (disconnect). Beside it: the live transcript of the call whose room matches, found via
  `GET /calls?room=` (poll + WS refresh like everywhere else), with a link to the case once linked.
  Deps: @livekit/components-react, @livekit/components-styles, livekit-client.
- Call end: when the browser participant disconnects, the agent job shuts down -> existing end_call marks status=ended.

## Summary (added 13:37)
- `calls` gains nullable `summary TEXT`; Call JSON includes `"summary"` (null until written).
- `PATCH /calls/{id}` accepts `{"summary": "..."}` like its other fields; staff can also edit it.
- Written by: the agent, in its shutdown callback, right before it PATCHes status=ended — it asks the
  same LLM for at most two sentences over the call's own transcript. Fewer than 2 turns, or any LLM
  failure -> no summary written (stays null); the call is still marked ended.
- Dashboard: shows it on /calls/[id] and on the case's call list; absent = "no summary".

## Warm transfer (added 14:05) — the caller asks for a person
- `CallStatus` gains `"needs_person"`: `active | needs_person | ended`. It is a live status, not a terminal
  one — `ended_at` stays null until the call is actually ended.
- `calls` gains nullable `transfer_reason TEXT`; Call JSON includes `"transfer_reason"` (null unless transferred).
- `PATCH /calls/{id}` accepts `{"status": "needs_person", "transfer_reason": "..."}` like its other fields;
  staff PATCH `{"status": "active"}` when they pick up. `GET /calls?status=needs_person` lists the queue.
- Agent tool `transfer_to_staff(reason)` -> PATCHes the call and tells the agent to keep the line open.
  Used when the caller asks for a human, is upset, or wants something outside the other tools.
- Dashboard: the home "Live calls" strip shows needs_person calls first with an amber "Needs a person" banner
  (plus the reason); /calls and /calls/[id] show an amber badge. The call stays needs_person until hang-up;
  staff actually joining the room (staff token + agent hand-off) is not built.

## Auto hang-up (added 14:20) — the agent drops the line after goodbye
- Agent tool `end_call()` -> waits for the goodbye to finish playing, 2.5 s grace, then deletes the LiveKit
  room (`DeleteRoomRequest`). No backend write: the browser disconnect drives the normal shutdown path
  (summary, then PATCH status=ended), so the call is marked ended exactly once. Never used after a transfer.
