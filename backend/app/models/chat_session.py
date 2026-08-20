from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    known_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    known_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    known_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reservation_draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    checkout_draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feedback_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_addon_item_id: Mapped[int | None] = mapped_column(nullable=True)
    pending_addon_item_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pending_addon_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
