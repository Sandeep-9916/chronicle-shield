import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, BigInteger, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), nullable=False, index=True)
    evidence_seq = Column(Integer, nullable=False, default=1)
    file_name = Column(String(255), nullable=False)  # Sanitized original filename
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    storage_path = Column(String(500), nullable=False, unique=True)  # Random UUID path
    sha256_hash = Column(String(64), nullable=False, index=True)
    processing_status = Column(String(20), nullable=False, default="PENDING")  # PENDING, PROCESSING, COMPLETED, FAILED
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    case = relationship("Case", back_populates="evidence")
    chunks = relationship("Chunk", back_populates="evidence", cascade="all, delete-orphan", order_by="Chunk.line_number")
