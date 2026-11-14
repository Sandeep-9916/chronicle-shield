import json
import hashlib
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, UniqueConstraint, JSON, event
from sqlalchemy.orm import relationship
from backend.app.database import Base


def format_canonical_timestamp(dt: datetime) -> str:
    """
    Standardizes UTC ISO-8601 timestamp string ending with 'Z' and microsecond precision.
    Guarantees cross-database consistency between SQLite and PostgreSQL.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer().with_variant(BigInteger, "postgresql"), primary_key=True, autoincrement=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(BigInteger, nullable=False)
    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(50), nullable=False)
    evidence_id = Column(String(36), ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True)
    details = Column(JSON, nullable=False, default=dict)
    previous_hash = Column(String(64), nullable=False)
    current_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("case_id", "seq", name="uq_audit_log_case_seq"),
    )

    case = relationship("Case", back_populates="audit_logs")


# Enforce DB immutability at the ORM layer
@event.listens_for(AuditLog, "before_update")
def block_audit_log_update(mapper, connection, target):
    raise PermissionError("Chronicle Shield security violation: audit_log is append-only and cannot be updated.")


@event.listens_for(AuditLog, "before_delete")
def block_audit_log_delete(mapper, connection, target):
    raise PermissionError("Chronicle Shield security violation: audit_log is append-only and cannot be deleted.")


def compute_canonical_hash(
    seq: int,
    case_id: str,
    user_id: str | None,
    action: str,
    evidence_id: str | None,
    timestamp_iso: str,
    previous_hash: str
) -> str:
    """
    Computes SHA-256 over a canonical, fixed-order JSON of:
    seq, case_id, user_id, action, evidence_id, timestamp (UTC), previous_hash.
    """
    payload = {
        "action": str(action),
        "case_id": str(case_id),
        "evidence_id": str(evidence_id) if evidence_id else None,
        "previous_hash": str(previous_hash),
        "seq": int(seq),
        "timestamp": str(timestamp_iso),
        "user_id": str(user_id) if user_id else None,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
