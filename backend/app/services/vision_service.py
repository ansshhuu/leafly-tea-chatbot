import difflib
import logging
import re

from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import CAFE_PHONE, settings
from app.models.chat_history import ChatHistory
from app.models.menu_item import MenuItem
from app.prompts.vision_prompt import build_vision_prompt
from app.schemas.vision import ImageAnalysisOutput
from app.services import menu_cache_service, menu_context, usage_logger
from app.services.gemini_client import get_client
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "I'm having some trouble right now - please try again in a moment."
DEFAULT_CAPTION = "What is this?"
# Strict - only a genuine near-exact name match counts (e.g. a typo-level
# difference), never a loose "similar item" guess. Matches the same
# reasoning as order_service.AUTO_MATCH_FUZZY_CUTOFF.
NAME_MATCH_CUTOFF = 0.72

BOT_AVATAR_REPLY = "That's me! I'm Rumi 🤖"
OUT_OF_SCOPE_REPLY = (
    "I can only help with photos of food or drinks (to find similar menu items), "
    "a receipt, or my own picture! For anything else, I'm not much help there - "
    "but happy to chat about the menu, orders, or reservations instead."
)
NO_MATCH_SUFFIX = f"That's not on our menu — for special requests, contact us at {CAFE_PHONE}."
SPECIAL_REQUEST_SUFFIX = (
    f"While this isn't on our regular menu, we'd love to see if we can make something "
    f"special for you! Please contact our team at {CAFE_PHONE} to discuss custom requests."
)


def _match_menu_item_by_name(items: list[MenuItem], identified_name: str | None) -> MenuItem | None:
    """Simple exact/near-exact NAME match only - no category/tag-based
    "similar item" guessing (that's what silently suggested unrelated items
    for photos of food we don't serve, e.g. stir-fried noodles, Coke)."""
    if not identified_name:
        return None
    needle = identified_name.strip().lower()
    if not needle:
        return None

    for item in items:
        if item.name.lower() == needle:
            return item

    names = [item.name.lower() for item in items]
    close = difflib.get_close_matches(needle, names, n=1, cutoff=NAME_MATCH_CUTOFF)
    if not close:
        return None
    return next(item for item in items if item.name.lower() == close[0])


# Phrases that signal the customer wants something custom/special MADE for
# them based on the photo, not just "what is this" identification - e.g.
# "can I get this made", "is this a special order", "I want something like
# this". Checked against the caption text only (punctuation stripped, same
# approach as ai_service._is_order_summary_question), never against the
# image content itself.
_SPECIAL_REQUEST_KEYWORDS = (
    "special order",
    "special request",
    "custom order",
    "custom request",
    "can you make",
    "can i get this made",
    "make this for me",
    "make one like this",
    "something like this",
    "like this",
    "custom",
    "special",
)


def _is_special_request(caption: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", caption.lower())
    return any(phrase in normalized for phrase in _SPECIAL_REQUEST_KEYWORDS)


async def _call_vision(
    db: AsyncSession, image_bytes: bytes, mime_type: str, caption: str | None
) -> tuple[ImageAnalysisOutput, int | None]:
    if settings.test_mode:
        return (
            ImageAnalysisOutput(
                image_type="other",
                description="[TEST_MODE] mocked reply - no real Gemini call was made.",
                identified_name=None,
            ),
            0,
        )

    client = get_client()
    parts = [types.Part.from_bytes(data=image_bytes, mime_type=mime_type)]
    if caption:
        parts.append(types.Part.from_text(text=caption))

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            system_instruction=build_vision_prompt(),
            response_mime_type="application/json",
            response_schema=ImageAnalysisOutput,
            temperature=0.3,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    parsed = response.parsed
    if not isinstance(parsed, ImageAnalysisOutput):
        parsed = ImageAnalysisOutput.model_validate_json(response.text)

    tokens_used = getattr(getattr(response, "usage_metadata", None), "total_token_count", None)
    return parsed, tokens_used


async def _save_turn(db: AsyncSession, session_id: str, caption: str | None, reply_text: str) -> None:
    user_message = f"[image uploaded] {caption}".strip() if caption else "[image uploaded]"
    db.add(ChatHistory(session_id=session_id, role="user", message=user_message))
    db.add(ChatHistory(session_id=session_id, role="assistant", message=reply_text))
    await db.commit()


async def analyze_menu_image(
    db: AsyncSession, session_id: str, image_bytes: bytes, mime_type: str, caption: str | None
) -> dict:
    caption = caption.strip() if caption and caption.strip() else DEFAULT_CAPTION

    if not rate_limiter.is_within_limits():
        usage_logger.log_call(session_id=session_id, tokens_used=None, cached=False, fallback=True)
        result = {"reply_text": FALLBACK_MESSAGE, "intent": "menu_search", "sentiment": "neutral", "language": "en"}
        await _save_turn(db, session_id, caption, result["reply_text"])
        return result

    try:
        parsed, tokens_used = await _call_vision(db, image_bytes, mime_type, caption)
    except Exception:
        logger.exception("Gemini vision call failed for session %s", session_id)
        result = {"reply_text": FALLBACK_MESSAGE, "intent": "menu_search", "sentiment": "neutral", "language": "en"}
        await _save_turn(db, session_id, caption, result["reply_text"])
        return result

    rate_limiter.record_call()
    usage_logger.log_call(session_id=session_id, tokens_used=tokens_used, cached=False, fallback=False)

    if parsed.image_type == "bot_avatar":
        result = {"reply_text": BOT_AVATAR_REPLY, "intent": "general_chat", "sentiment": "happy", "language": "en"}
        await _save_turn(db, session_id, caption, result["reply_text"])
        return result

    if parsed.image_type == "other":
        result = {"reply_text": OUT_OF_SCOPE_REPLY, "intent": "general_chat", "sentiment": "neutral", "language": "en"}
        await _save_turn(db, session_id, caption, result["reply_text"])
        return result

    if parsed.image_type == "receipt":
        result = {"reply_text": parsed.description, "intent": "faq", "sentiment": "neutral", "language": "en"}
        await _save_turn(db, session_id, caption, result["reply_text"])
        return result

    if _is_special_request(caption):
        # The customer wants something custom/special made based on the
        # photo, not a lookup of what's already on the menu - skip matching
        # entirely and hand off to the team, regardless of whether the photo
        # happens to resemble an existing item.
        reply_text = f"{parsed.description} {SPECIAL_REQUEST_SUFFIX}".strip()
        suggested_items = None
    else:
        items = await menu_cache_service.get_available_items(db)
        match = _match_menu_item_by_name(items, parsed.identified_name)
        if match is not None:
            reply_text = parsed.description
            suggested_items = [menu_context._row_to_dict(match)]
        else:
            reply_text = f"{parsed.description} {NO_MATCH_SUFFIX}".strip()
            suggested_items = None

    result = {
        "reply_text": reply_text,
        "intent": "menu_search",
        "sentiment": "neutral",
        "language": "en",
        "suggested_items": suggested_items,
    }
    await _save_turn(db, session_id, caption, reply_text)
    return result
