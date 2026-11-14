from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    version: int
    status: str  # "active" or "outdated"
    summary_text: str
    citations: List[str] = Field(default_factory=list)
    removed_sentences: List[Dict[str, str]] = Field(default_factory=list)
    summary_metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SummaryStatusResponse(BaseModel):
    case_id: str
    status: str  # "idle" | "in_progress" | "completed" | "failed"
    progress: str
    error: Optional[str] = None
