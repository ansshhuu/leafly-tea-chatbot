import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import session_service

# Only these are treated as explicit confirmation of the just-suggested
# add-on - anything else (a new question, an unrelated item name, a typo
# that happens to contain the add-on's name) falls through to normal intent
# routing instead of being guessed as a "yes". This replaces an earlier
# loose substring/keyword match against the add-on item's name, which was
# firing on unrelated replies that merely happened to mention the item.
_AFFIRMATIVE_PATTERN = re.compile(
    r"^(y|ya|yah|yeah|yep|yup|yes|yes please|sure|ok|okay|k|add it|add|please add|add that|"
    r"haan|han|ha|theek hai|thik hai|chalega|karo|add karo|haan karo|haan please)[.!\s]*$",
    re.IGNORECASE,
)
_DECLINE_PATTERN = re.compile(
    r"^(n|no|nah|nope|no thanks|no thank you|not now|skip|nahi|nako|rehne do|na)[.!\s]*$",
    re.IGNORECASE,
)
# A hedge word ("maybe") is NOT safe to just drop-and-fall-through to Gemini
# like a real unrelated message would be: Gemini still sees its own "Want to
# add X?" turn in chat history, and can bias toward reading "maybe" as
# confirmation - producing a genuine order_action=add that actually adds the
# item via the normal order-intent path, not merely a wrong reply string.
# These carry no topic of their own, so they're short-circuited with a
# clarifying nudge and never reach Gemini at all - a real question ("does it
# have nuts?") still falls through to normal routing untouched, since it
# isn't in this list.
_AMBIGUOUS_FILLER_PATTERN = re.compile(
    r"^(maybe|may be|not sure|not really sure|idk|i dont know|i don't know|hmm|hmmm|later|perhaps|possibly|"
    r"shayad|pata nahi|pta nahi)[.!\s]*$",
    re.IGNORECASE,
)

_pending: dict[str, dict] = {}


def is_affirmative(user_message: str, item_name: str | None = None) -> bool:
    normalized = user_message.strip()
    if bool(_AFFIRMATIVE_PATTERN.match(normalized)):
        return True
    # The quick-reply button's own label ("Add Butter Croissant") isn't a
    # generic affirmative word, but it's exact and unambiguous - the click
    # sends this literal text as the chat message (see QuickReplyOptions.jsx),
    # so matching it here is what makes tapping the button behave exactly
    # like a typed "yes", without the free-text ambiguity risk at all.
    if item_name is not None:
        return normalized.lower() == f"add {item_name}".lower()
    return False


def confirm_quick_replies(item_name: str) -> list[str]:
    return [f"Add {item_name}", "No thanks"]


def is_decline(user_message: str) -> bool:
    return bool(_DECLINE_PATTERN.match(user_message.strip()))


def is_ambiguous_filler(user_message: str) -> bool:
    return bool(_AMBIGUOUS_FILLER_PATTERN.match(user_message.strip()))


async def mark_pending(db: AsyncSession, session_id: str, item_id: int, item_name: str, language: str) -> None:
    _pending[session_id] = {"item_id": item_id, "item_name": item_name, "language": language}
    await session_service.update_state(
        db,
        session_id,
        pending_addon_item_id=item_id,
        pending_addon_item_name=item_name,
        pending_addon_language=language,
    )


async def get_pending(db: AsyncSession, session_id: str) -> dict | None:
    if session_id in _pending:
        return _pending[session_id]
    state = await session_service.get_state(db, session_id)
    item_id = state.get("pending_addon_item_id")
    if item_id is None:
        _pending[session_id] = None
        return None
    pending = {
        "item_id": item_id,
        "item_name": state.get("pending_addon_item_name"),
        "language": state.get("pending_addon_language") or "en",
    }
    _pending[session_id] = pending
    return pending


async def clear_pending(db: AsyncSession, session_id: str) -> None:
    _pending[session_id] = None
    await session_service.update_state(
        db, session_id, pending_addon_item_id=None, pending_addon_item_name=None, pending_addon_language=None
    )


def clear() -> None:
    _pending.clear()
