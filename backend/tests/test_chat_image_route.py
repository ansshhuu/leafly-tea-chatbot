from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.api.routes import chat as chat_route
from app.db.session import get_db
from app.main import app

FAKE_RESULT = {
    "reply_text": "That looks like a chocolate muffin! This looks similar to what we have here: Chocolate Muffin (Rs.110).",
    "intent": "menu_search",
    "sentiment": "neutral",
    "language": "en",
}


async def test_chat_image_endpoint_returns_reply(db_session, monkeypatch):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(chat_route, "analyze_menu_image", AsyncMock(return_value=FAKE_RESULT))

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"image": ("photo.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")}
            data = {"session_id": "img-route-1", "message": "is this on the menu?"}
            response = await client.post("/api/chat/image", data=data, files=files)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "Chocolate Muffin" in body["reply"]
    assert body["intent"] == "menu_search"


async def test_chat_image_endpoint_rejects_unsupported_content_type(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"image": ("photo.gif", b"GIF89a", "image/gif")}
            data = {"session_id": "img-route-2"}
            response = await client.post("/api/chat/image", data=data, files=files)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


async def test_chat_image_endpoint_rejects_oversized_image(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        oversized = b"\xff\xd8\xff\xe0" + b"0" * (5 * 1024 * 1024 + 1)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"image": ("big.jpg", oversized, "image/jpeg")}
            data = {"session_id": "img-route-3"}
            response = await client.post("/api/chat/image", data=data, files=files)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413


async def test_chat_image_endpoint_rejects_empty_image(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            files = {"image": ("empty.jpg", b"", "image/jpeg")}
            data = {"session_id": "img-route-4"}
            response = await client.post("/api/chat/image", data=data, files=files)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
