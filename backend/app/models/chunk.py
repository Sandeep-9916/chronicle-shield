import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_id = Column(String(36), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String(50), nullable=False, index=True)  # e.g. E3-p2-L5
    text = Column(Text, nullable=False)
    page_or_segment = Column(String(50), nullable=True)  # p1, p2, or s00:01:23-00:01:45
    line_number = Column(Integer, nullable=False)
    sender = Column(String(255), nullable=True)
    timestamp_str = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=False)  # 0.0 to 100.0
    ocr_engine = Column(String(50), nullable=False)  # tesseract, rapidocr, pymupdf_native, faster_whisper, chat_parser
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    evidence = relationship("Evidence", back_populates="chunks")
