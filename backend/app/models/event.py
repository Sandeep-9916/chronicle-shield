import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from backend.app.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_id = Column(String(36), ForeignKey("evidence.id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_id = Column(String(50), nullable=True)  # e.g. E3-p2-L5
    event = Column(Text, nullable=False)
    who = Column(String(255), nullable=False)
    to_whom = Column(String(255), nullable=False)
    date = Column(String(100), nullable=False)
    date_iso = Column(DateTime(timezone=True), nullable=True)  # Normalized ISO-8601 UTC timestamp
    quote = Column(Text, nullable=False)
    status = Column(String(50), nullable=False, default="verified")  # verified, needs_review, or rejected
    verification_source = Column(String(50), nullable=False, default="machine_verified")  # machine_verified, human_approved, user_edited
    original_event_data = Column(JSON, nullable=True)  # Preserves original AI output when edited
    user_reviewed = Column(Boolean, nullable=False, default=False)
    verification_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    case = relationship("Case", back_populates="events")


# Add events relationship to Case
from backend.app.models.case import Case
Case.events = relationship("Event", back_populates="case", cascade="all, delete-orphan")
