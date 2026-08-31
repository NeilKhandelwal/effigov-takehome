from typing import Literal

from pydantic import BaseModel

IssueType = Literal["missed_pickup", "pothole", "streetlight", "water", "animal", "other"]
Status = Literal["open", "in_progress", "resolved"]
CallStatus = Literal["active", "needs_person", "ended"]
Role = Literal["user", "agent"]
LinkHow = Literal["created", "looked_up"]


class CaseCreate(BaseModel):
    name: str
    phone: str
    issue_type: IssueType | None = None
    description: str


class CaseUpdate(BaseModel):
    status: Status | None = None
    issue_type: IssueType | None = None
    description: str | None = None


class Case(BaseModel):
    id: str
    name: str
    phone: str
    issue_type: IssueType | None
    description: str
    status: Status
    notes: str  # derived: every field="note" event on the case, oldest first, joined by "\n"
    created_at: str
    updated_at: str


class CaseCreated(Case):
    # the only response that carries the code: after this it is write-only, compared but never shown
    lookup_code: str


class CallCreate(BaseModel):
    room: str | None = None


class CallUpdate(BaseModel):
    status: CallStatus | None = None
    case_id: str | None = None
    summary: str | None = None
    transfer_reason: str | None = None


class CallCaseLink(BaseModel):
    case_id: str
    how: LinkHow = "created"


class Call(BaseModel):
    id: str
    case_id: str | None  # the case being worked right now; case_ids is every case this call touched
    case_ids: list[str] = []
    status: CallStatus
    started_at: str
    ended_at: str | None
    updated_at: str  # bumped on every write to the call; what GET /calls?since= compares
    room: str | None
    summary: str | None
    transfer_reason: str | None


class TranscriptCreate(BaseModel):
    role: Role
    text: str


class TranscriptLine(BaseModel):
    id: int
    call_id: str
    role: Role
    text: str
    ts: str


class CallDetail(Call):
    transcript: list[TranscriptLine]


class CaseEvent(BaseModel):
    id: int
    case_id: str
    field: str
    old_value: str | None
    new_value: str | None
    source: str
    ts: str
