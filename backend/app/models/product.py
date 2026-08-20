from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Base price for the smaller (100g) size - hampers store their single
    # bundle price here too, with size_options left empty.
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    origin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tea_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    caffeine_level: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # e.g. [{"size": "100g", "price": 699.0}, {"size": "250g", "price": 1599.0}]
    size_options: Mapped[list[dict]] = mapped_column(JSON, default=list)
    badge: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_hamper: Mapped[bool] = mapped_column(Boolean, default=False)
    hamper_contents: Mapped[list[str]] = mapped_column(JSON, default=list)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
