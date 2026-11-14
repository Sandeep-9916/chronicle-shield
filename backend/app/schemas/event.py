from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    evidence_id: Optional[str] = None
    chunk_id: Optional[str] = None
    event: str
    who: str
    to_whom: str
    date: str
    date_iso: Optional[datetime] = None
    quote: str
    status: str  # verified, needs_review, or rejected
    verification_source: str = "machine_verified"  # machine_verified, human_approved, user_edited
    original_event_data: Optional[dict] = None
    user_reviewed: bool = False
    verification_notes: Optional[str] = None
    created_at: datetime


class EventReviewRequest(BaseModel):
    action: str  # "approve", "reject", or "edit"
    event: Optional[str] = None
    who: Optional[str] = None
    to_whom: Optional[str] = None
    date: Optional[str] = None
    quote: Optional[str] = None


class MergedEventsResponse(BaseModel):
    case_id: str
    total_events: int
    grouped_by_day: dict[str, dict[str, list[EventResponse]]]
    undated: list[EventResponse]


class ExtractionStatusResponse(BaseModel):
    case_id: str
    status: str  # idle, in_progress, completed, failed
    progress: str
    total: int
    error: Optional[str] = None
