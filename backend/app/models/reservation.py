from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    date: Mapped[date] = mapped_column(Date, nullable=False)
    time: Mapped[time] = mapped_column(Time, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, default=1)
    special_requests: Mapped[str | None] = mapped_column(String(500), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_birthday: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    location: Mapped[str | None] = mapped_column(String(60), nullable=True)
