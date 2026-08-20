from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(30), default="draft")
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    tax_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    fulfillment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Includes the customer's house/flat number appended, when given (see
    # ai_service._full_delivery_address) - a single complete address string.
    delivery_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # The house/flat number on its own too, for staff-facing structured
    # display (see email_service.send_internal_order_notification).
    delivery_flat_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Always False now that free-text/unverified address submission is
    # disabled (every address comes from a verified Nominatim
    # autocomplete selection or a previously-saved profile address) -
    # retained for schema/staff-tooling stability.
    delivery_unverified: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str | None] = mapped_column(String(60), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_birthday: Mapped[bool] = mapped_column(Boolean, default=False)
    upsell_shown: Mapped[bool] = mapped_column(Boolean, default=False)
    coupon_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    cart_reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
