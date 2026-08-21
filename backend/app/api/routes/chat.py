from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, WelcomeResponse
from app.schemas.chat_history import ChatHistoryRead
from app.services import chat_history_service, weather_service
from app.services.ai_service import process_chat_message

router = APIRouter()

DEFAULT_WELCOME_TEXT = "Hi there! 👋 I'm your Leafly Assistant. How can I help you today?"
WELCOME_QUICK_ACTIONS = ["Explore Tea Collections", "Wellness Benefits", "Ask About a Tea", "Gift Hampers"]


@router.get("/welcome", response_model=WelcomeResponse)
async def welcome(lat: float | None = None, lon: float | None = None) -> WelcomeResponse:
    # lat/lon are the customer's own browser geolocation, when granted - see
    # weather_service.get_condition - falling back to a default location
    # when omitted (permission denied/unavailable), so this never blocks on it.
    condition = await weather_service.get_condition(lat, lon)
    hint = weather_service.get_weather_hint(condition)
    reply = f"{DEFAULT_WELCOME_TEXT} {hint}" if hint else DEFAULT_WELCOME_TEXT
    return WelcomeResponse(reply=reply, quick_reply_options=WELCOME_QUICK_ACTIONS)


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatResponse:
    result = await process_chat_message(db, payload.session_id, payload.message, user_id=payload.user_id)
    return ChatResponse(
        reply=result["reply_text"],
        timestamp=datetime.now(timezone.utc),
        intent=result["intent"],
        sentiment=result["sentiment"],
        language=result.get("language", "en"),
        menu_display=result.get("menu_display"),
        suggested_items=result.get("suggested_items"),
        quick_reply_options=result.get("quick_reply_options"),
    )


@router.get("/history/{session_id}", response_model=list[ChatHistoryRead])
async def chat_history(session_id: str, db: AsyncSession = Depends(get_db)) -> list[ChatHistoryRead]:
    """Pure DB read for the frontend's reload-sync - never calls Gemini and
    never re-processes old messages, just returns them as-is (see
    chat_history_service.get_session_history)."""
    return await chat_history_service.get_session_history(db, session_id)
