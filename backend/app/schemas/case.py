from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class CaseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
