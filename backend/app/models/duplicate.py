import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index
from backend.app.database import Base


class EvidenceDuplicate(Base):
    __tablename__ = "evidence_duplicates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    duplicate_type = Column(String(50), nullable=False)  # exact_sha256, similar_image, similar_text
    primary_evidence_id = Column(String(36), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=True)
    duplicate_evidence_id = Column(String(36), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=True)
    primary_chunk_id = Column(String(100), nullable=True)
    duplicate_chunk_id = Column(String(100), nullable=True)
    similarity_score = Column(Float, nullable=False, default=1.0)
    status = Column(String(50), nullable=False, default="pending", index=True)  # pending, confirmed, dismissed
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_evidence_dup_case_status", "case_id", "status"),
    )
