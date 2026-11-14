from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ContradictionReviewRequest(BaseModel):
    action: str  # "resolve" | "dismiss"


class ContradictionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    rule_type: str  # time_conflict, metadata_mismatch, spatial_impossibility
    event_a_id: Optional[str] = None
    event_b_id: Optional[str] = None
    chunk_a_id: str
    chunk_b_id: str
    quote_a: str
    quote_b: str
    explanation: str
    quotes_verified: bool
    status: str  # flagged, resolved, dismissed
    created_at: datetime


class ContradictionListResponse(BaseModel):
    case_id: str
    total_contradictions: int
    flagged_count: int
    resolved_count: int
    dismissed_count: int
    items: List[ContradictionResponse]
