from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.api.routes import chat as chat_route
from app.db.session import get_db
from app.main import app
from app.models.chat_history import ChatHistory
from app.services import weather_service

FAKE_RESULT = {
    "reply_text": "Hello there!",
    "intent": "general_chat",
    "sentiment": "happy",
    "filters": None,
}


async def test_chat_endpoint_returns_reply_intent_sentiment_only(db_session, monkeypatch):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(chat_route, "process_chat_message", AsyncMock(return_value=FAKE_RESULT))

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello there!"
    assert body["intent"] == "general_chat"
    assert body["sentiment"] == "happy"
    assert body["language"] == "en"
    assert "filters" not in body
    assert "timestamp" in body


async def test_chat_endpoint_passes_through_detected_language(db_session, monkeypatch):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        chat_route,
        "process_chat_message",
        AsyncMock(return_value={**FAKE_RESULT, "language": "hi", "reply_text": "नमस्ते!"}),
    )

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={"session_id": "s2", "message": "नमस्ते"})
    finally:
        app.dependency_overrides.clear()

    assert response.json()["language"] == "hi"


async def test_chat_endpoint_accepts_empty_order_summary_with_no_orders_yet(db_session, monkeypatch):
    # Reproduces a 500: order_id/status are None when the customer has no draft
    # or past order (e.g. "what did I order?" before ever ordering anything).
    fake_result = {
        "reply_text": "Your order is currently empty.",
        "intent": "order",
        "sentiment": "neutral",
        "filters": None,
        "order_summary": {
            "order_id": None,
            "status": None,
            "items": [],
            "subtotal": 0.0,
            "tax": 0.0,
            "total": 0.0,
        },
    }

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(chat_route, "process_chat_message", AsyncMock(return_value=fake_result))

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat", json={"session_id": "s-no-orders", "message": "what did I order?"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["order_summary"]["order_id"] is None
    assert body["order_summary"]["status"] is None


async def test_chat_endpoint_passes_address_coords_through_to_process_chat_message(db_session, monkeypatch):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    mock_process = AsyncMock(return_value=FAKE_RESULT)
    monkeypatch.setattr(chat_route, "process_chat_message", mock_process)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                json={
                    "session_id": "s-addr",
                    "message": "14th Road, Bandra West, Mumbai",
                    "address_lat": 19.0596,
                    "address_lon": 72.8295,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    mock_process.assert_awaited_once_with(
        db_session, "s-addr", "14th Road, Bandra West, Mumbai", user_id=None, address_coords=(19.0596, 72.8295)
    )


async def test_chat_endpoint_omits_address_coords_when_not_provided(db_session, monkeypatch):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    mock_process = AsyncMock(return_value=FAKE_RESULT)
    monkeypatch.setattr(chat_route, "process_chat_message", mock_process)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={"session_id": "s-no-addr", "message": "hi"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    mock_process.assert_awaited_once_with(db_session, "s-no-addr", "hi", user_id=None, address_coords=None)


async def test_chat_endpoint_surfaces_awaiting_address_input_flag(db_session, monkeypatch):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        chat_route, "process_chat_message", AsyncMock(return_value={**FAKE_RESULT, "awaiting_address_input": True})
    )

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={"session_id": "s-await-addr", "message": "delivery"})
    finally:
        app.dependency_overrides.clear()

    assert response.json()["awaiting_address_input"] is True


async def test_chat_history_endpoint_returns_stored_turns_in_order(db_session, monkeypatch):
    db_session.add_all(
        [
            ChatHistory(session_id="s3", role="user", message="hi"),
            ChatHistory(session_id="s3", role="assistant", message="Hello there!"),
            ChatHistory(session_id="other-session", role="user", message="should not appear"),
        ]
    )
    await db_session.commit()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    call_gemini_mock = AsyncMock()
    monkeypatch.setattr(chat_route, "process_chat_message", call_gemini_mock)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/chat/history/s3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [row["role"] for row in body] == ["user", "assistant"]
    assert [row["message"] for row in body] == ["hi", "Hello there!"]
    call_gemini_mock.assert_not_called()


async def test_chat_history_endpoint_empty_for_unknown_session(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/chat/history/never-existed")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == []


async def test_welcome_endpoint_uses_generic_message_when_weather_is_pleasant(monkeypatch):
    monkeypatch.setattr(weather_service, "get_condition", AsyncMock(return_value="pleasant"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/chat/welcome")

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == chat_route.DEFAULT_WELCOME_TEXT
    assert body["quick_reply_options"] == chat_route.WELCOME_QUICK_ACTIONS


async def test_welcome_endpoint_mentions_rain_when_condition_is_rainy(monkeypatch):
    monkeypatch.setattr(weather_service, "get_condition", AsyncMock(return_value="rainy"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/chat/welcome")

    assert "raining" in response.json()["reply"].lower()


async def test_welcome_endpoint_falls_back_to_generic_message_when_weather_fetch_fails(monkeypatch):
    monkeypatch.setattr(weather_service, "get_condition", AsyncMock(return_value=None))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/chat/welcome")

    assert response.status_code == 200
    assert response.json()["reply"] == chat_route.DEFAULT_WELCOME_TEXT
