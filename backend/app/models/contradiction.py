import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Index
from backend.app.database import Base


class CaseContradiction(Base):
    __tablename__ = "case_contradictions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_type = Column(String(50), nullable=False)  # time_conflict, metadata_mismatch, spatial_impossibility
    event_a_id = Column(String(36), ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    event_b_id = Column(String(36), ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    chunk_a_id = Column(String(100), nullable=False)
    chunk_b_id = Column(String(100), nullable=False)
    quote_a = Column(Text, nullable=False)
    quote_b = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    quotes_verified = Column(Boolean, nullable=False, default=True)
    status = Column(String(50), nullable=False, default="flagged", index=True)  # flagged, resolved, dismissed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_case_contra_case_status", "case_id", "status"),
    )
