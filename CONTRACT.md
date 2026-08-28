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

## Stretch (not built until core works)
- `POST /cases/{id}/transcript` body {role: "user"|"agent", text} -> 201
- `GET /cases/{id}/transcript` -> [{role, text, ts}]
- `WS /ws` -> server pushes {"type": "case.updated"|"transcript.appended", "case_id": ...} on every write

## Agent tools (LiveKit function tools, call backend via httpx)
- create_case(name, phone, issue_type, description) -> "Created case C-1001"
- lookup_case(phone) -> summary of most recent case for that phone, or "none found"
- add_note(case_id, note) -> appends line to notes

## Ports
backend :8000, dashboard :3000, agent = console process (no port)
