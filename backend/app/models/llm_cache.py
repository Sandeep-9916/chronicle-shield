from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON
from backend.app.database import Base


class LLMCache(Base):
    __tablename__ = "llm_cache"

    prompt_hash = Column(String(64), primary_key=True)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    response_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
