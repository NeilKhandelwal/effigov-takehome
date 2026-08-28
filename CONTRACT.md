# API contract (fixed 13:00 — all three lanes build against this)

Backend on http://localhost:8000. JSON everywhere. Errors: 404 {"detail": "..."}, 422 on bad body.

## Case
```json
{
  "id": "C-1001",              // string, "C-" + 4-digit autoincrement starting 1001; agent reads it aloud
  "name": "Maria Lopez",
  "phone": "5551234567",       // digits only, stored as given after stripping non-digits
  "issue_type": "missed_pickup", // one of: missed_pickup | pothole | streetlight | water | animal | other
  "description": "Trash not collected on Elm St Tuesday",
  "status": "open",            // open | in_progress | resolved
  "notes": "",                 // free text, appended to by agent/staff
  "created_at": "2026-08-28T20:01:02Z",
  "updated_at": "2026-08-28T20:01:02Z"
}
```

## Endpoints
- `POST /cases` body {name, phone, issue_type, description} -> 201 Case (status=open, notes="")
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

## Audit (added 13:20)
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
- create_case(name, phone, issue_type, description) -> "Created case C-1001"
- lookup_case(phone) -> summary of most recent case for that phone, or "none found"
- add_note(case_id, note) -> appends line to notes

## Ports
backend :8000, dashboard :3000, agent = console process (no port)
