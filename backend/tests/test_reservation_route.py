from httpx import ASGITransport, AsyncClient

from app.db.session import get_db
from app.main import app


async def test_reservation_action_creates_reservation_with_explicit_date_time(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/reservation/action",
                json={"date": "2099-06-15", "time": "19:00:00", "guests": 4, "special_requests": "birthday"},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["available"] is True
            reservation_id = body["reservation"]["id"]

            get_response = await client.get(f"/api/reservation/{reservation_id}")
    finally:
        app.dependency_overrides.clear()

    assert get_response.status_code == 200
    assert get_response.json()["guests"] == 4


async def test_reservation_action_resolves_date_phrase(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/reservation/action",
                json={"date_phrase": "tomorrow", "time_phrase": "7pm", "guests": 2},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["available"] is True


async def test_reservation_action_unparseable_phrase_returns_422(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/reservation/action",
                json={"date_phrase": "blah blah", "time_phrase": "whenever", "guests": 2},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


async def test_reservation_get_404_for_missing_reservation(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/reservation/999999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
