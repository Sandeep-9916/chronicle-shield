from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: str
    seq: int
    user_id: Optional[str]
    action: str
    evidence_id: Optional[str]
    details: Dict[str, Any]
    previous_hash: str
    current_hash: str
    created_at: datetime


class VerificationResult(BaseModel):
    status: str  # "PASS" or "FAIL"
    chain_valid: bool
    files_valid: bool
    total_logs_checked: int
    total_files_checked: int
    broken_audit_entry_seq: Optional[int] = None
    broken_audit_entry_id: Optional[int] = None
    tampered_evidence_id: Optional[str] = None
    tampered_file_name: Optional[str] = None
    reason: Optional[str] = None
    timestamp: datetime
