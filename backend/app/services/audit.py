from typing import Any
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


def verify_audit_entries(
    entries: list[Any],
) -> tuple[bool, int, int | None, str | None]:
    """
    Verifies cryptographic hash chain continuity over any list of audit log objects or dicts.
    Returns: (is_valid: bool, total_checked: int, broken_seq: Optional[int], fail_reason: Optional[str])
    """
    expected_seq = 1
    expected_prev_hash = GENESIS_HASH

    for entry in entries:
        seq = entry.seq if hasattr(entry, "seq") else entry["seq"]
        prev_hash = entry.previous_hash if hasattr(entry, "previous_hash") else entry["previous_hash"]
        curr_hash = entry.current_hash if hasattr(entry, "current_hash") else entry["current_hash"]
        case_id = entry.case_id if hasattr(entry, "case_id") else entry["case_id"]
        user_id = entry.user_id if hasattr(entry, "user_id") else entry.get("user_id")
        action = entry.action if hasattr(entry, "action") else entry["action"]
        evidence_id = entry.evidence_id if hasattr(entry, "evidence_id") else entry.get("evidence_id")
        created_at = entry.created_at if hasattr(entry, "created_at") else entry["created_at"]

        if seq != expected_seq:
            return False, len(entries), seq, f"Audit log sequence break: expected seq {expected_seq}, found {seq}"

        if prev_hash != expected_prev_hash:
            return False, len(entries), seq, f"Audit log previous_hash mismatch at seq {seq}"

        timestamp_iso = format_canonical_timestamp(created_at)
        recalculated_hash = compute_canonical_hash(
            seq=seq,
            case_id=case_id,
            user_id=user_id,
            action=action,
            evidence_id=evidence_id,
            timestamp_iso=timestamp_iso,
            previous_hash=prev_hash,
        )

        if recalculated_hash != curr_hash:
            return False, len(entries), seq, f"Audit log hash mismatch at seq {seq}. Payload was modified."

        expected_prev_hash = curr_hash
        expected_seq += 1

    return True, len(entries), None, None


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
    is_valid, total, broken_seq, reason = verify_audit_entries(audit_logs)
    return is_valid, total, reason

