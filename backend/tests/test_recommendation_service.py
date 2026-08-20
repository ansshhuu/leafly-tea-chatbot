from datetime import datetime, timezone

from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.services import recommendation_service as rec


def test_time_bucket_boundaries():
    assert rec.time_bucket(datetime(2026, 1, 1, 8, tzinfo=timezone.utc)) == "breakfast"
    assert rec.time_bucket(datetime(2026, 1, 1, 13, tzinfo=timezone.utc)) == "afternoon"
    assert rec.time_bucket(datetime(2026, 1, 1, 20, tzinfo=timezone.utc)) == "evening"
    assert rec.time_bucket(datetime(2026, 1, 1, 3, tzinfo=timezone.utc)) == "evening"


def test_weather_bias_category_from_keywords():
    assert rec.weather_bias_category("it's so hot today") == "Cold Beverages"
    assert rec.weather_bias_category("it's raining and cold") == "Hot Beverages"
    assert rec.weather_bias_category("nothing special") is None


def test_shortlist_ranks_time_and_weather_matches_first():
    candidates = [
        {"name": "Iced Latte", "price": 150, "category": "Cold Beverages", "tags": [], "spice_level": 0},
        {"name": "Butter Croissant", "price": 120, "category": "Bakery", "tags": [], "spice_level": 0},
        {"name": "Vada Pav", "price": 70, "category": "Snacks", "tags": [], "spice_level": 2},
    ]

    morning = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    ranked = rec.shortlist(candidates, "good morning", now=morning)
    assert ranked[0]["name"] == "Butter Croissant"

    hot_afternoon = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
    ranked_hot = rec.shortlist(candidates, "it's really hot outside", now=hot_afternoon)
    assert ranked_hot[0]["name"] == "Iced Latte"


def test_shortlist_time_of_day_override_beats_server_clock():
    candidates = [
        {"name": "Iced Latte", "price": 150, "category": "Cold Beverages", "tags": [], "spice_level": 0},
        {"name": "Butter Croissant", "price": 120, "category": "Bakery", "tags": [], "spice_level": 0},
    ]

    afternoon = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
    ranked = rec.shortlist(candidates, "something to eat", now=afternoon, time_of_day_override="breakfast")

    assert ranked[0]["name"] == "Butter Croissant"


def test_combo_within_budget_stays_under_budget_and_picks_at_least_two_items():
    items = [
        {"name": "Cutting Chai", "price": 50},
        {"name": "Samosa", "price": 60},
        {"name": "Cold Brew", "price": 160},
    ]

    combo = rec.combo_within_budget(items, budget=120)

    assert len(combo) >= 2
    assert sum(item["price"] for item in combo) <= 120


def test_combo_within_budget_returns_empty_when_nothing_fits():
    items = [{"name": "Cold Brew", "price": 160}]
    combo = rec.combo_within_budget(items, budget=100)
    assert combo == []


def test_mentions_previous_order_keyword_gate():
    assert rec.mentions_previous_order("same as last time please")
    assert rec.mentions_previous_order("I'll have my usual")
    assert not rec.mentions_previous_order("what's on the menu")


async def test_get_previous_order_summary_returns_none_without_orders(db_session):
    summary = await rec.get_previous_order_summary(db_session, session_id="session-no-orders")

    assert summary is None


async def test_get_previous_order_summary_lists_recent_items(db_session):
    db_session.add(MenuItem(id=1, name="Masala Chai", price=80, category="Hot Beverages"))
    await db_session.flush()
    order = Order(session_id="session-with-order", status="confirmed")
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order.id, menu_item_id=1, quantity=2, price_at_order=80))
    await db_session.commit()

    summary = await rec.get_previous_order_summary(db_session, session_id="session-with-order")

    assert summary == "Customer's previous order included: 2x Masala Chai"


async def test_get_previous_order_summary_never_leaks_across_sessions(db_session):
    db_session.add(MenuItem(id=1, name="Masala Chai", price=80, category="Hot Beverages"))
    await db_session.flush()
    order = Order(session_id="session-owner", status="confirmed")
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order.id, menu_item_id=1, quantity=2, price_at_order=80))
    await db_session.commit()

    summary = await rec.get_previous_order_summary(db_session, session_id="session-stranger")

    assert summary is None


async def test_get_previous_order_summary_ignores_unconfirmed_draft_carts(db_session):
    db_session.add(MenuItem(id=1, name="Masala Chai", price=80, category="Hot Beverages"))
    await db_session.flush()
    order = Order(session_id="session-draft-only", status="draft")
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order.id, menu_item_id=1, quantity=2, price_at_order=80))
    await db_session.commit()

    summary = await rec.get_previous_order_summary(db_session, session_id="session-draft-only")

    assert summary is None
