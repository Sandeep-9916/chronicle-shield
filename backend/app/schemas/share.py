from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ShareLinkCreate(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=720, description="Expiration in hours (1-720)")


class ShareLinkResponse(BaseModel):
    id: str
    case_id: str
    token: str
    share_url: str
    expires_at: datetime
    is_revoked: bool
    revoked_at: Optional[datetime] = None
    access_count: int
    last_accessed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicEvidenceItem(BaseModel):
    id: str
    evidence_seq: int
    file_name: str
    file_size: int
    mime_type: str
    sha256_hash: str
    hash_verified: bool
    created_at: datetime


class PublicSharedCaseResponse(BaseModel):
    case_id: str
    title: str
    description: Optional[str] = None
    token: str
    expires_at: datetime
    access_count: int
    integrity_status: str  # "VERIFIED" or "COMPROMISED"
    audit_chain_verified: bool
    audit_blocks_count: int
    summary: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = []
    contradictions: List[Dict[str, Any]] = []
    evidence: List[PublicEvidenceItem] = []
