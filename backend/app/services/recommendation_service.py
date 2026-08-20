from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem

HOT_WEATHER_WORDS = {"hot", "summer", "heat", "sunny", "humid"}
COLD_WEATHER_WORDS = {"cold", "rain", "rainy", "winter", "chilly", "monsoon"}

TIME_OF_DAY_CATEGORIES = {
    "breakfast": {"Bakery", "Hot Beverages"},
    "afternoon": {"Snacks", "Cold Beverages"},
    "evening": {"Bakery", "Hot Beverages"},
}

REORDER_KEYWORDS = {
    "again", "usual", "last time", "previous order", "reorder",
    "same as before", "same as last time", "my order",
}

SHORTLIST_SIZE = 8


def time_bucket(now: datetime | None = None) -> str:
    hour = (now or datetime.now(timezone.utc)).hour
    if 7 <= hour < 11:
        return "breakfast"
    if 11 <= hour < 17:
        return "afternoon"
    return "evening"


def weather_bias_category(user_message: str) -> str | None:
    text = user_message.lower()
    if any(word in text for word in HOT_WEATHER_WORDS):
        return "Cold Beverages"
    if any(word in text for word in COLD_WEATHER_WORDS):
        return "Hot Beverages"
    return None


def _score(item: dict, bucket: str, weather_category: str | None) -> int:
    score = 0
    if item["category"] in TIME_OF_DAY_CATEGORIES.get(bucket, set()):
        score += 2
    if weather_category and item["category"] == weather_category:
        score += 3
    return score


def shortlist(
    candidates: list[dict],
    user_message: str,
    now: datetime | None = None,
    time_of_day_override: str | None = None,
) -> list[dict]:
    bucket = time_of_day_override or time_bucket(now)
    weather_category = weather_bias_category(user_message)
    ranked = sorted(candidates, key=lambda item: _score(item, bucket, weather_category), reverse=True)
    return ranked[:SHORTLIST_SIZE]


def combo_within_budget(items: list[dict], budget: float, max_items: int = 3) -> list[dict]:
    sorted_items = sorted(items, key=lambda item: item["price"])
    best_combo: list[dict] = []
    best_total = 0.0

    def _search(start: int, chosen: list[dict], total: float) -> None:
        nonlocal best_combo, best_total
        if len(chosen) >= 2 and total > best_total:
            best_combo, best_total = list(chosen), total
        if len(chosen) == max_items:
            return
        for i in range(start, len(sorted_items)):
            price = sorted_items[i]["price"]
            if total + price > budget:
                continue
            _search(i + 1, chosen + [sorted_items[i]], total + price)

    _search(0, [], 0.0)
    return best_combo


def mentions_previous_order(user_message: str) -> bool:
    text = user_message.lower()
    return any(keyword in text for keyword in REORDER_KEYWORDS)


async def get_previous_order_summary(db: AsyncSession, session_id: str) -> str | None:
    stmt = (
        select(MenuItem.name, OrderItem.quantity)
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.session_id == session_id, Order.status == "confirmed")
        .order_by(Order.created_at.desc())
        .limit(5)
    )
    result = await db.execute(stmt)
    rows = result.all()
    if not rows:
        return None

    items = ", ".join(f"{row.quantity}x {row.name}" for row in rows)
    return f"Customer's previous order included: {items}"
