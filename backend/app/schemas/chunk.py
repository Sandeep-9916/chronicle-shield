from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    evidence_id: str
    chunk_id: str
    text: str
    page_or_segment: Optional[str] = None
    line_number: int
    sender: Optional[str] = None
    timestamp_str: Optional[str] = None
    confidence: float
    ocr_engine: str
    created_at: datetime
