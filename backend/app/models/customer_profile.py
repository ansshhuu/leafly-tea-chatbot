from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CustomerProfile(Base):

    __tablename__ = "customer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)

    dietary_preference: Mapped[str | None] = mapped_column(String(30), nullable=True)
    preferred_seating: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Last confirmed delivery address, offered back on future orders ("Deliver
    # to your last address?") - see customer_profile_service.remember_delivery_address.
    # lat/lon are stored alongside so a reuse never needs re-geocoding.
    last_delivery_address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_delivery_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_delivery_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
