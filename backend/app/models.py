from typing import Literal

from pydantic import BaseModel

IssueType = Literal["missed_pickup", "pothole", "streetlight", "water", "animal", "other"]
Status = Literal["open", "in_progress", "resolved"]


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
