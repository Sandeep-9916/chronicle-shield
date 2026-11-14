import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from backend.app.database import Base


class CaseSummary(Base):
    __tablename__ = "case_summaries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="active")  # active or outdated
    summary_text = Column(Text, nullable=False)
    citations = Column(JSON, nullable=False, default=list)  # list of cited chunk IDs
    removed_sentences = Column(JSON, nullable=False, default=list)  # dropped uncorroborated sentences + reasons
    summary_metadata = Column(JSON, nullable=False, default=dict)  # counts of machine_verified, human_approved, user_edited
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    case = relationship("Case", back_populates="summaries")


# Add relationship to Case
from backend.app.models.case import Case
Case.summaries = relationship("CaseSummary", back_populates="case", cascade="all, delete-orphan")
