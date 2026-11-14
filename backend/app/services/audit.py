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


def verify_case_chain(case_id: str, db: Session) -> tuple[bool, int, str | None]:
    """
    Verifies cryptographic hash chain continuity for a case.
    Returns: (is_valid, blocks_count, fail_reason)
    """
    audit_logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.seq.asc())
        .all()
    )

    expected_seq = 1
    expected_prev_hash = GENESIS_HASH

    for entry in audit_logs:
        if entry.seq != expected_seq:
            return False, len(audit_logs), f"Audit sequence break: expected {expected_seq}, found {entry.seq}"

        if entry.previous_hash != expected_prev_hash:
            return False, len(audit_logs), f"Audit previous_hash mismatch at seq {entry.seq}"

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
            return False, len(audit_logs), f"Audit hash corrupted at seq {entry.seq}"

        expected_prev_hash = entry.current_hash
        expected_seq += 1

    return True, len(audit_logs), None

