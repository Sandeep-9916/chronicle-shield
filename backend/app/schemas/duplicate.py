from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class DuplicateReviewRequest(BaseModel):
    action: str  # "confirm" | "dismiss"


class DuplicateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    duplicate_type: str  # exact_sha256, similar_image, similar_text
    primary_evidence_id: Optional[str] = None
    duplicate_evidence_id: Optional[str] = None
    primary_chunk_id: Optional[str] = None
    duplicate_chunk_id: Optional[str] = None
    similarity_score: float
    status: str  # pending, confirmed, dismissed
    created_at: datetime

    # Augmented fields for UI display
    primary_file_name: Optional[str] = None
    duplicate_file_name: Optional[str] = None
    primary_text: Optional[str] = None
    duplicate_text: Optional[str] = None


class DuplicateGroupResponse(BaseModel):
    case_id: str
    total_duplicates: int
    pending_count: int
    confirmed_count: int
    dismissed_count: int
    items: List[DuplicateResponse]
