import os
from typing import Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.audit_log import AuditLog
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.demo_service import create_demo_case
from backend.app.services.storage import storage_service

router = APIRouter(prefix="/api/demo", tags=["demo"])

# Store backup of original evidence bytes before tamper for clean restoration
_tamper_backups: Dict[str, bytes] = {}


class TamperFileRequest(BaseModel):
    case_id: str
    evidence_id: Optional[str] = None


class TamperAuditRequest(BaseModel):
    case_id: str


@router.post("/load")
def load_demo_case(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a full fake workplace harassment case (chat, screenshots, audio, PDF)
    with 1 planted duplicate and 1 planted contradiction, and triggers the Process Everything pipeline.
    """
    demo_case = create_demo_case(user_id=current_user.id, db=db)
    return {
        "status": "success",
        "message": "Demo harassment investigation case loaded with planted duplicate and planted contradiction.",
        "case_id": demo_case.id,
        "title": demo_case.title,
    }


@router.post("/tamper-file")
def simulate_file_tamper(
    req: TamperFileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Simulates malicious tampering by flipping bytes in an evidence file's storage
    without updating the database SHA-256 hash or audit chain.
    """
    case = db.query(Case).filter(Case.id == req.case_id, Case.user_id == current_user.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    query = db.query(Evidence).filter(Evidence.case_id == case.id)
    if req.evidence_id:
        ev = query.filter(Evidence.id == req.evidence_id).first()
    else:
        ev = query.order_by(Evidence.evidence_seq.asc()).first()

    if not ev:
        raise HTTPException(status_code=404, detail="No evidence file found to tamper with")

    try:
        original_bytes = storage_service.download_file(ev.storage_path)
        _tamper_backups[ev.id] = original_bytes

        # Alter bytes by prepending malicious bytes directly to storage to simulate out-of-band attacker modification
        tampered_bytes = b"[MALICIOUS_TAMPERED_BYTE_INJECTION]" + original_bytes[35:]
        local_target = os.path.join(storage_service.local_dir, ev.storage_path.replace("/", os.sep))
        with open(local_target, "wb") as f:
            f.write(tampered_bytes)

        return {
            "status": "tampered",
            "message": f"Successfully tampered storage bytes of evidence E{ev.evidence_seq} ({ev.file_name}).",
            "evidence_id": ev.id,
            "evidence_seq": ev.evidence_seq,
            "file_name": ev.file_name,
            "original_sha256": ev.sha256_hash,
            "instruction": "Now click 'Verify Integrity' on the dashboard or Tamper page to observe immediate verification failure.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to tamper file: {str(e)}")


@router.post("/tamper-audit")
def simulate_audit_tamper(
    req: TamperAuditRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Simulates tampering with the audit log hash chain on an in-memory copy of the chain.
    Never modifies the real audit_log table in database, preserving PostgreSQL trigger
    immutability protections (Rule 3).
    """
    case = db.query(Case).filter(Case.id == req.case_id, Case.user_id == current_user.id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    audit_entries = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case.id)
        .order_by(AuditLog.seq.asc())
        .all()
    )
    if not audit_entries:
        raise HTTPException(status_code=404, detail="No audit log entries found to simulate tampering")

    # Clone entries to in-memory representation
    chain_copy = [
        {
            "id": e.id,
            "seq": e.seq,
            "case_id": e.case_id,
            "user_id": e.user_id,
            "action": e.action,
            "evidence_id": e.evidence_id,
            "previous_hash": e.previous_hash,
            "current_hash": e.current_hash,
            "created_at": e.created_at,
        }
        for e in audit_entries
    ]

    # Select entry to alter (entry #2 if available, else entry #1)
    target_idx = 1 if len(chain_copy) > 1 else 0
    target_seq = chain_copy[target_idx]["seq"]
    original_prev_hash = chain_copy[target_idx]["previous_hash"]
    corrupted_hash = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

    # Corrupt in-memory previous_hash
    chain_copy[target_idx]["previous_hash"] = corrupted_hash

    # Run cryptographic verifier on this altered in-memory chain
    from backend.app.services.audit import verify_audit_entries
    chain_valid, total_checked, broken_seq, fail_reason = verify_audit_entries(chain_copy)

    return {
        "status": "tampered",
        "simulation": True,
        "chain_valid": chain_valid,
        "broken_audit_entry_seq": broken_seq,
        "corrupted_block_seq": target_seq,
        "expected_hash": original_prev_hash,
        "corrupted_hash": corrupted_hash,
        "total_logs_checked": total_checked,
        "reason": fail_reason,
        "message": f"Simulated audit chain tampering on in-memory chain. Verifier successfully flagged broken block seq #{broken_seq}.",
        "db_immutable": True,
        "db_protection_note": "Real database table audit_log was not modified, respecting PostgreSQL UPDATE/DELETE trigger.",
    }


@router.post("/restore")
def restore_demo_case(
    req: TamperFileRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restores any tampered evidence files from backup."""
    restored_count = 0
    for ev_id, original_bytes in list(_tamper_backups.items()):
        ev = db.query(Evidence).filter(Evidence.id == ev_id).first()
        if ev:
            local_target = os.path.join(storage_service.local_dir, ev.storage_path.replace("/", os.sep))
            with open(local_target, "wb") as f:
                f.write(original_bytes)
            restored_count += 1
            del _tamper_backups[ev_id]

    return {
        "status": "restored",
        "restored_files_count": restored_count,
        "message": "All tampered evidence file storage bytes have been restored to their authentic original state.",
    }
