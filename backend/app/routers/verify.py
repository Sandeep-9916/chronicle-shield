from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.models.case import Case
from backend.app.models.evidence import Evidence
from backend.app.models.audit_log import AuditLog, compute_canonical_hash, format_canonical_timestamp
from backend.app.schemas.audit import VerificationResult
from backend.app.auth.security import get_current_user, CurrentUser
from backend.app.services.validator import compute_sha256
from backend.app.services.storage import storage_service
from backend.app.services.audit import GENESIS_HASH

router = APIRouter(prefix="/api/cases/{case_id}/verify", tags=["verify"])


@router.get("", response_model=VerificationResult)
def verify_case_integrity(
    case_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verification Endpoint (Module 1):
    1. Recomputes the entire audit log hash chain for the case from sequence 1.
    2. Re-checks all stored evidence files in private storage against recorded SHA-256 hashes.
    3. Returns PASS/FAIL, pinpointing the exact broken sequence/entry or tampered file.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if case.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this case")

    # 1. Audit Chain Verification
    audit_logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.seq.asc())
        .all()
    )

    expected_seq = 1
    expected_prev_hash = GENESIS_HASH
    chain_valid = True
    broken_seq = None
    broken_id = None
    fail_reason = None

    for entry in audit_logs:
        # Check sequence continuity
        if entry.seq != expected_seq:
            chain_valid = False
            broken_seq = entry.seq
            broken_id = entry.id
            fail_reason = f"Audit log sequence break: expected seq {expected_seq}, found {entry.seq}"
            break

        # Check previous hash link
        if entry.previous_hash != expected_prev_hash:
            chain_valid = False
            broken_seq = entry.seq
            broken_id = entry.id
            fail_reason = f"Audit log previous_hash mismatch at seq {entry.seq}"
            break

        # Recompute canonical hash with normalized timestamp
        timestamp_iso = format_canonical_timestamp(entry.created_at)
        recalculated_hash = compute_canonical_hash(
            seq=entry.seq,
            case_id=entry.case_id,
            user_id=entry.user_id,
            action=entry.action,
            evidence_id=entry.evidence_id,
            timestamp_iso=timestamp_iso,
            previous_hash=entry.previous_hash,
        )

        if recalculated_hash != entry.current_hash:
            chain_valid = False
            broken_seq = entry.seq
            broken_id = entry.id
            fail_reason = f"Audit log hash mismatch at seq {entry.seq}. Payload was modified."
            break

        expected_prev_hash = entry.current_hash
        expected_seq += 1

    # 2. File Hashes Verification in Private Storage
    evidence_list = db.query(Evidence).filter(Evidence.case_id == case_id).all()
    files_valid = True
    tampered_evidence_id = None
    tampered_file_name = None

    if chain_valid:
        for ev in evidence_list:
            try:
                content = storage_service.download_file(ev.storage_path)
                calculated_hash = compute_sha256(content)
                if calculated_hash != ev.sha256_hash:
                    files_valid = False
                    tampered_evidence_id = ev.id
                    tampered_file_name = ev.file_name
                    fail_reason = f"Stored file content changed! Expected hash {ev.sha256_hash}, calculated {calculated_hash} for {ev.file_name}"
                    break
            except Exception as e:
                files_valid = False
                tampered_evidence_id = ev.id
                tampered_file_name = ev.file_name
                fail_reason = f"Failed to retrieve stored file '{ev.file_name}': {str(e)}"
                break

    is_overall_pass = chain_valid and files_valid

    return VerificationResult(
        status="PASS" if is_overall_pass else "FAIL",
        chain_valid=chain_valid,
        files_valid=files_valid,
        total_logs_checked=len(audit_logs),
        total_files_checked=len(evidence_list),
        broken_audit_entry_seq=broken_seq,
        broken_audit_entry_id=broken_id,
        tampered_evidence_id=tampered_evidence_id,
        tampered_file_name=tampered_file_name,
        reason=fail_reason,
        timestamp=datetime.now(timezone.utc),
    )
