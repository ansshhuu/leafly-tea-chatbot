from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.api.routes import chat as chat_route
from app.db.session import get_db
from app.main import app
from app.models.chat_history import ChatHistory

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


async def test_chat_endpoint_omits_user_id_when_not_provided(db_session, monkeypatch):
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
    mock_process.assert_awaited_once_with(db_session, "s-no-addr", "hi", user_id=None)


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


async def test_welcome_endpoint_returns_static_greeting():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/chat/welcome")

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == chat_route.DEFAULT_WELCOME_TEXT
    assert body["quick_reply_options"] == chat_route.WELCOME_QUICK_ACTIONS
