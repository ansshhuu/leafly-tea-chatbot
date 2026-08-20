from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, WelcomeResponse
from app.schemas.chat_history import ChatHistoryRead
from app.schemas.vision import ChatImageResponse
from app.services import chat_history_service, weather_service
from app.services.ai_service import process_chat_message
from app.services.reservation_service import run_reminder_check
from app.services.vision_service import analyze_menu_image

router = APIRouter()

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}

DEFAULT_WELCOME_TEXT = "Hi there! 👋 Welcome to Rasa Café. I'm Rumi - how can I help you today?"
WELCOME_QUICK_ACTIONS = ["View Menu", "Café Location", "Book a Table", "Events & Offers"]


@router.get("/welcome", response_model=WelcomeResponse)
async def welcome(lat: float | None = None, lon: float | None = None) -> WelcomeResponse:
    # lat/lon are the customer's own browser geolocation, when granted - see
    # weather_service.get_condition - falling back to the cafe's own location
    # when omitted (permission denied/unavailable), so this never blocks on it.
    condition = await weather_service.get_condition(lat, lon)
    hint = weather_service.get_weather_hint(condition)
    reply = f"{DEFAULT_WELCOME_TEXT} {hint}" if hint else DEFAULT_WELCOME_TEXT
    return WelcomeResponse(reply=reply, quick_reply_options=WELCOME_QUICK_ACTIONS)


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)
) -> ChatResponse:
    # Throttled to ~once/minute internally, but it opens its own DB session -
    # runs after the response is sent so it never adds latency to a chat turn.
    background_tasks.add_task(run_reminder_check)

    address_coords = None
    if payload.address_lat is not None and payload.address_lon is not None:
        address_coords = (payload.address_lat, payload.address_lon)

    result = await process_chat_message(
        db, payload.session_id, payload.message, user_id=payload.user_id, address_coords=address_coords
    )
    return ChatResponse(
        reply=result["reply_text"],
        timestamp=datetime.now(timezone.utc),
        intent=result["intent"],
        sentiment=result["sentiment"],
        language=result.get("language", "en"),
        menu_display=result.get("menu_display"),
        suggested_items=result.get("suggested_items"),
        order_summary=result.get("order_summary"),
        quick_reply_options=result.get("quick_reply_options"),
        date_picker_options=result.get("date_picker_options"),
        payment_request=result.get("payment_request"),
        loyalty_card=result.get("loyalty_card"),
        location_cards=result.get("location_cards"),
        awaiting_address_input=result.get("awaiting_address_input", False),
    )


@router.get("/history/{session_id}", response_model=list[ChatHistoryRead])
async def chat_history(session_id: str, db: AsyncSession = Depends(get_db)) -> list[ChatHistoryRead]:
    """Pure DB read for the frontend's reload-sync - never calls Gemini and
    never re-processes old messages, just returns them as-is (see
    chat_history_service.get_session_history)."""
    return await chat_history_service.get_session_history(db, session_id)


@router.post("/image", response_model=ChatImageResponse)
async def chat_image(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    message: str | None = Form(None),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> ChatImageResponse:
    background_tasks.add_task(run_reminder_check)

    if image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail="Only JPG and PNG images are supported")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="Empty image upload")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 5MB or smaller")

    result = await analyze_menu_image(db, session_id, image_bytes, image.content_type, message or None)
    return ChatImageResponse(
        reply=result["reply_text"],
        timestamp=datetime.now(timezone.utc),
        intent=result["intent"],
        sentiment=result["sentiment"],
        language=result.get("language", "en"),
        suggested_items=result.get("suggested_items"),
    )
