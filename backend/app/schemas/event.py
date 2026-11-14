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
    status: str  # verified or needs_review
    verification_notes: Optional[str] = None
    created_at: datetime


class ExtractionStatusResponse(BaseModel):
    case_id: str
    status: str  # idle, in_progress, completed, failed
    progress: str
    total: int
    error: Optional[str] = None
