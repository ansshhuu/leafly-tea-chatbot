import asyncio

from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.models.menu_item import MenuItem
from app.services import order_service, session_context_service


async def _seed_menu(db_session):
    item = MenuItem(name="Samosa", price=60, category="Snacks", available=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _post_cart_reminder(db_session, session_id: str):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/email/cart-reminder", json={"session_id": session_id})
    finally:
        app.dependency_overrides.clear()


async def test_cart_reminder_skips_when_no_email_known(db_session):
    item = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "cart-session-1")
    await order_service.add_item(db_session, order.id, item.id, 1)

    response = await _post_cart_reminder(db_session, "cart-session-1")

    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is False
    assert body["reason"] == "no_email_known"


async def test_cart_reminder_skips_when_cart_is_empty(db_session):
    await session_context_service.remember_email(db_session, "cart-session-2", "anshu@example.com")

    response = await _post_cart_reminder(db_session, "cart-session-2")

    assert response.status_code == 200
    body = response.json()
    assert body["sent"] is False
    assert body["reason"] == "no_active_cart"


async def test_cart_reminder_sends_once_then_skips_on_repeat_call(db_session, monkeypatch):
    from unittest.mock import AsyncMock

    from app.services import email_service

    fake_send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_cart_abandonment", fake_send)

    item = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "cart-session-3")
    await order_service.add_item(db_session, order.id, item.id, 2)
    await session_context_service.remember_email(db_session, "cart-session-3", "anshu@example.com")

    first = await _post_cart_reminder(db_session, "cart-session-3")
    await asyncio.sleep(0)
    assert first.status_code == 200
    assert first.json() == {"sent": True, "reason": None}
    fake_send.assert_awaited_once()

    second = await _post_cart_reminder(db_session, "cart-session-3")
    assert second.status_code == 200
    assert second.json() == {"sent": False, "reason": "already_sent"}
    fake_send.assert_awaited_once()
