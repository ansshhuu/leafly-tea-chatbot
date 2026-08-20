import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_profile import CustomerProfile
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem

_DIETARY_PATTERNS = [
    (re.compile(r"\bvegan\b", re.IGNORECASE), "vegan"),
    (re.compile(r"\bgluten[- ]?free\b", re.IGNORECASE), "gluten_free"),
    (re.compile(r"\bvegetarian\b|\bi'?m veg\b|\bveg only\b", re.IGNORECASE), "veg"),
]
_SEATING_PATTERNS = [
    (re.compile(r"\bwindow seat\b|\bby the window\b", re.IGNORECASE), "window seat"),
    (re.compile(r"\boutdoor\b|\bpatio\b|\bterrace\b", re.IGNORECASE), "outdoor"),
    (re.compile(r"\bindoor\b", re.IGNORECASE), "indoor"),
]
_FAVORITE_MIN_QUANTITY = 2


def detect_dietary_preference(text: str) -> str | None:
    for pattern, label in _DIETARY_PATTERNS:
        if pattern.search(text):
            return label
    return None


def detect_seating_preference(text: str) -> str | None:
    for pattern, label in _SEATING_PATTERNS:
        if pattern.search(text):
            return label
    return None


async def get_profile(db: AsyncSession, phone: str) -> CustomerProfile | None:
    stmt = select(CustomerProfile).where(CustomerProfile.phone == phone)
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_or_create_profile(db: AsyncSession, phone: str, name: str | None = None) -> CustomerProfile:
    profile = await get_profile(db, phone)
    if profile is not None:
        if name and not profile.name:
            profile.name = name
            await db.commit()
        return profile

    profile = CustomerProfile(phone=phone, name=name)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def remember_dietary_preference(db: AsyncSession, phone: str, preference: str) -> None:
    profile = await get_or_create_profile(db, phone)
    profile.dietary_preference = preference
    await db.commit()


async def remember_seating_preference(db: AsyncSession, phone: str, seating: str) -> None:
    profile = await get_or_create_profile(db, phone)
    profile.preferred_seating = seating
    await db.commit()


async def remember_delivery_address(db: AsyncSession, phone: str, address: str, lat: float, lon: float) -> None:
    profile = await get_or_create_profile(db, phone)
    profile.last_delivery_address = address
    profile.last_delivery_lat = lat
    profile.last_delivery_lon = lon
    await db.commit()


async def get_last_delivery_address(db: AsyncSession, phone: str | None) -> dict | None:
    """Returns {"address", "lat", "lon"} for a returning customer's saved
    delivery address, or None if there's no phone, no profile, or the
    profile has never completed a delivery order yet."""
    if not phone:
        return None
    profile = await get_profile(db, phone)
    if profile is None or profile.last_delivery_address is None:
        return None
    if profile.last_delivery_lat is None or profile.last_delivery_lon is None:
        return None
    return {
        "address": profile.last_delivery_address,
        "lat": profile.last_delivery_lat,
        "lon": profile.last_delivery_lon,
    }


async def get_favorite_item_name(db: AsyncSession, phone: str) -> str | None:
    stmt = (
        select(MenuItem.name, func.sum(OrderItem.quantity).label("total_qty"))
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.guest_phone == phone, Order.status == "confirmed")
        .group_by(MenuItem.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None or row.total_qty < _FAVORITE_MIN_QUANTITY:
        return None
    return row.name


async def build_welcome_back_message(db: AsyncSession, phone: str, session_name: str | None) -> str | None:
    favorite = await get_favorite_item_name(db, phone)
    if not favorite:
        return None

    profile = await get_profile(db, phone)
    name = session_name or (profile.name if profile else None)
    if name:
        return f"Welcome back, {name}! Good to see you again — last time you went for {favorite}."
    return f"Welcome back! Good to see you again — last time you went for {favorite}."
