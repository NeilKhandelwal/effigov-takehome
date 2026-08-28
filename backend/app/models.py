from typing import Literal

from pydantic import BaseModel

IssueType = Literal["missed_pickup", "pothole", "streetlight", "water", "animal", "other"]
Status = Literal["open", "in_progress", "resolved"]
CallStatus = Literal["active", "ended"]
Role = Literal["user", "agent"]


class CaseCreate(BaseModel):
    name: str
    phone: str
    issue_type: IssueType
    description: str


class CaseUpdate(BaseModel):
    status: Status | None = None
    notes: str | None = None
    issue_type: IssueType | None = None
    description: str | None = None


class Case(BaseModel):
    id: str
    name: str
    phone: str
    issue_type: IssueType
    description: str
    status: Status
    notes: str
    created_at: str
    updated_at: str


class CallCreate(BaseModel):
    room: str | None = None


class CallUpdate(BaseModel):
    status: CallStatus | None = None
    case_id: str | None = None


class Call(BaseModel):
    id: str
    case_id: str | None
    status: CallStatus
    started_at: str
    ended_at: str | None
    room: str | None


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
