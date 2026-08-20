from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback import Feedback
from app.services import session_service

_SENTIMENT_MAP = {
    "happy": "positive",
    "angry": "negative",
    "urgent": "negative",
    "neutral": "neutral",
    "confused": "neutral",
}

_pending: dict[str, bool] = {}


async def mark_pending(db: AsyncSession, session_id: str) -> None:
    _pending[session_id] = True
    await session_service.update_state(db, session_id, feedback_pending=True)


async def is_pending(db: AsyncSession, session_id: str) -> bool:
    if session_id in _pending:
        return _pending[session_id]
    state = await session_service.get_state(db, session_id)
    pending = bool(state.get("feedback_pending"))
    _pending[session_id] = pending
    return pending


async def clear_pending(db: AsyncSession, session_id: str) -> None:
    _pending[session_id] = False
    await session_service.update_state(db, session_id, feedback_pending=False)


def clear() -> None:
    _pending.clear()


def map_sentiment(raw_sentiment: str) -> str:
    return _SENTIMENT_MAP.get(raw_sentiment, "neutral")


async def save_feedback(
    db: AsyncSession, session_id: str, guest_phone: str | None, feedback_text: str, sentiment: str
) -> Feedback:
    feedback = Feedback(session_id=session_id, guest_phone=guest_phone, feedback_text=feedback_text, sentiment=sentiment)
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return feedback
