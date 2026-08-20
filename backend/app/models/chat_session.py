from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    known_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    known_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    known_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
