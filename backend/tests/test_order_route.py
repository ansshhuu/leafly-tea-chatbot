from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app
from app.models.menu_item import MenuItem


async def _seed_menu(db_session):
    item = MenuItem(name="Samosa", price=60, category="Snacks", available=True)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def test_order_action_add_then_summary_roundtrip(db_session):
    item = await _seed_menu(db_session)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            add_response = await client.post(
                "/api/order/action",
                json={"session_id": "route-session-1", "action": "add", "menu_item_id": item.id, "quantity": 2},
            )
            assert add_response.status_code == 200
            body = add_response.json()
            assert body["summary"]["subtotal"] == 120.0
            assert body["summary"]["total"] == 126.0

            order_id = body["summary"]["order_id"]
            summary_response = await client.get(f"/api/order/{order_id}/summary")
    finally:
        app.dependency_overrides.clear()

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["items"][0]["name"] == "Samosa"
    assert summary["items"][0]["quantity"] == 2


async def test_order_action_resolves_item_name_fuzzily(db_session):
    item = await _seed_menu(db_session)

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/order/action",
                json={"session_id": "route-session-2", "action": "add", "item_name": "samosas", "quantity": 1},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"]["items"][0]["menu_item_id"] == item.id


async def test_order_summary_404_for_missing_order(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/order/999999/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
