import logging
import re

from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import CONTACT_EMAIL, TAGLINES, settings
from app.core.timing import timed
from app.models.chat_history import ChatHistory
from app.prompts.system_prompt import build_system_prompt
from app.prompts.templates import t
from app.schemas.chat import Filters, GeminiChatOutput
from app.services import (
    cache_service,
    escalation_service,
    faq_service,
    product_context,
    quick_reply_service,
    recommendation_service,
    session_context_service,
    usage_logger,
)
from app.services.gemini_client import get_client
from app.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "I'm having some trouble right now - please try again in a moment."
EMOJI_ONLY_REPLY = "I couldn't quite understand that - could you type it in words?"
CACHEABLE_INTENTS = {"menu_search", "faq", "recommendation"}
GROUNDABLE_INTENTS = {"menu_search", "recommendation"}
HISTORY_LIMIT = 10

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "\U00002b00-\U00002bff"
    "\U0000fe0f"
    "\U0000200d"
    "]+"
)


def _is_emoji_only(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return _EMOJI_PATTERN.sub("", stripped).strip() == ""


def _fallback_result() -> dict:
    return {
        "reply_text": FALLBACK_MESSAGE,
        "intent": "general_chat",
        "sentiment": "neutral",
        "language": "en",
        "filters": None,
    }


async def _fetch_recent_history(db: AsyncSession, session_id: str) -> list[ChatHistory]:
    async with timed("db.chat_history_fetch"):
        stmt = (
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
            .limit(HISTORY_LIMIT)
        )
        result = await db.execute(stmt)
        return list(reversed(result.scalars().all()))


async def _save_turn(db: AsyncSession, session_id: str, user_message: str, reply_text: str) -> None:
    async with timed("db.save_turn_commit"):
        db.add(ChatHistory(session_id=session_id, role="user", message=user_message))
        db.add(ChatHistory(session_id=session_id, role="assistant", message=reply_text))
        await db.commit()


def _history_to_contents(history: list[ChatHistory], user_message: str) -> list[types.Content]:
    contents = [
        types.Content(
            role="user" if turn.role == "user" else "model",
            parts=[types.Part.from_text(text=turn.message)],
        )
        for turn in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))
    return contents


async def _build_pre_call_context(db: AsyncSession, user_message: str, session_id: str) -> str:
    async with timed("pre_call_context_build"):
        popular = await product_context.get_popular_items(db)
        blocks = [product_context.format_items_block(popular, "A few popular picks (small sample, not the full catalog)")]

        faq_matches = faq_service.find_matches(user_message)
        if faq_matches:
            blocks.append(faq_service.format_faq_block(faq_matches))

        known_name = await session_context_service.get_name(db, session_id)
        if known_name:
            blocks.append(
                f"Customer's name for this session: {known_name} (use it naturally where it fits - a "
                "greeting, an order confirmation lead-in, etc. - you already know it, so don't ask again)."
            )

        return "\n\n".join(blocks)


def _is_broad_menu_query(filters: Filters | None) -> bool:
    if filters is None:
        return True
    return all(value is None for value in filters.model_dump().values())


def _is_about_question(user_message: str) -> bool:
    matches = faq_service.find_matches(user_message)
    return bool(matches) and matches[0]["category"] == "about"


def _build_about_reply(language: str) -> str:
    return t("faq_about_intro", language, tagline=TAGLINES[0], email=CONTACT_EMAIL)


async def _ground_reply(
    db: AsyncSession, parsed: GeminiChatOutput, user_message: str
) -> tuple[str, list[dict] | None]:
    if parsed.intent == "recommendation":
        candidates = await product_context.get_filtered_items(
            db, parsed.filters, limit=product_context.RECOMMENDATION_POOL_LIMIT
        )
    else:
        candidates = await product_context.get_filtered_items(db, parsed.filters)

    if not candidates:
        closest, relaxed_field = await product_context.get_closest_items(db, parsed.filters)
        if not closest:
            return f"{parsed.reply_text} I couldn't find anything in the catalog matching that right now.".strip(), None
        reply_text = f"{parsed.reply_text} {product_context.fallback_intro(relaxed_field)}".strip()
        return reply_text, closest

    if parsed.intent != "recommendation":
        return parsed.reply_text, candidates

    ranked = recommendation_service.shortlist(candidates, user_message)
    combo = None
    if parsed.filters and parsed.filters.max_price:
        combo = recommendation_service.combo_within_budget(ranked, parsed.filters.max_price)

    if parsed.filters and parsed.filters.max_price and not combo:
        suggested = sorted(ranked, key=lambda item: item["price"])[:1]
    elif combo:
        suggested = combo
    else:
        suggested = ranked

    return parsed.reply_text, suggested


_NAME_RECALL_KEYWORDS = (
    "whats my name",
    "what is my name",
    "who am i",
    "do you know my name",
    "do you remember my name",
)


def _is_name_recall_question(text: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", text.lower())
    return any(phrase in normalized for phrase in _NAME_RECALL_KEYWORDS)


async def _call_gemini(system_prompt: str, contents: list[types.Content]) -> tuple[GeminiChatOutput, int | None]:
    if settings.test_mode:
        return (
            GeminiChatOutput(
                reply_text="[TEST_MODE] mocked reply - no real Gemini call was made.",
                intent="general_chat",
                sentiment="neutral",
                language="en",
            ),
            0,
        )

    client = get_client()
    async with timed("gemini.generate_content"):
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=GeminiChatOutput,
                temperature=0.4,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

    parsed = response.parsed
    if not isinstance(parsed, GeminiChatOutput):
        parsed = GeminiChatOutput.model_validate_json(response.text)

    tokens_used = getattr(getattr(response, "usage_metadata", None), "total_token_count", None)
    return parsed, tokens_used


async def process_chat_message(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    user_id: int | None = None,
) -> dict:
    async with timed(f"chat_turn_total intent_hint={user_message[:24]!r}"):
        result = await _resolve_chat_result(db, session_id, user_message, user_id)

    if result["sentiment"] in escalation_service.ESCALATION_SENTIMENTS:
        await escalation_service.log_escalation(db, session_id, user_message, result["sentiment"])

    return result


def _apply_menu_translation(result: dict) -> None:
    """Translates any menu-item payload into result["language"] right before
    it goes out - re-run on EVERY path that can carry menu_display/
    suggested_items, including a cache hit (see the cache_service.get_cached
    branch below). A cached entry's items were only ever translated using
    whatever this function looked like at the moment it was cached - without
    this also running on cache hits, an entry cached before this translation
    step existed (or under a differently-classified language) would keep
    serving stale/untranslated item names for its whole TTL. Both translate_*
    calls are safe to re-run on already-translated input - the lookup is
    keyed by the item's ENGLISH name, so a name that's already in Hindi
    simply won't match and passes through unchanged."""
    if result.get("menu_display"):
        result["menu_display"] = product_context.translate_product_display(result["menu_display"], result["language"])
    if result.get("suggested_items"):
        result["suggested_items"] = product_context.translate_suggested_items(result["suggested_items"], result["language"])


async def _resolve_chat_result(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    user_id: int | None,
) -> dict:
    if _is_emoji_only(user_message):
        result = {
            "reply_text": EMOJI_ONLY_REPLY,
            "intent": "general_chat",
            "sentiment": "confused",
            "language": "en",
            "filters": None,
        }
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    normalized_query = user_message.strip().lower()

    cached = cache_service.get_cached(normalized_query)
    if cached is not None:
        usage_logger.log_call(session_id=session_id, tokens_used=None, cached=True, fallback=False)
        _apply_menu_translation(cached)
        await _save_turn(db, session_id, user_message, cached["reply_text"])
        return cached

    if not rate_limiter.is_within_limits():
        usage_logger.log_call(session_id=session_id, tokens_used=None, cached=False, fallback=True)
        result = _fallback_result()
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    history = await _fetch_recent_history(db, session_id)
    dynamic_context = await _build_pre_call_context(db, user_message, session_id)
    system_prompt = build_system_prompt(dynamic_context)
    contents = _history_to_contents(history, user_message)

    try:
        parsed, tokens_used = await _call_gemini(system_prompt, contents)
    except Exception:
        logger.exception("Gemini API call failed for session %s", session_id)
        result = _fallback_result()
        await _save_turn(db, session_id, user_message, result["reply_text"])
        return result

    rate_limiter.record_call()
    usage_logger.log_call(session_id=session_id, tokens_used=tokens_used, cached=False, fallback=False)
    logger.debug(
        "gemini.parsed intent=%s filters=%s reply_text=%r",
        parsed.intent,
        parsed.filters.model_dump() if parsed.filters else None,
        parsed.reply_text,
    )

    if parsed.detected_name:
        await session_context_service.remember_name(db, session_id, parsed.detected_name)

    result = parsed.model_dump()

    async with timed(f"intent_dispatch intent={parsed.intent}"):
        if _is_name_recall_question(user_message):
            known_name = await session_context_service.get_name(db, session_id)
            if known_name:
                result["reply_text"] = f"You're {known_name}! Good to chat with you again."
            else:
                result["reply_text"] = (
                    "I don't have a name on file for you yet this session - "
                    "let me know your name and I'll remember it!"
                )
        elif parsed.intent == "menu_search" and _is_broad_menu_query(parsed.filters):
            result["menu_display"] = await product_context.get_full_product_display(db)
        elif parsed.intent in GROUNDABLE_INTENTS:
            result["reply_text"], result["suggested_items"] = await _ground_reply(db, parsed, user_message)
        elif parsed.intent == "faq" and _is_about_question(user_message):
            result["reply_text"] = _build_about_reply(parsed.language)
        elif parsed.intent == "general_chat" and (
            quick_reply_service.is_capability_question(user_message) or quick_reply_service.is_greeting(user_message)
        ):
            result["quick_reply_options"] = list(quick_reply_service.QUICK_ACTION_OPTIONS)

    _apply_menu_translation(result)

    if result["sentiment"] in escalation_service.ESCALATION_SENTIMENTS:
        result["reply_text"] = t("escalation_response", result["language"], email=CONTACT_EMAIL)
        result["quick_reply_options"] = None
        result["menu_display"] = None
        result["suggested_items"] = None

    await _save_turn(db, session_id, user_message, result["reply_text"])

    if parsed.intent in CACHEABLE_INTENTS:
        cache_service.set_cached(normalized_query, result)

    return result
