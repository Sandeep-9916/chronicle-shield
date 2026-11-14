from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.app.models.audit_log import AuditLog, compute_canonical_hash, format_canonical_timestamp

GENESIS_HASH = "0" * 64


def log_action(
    db: Session,
    case_id: str,
    action: str,
    user_id: str | None = None,
    evidence_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    """
    Appends a new hash-chained audit log entry for a specific case.
    Strictly guarantees:
    1. Sequential sequence numbers per case (seq = max(seq) + 1).
    2. previous_hash incorporates the immediate preceding entry's current_hash (or GENESIS_HASH).
    3. current_hash is computed over canonical JSON:
       (seq, case_id, user_id, action, evidence_id, timestamp, previous_hash).
    """
    # Fetch last audit entry for this case
    last_entry = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(desc(AuditLog.seq))
        .first()
    )

    if last_entry is None:
        seq = 1
        previous_hash = GENESIS_HASH
    else:
        seq = last_entry.seq + 1
        previous_hash = last_entry.current_hash

    # Standardize UTC timestamp
    timestamp = datetime.now(timezone.utc)
    timestamp_iso = format_canonical_timestamp(timestamp)

    current_hash = compute_canonical_hash(
        seq=seq,
        case_id=case_id,
        user_id=user_id,
        action=action,
        evidence_id=evidence_id,
        timestamp_iso=timestamp_iso,
        previous_hash=previous_hash,
    )

    entry = AuditLog(
        case_id=case_id,
        seq=seq,
        user_id=user_id,
        action=action,
        evidence_id=evidence_id,
        details=details or {},
        previous_hash=previous_hash,
        current_hash=current_hash,
        created_at=timestamp,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
