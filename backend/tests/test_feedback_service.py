from sqlalchemy import select

from app.models.feedback import Feedback
from app.services import feedback_service


async def test_pending_lifecycle(db_session):
    assert await feedback_service.is_pending(db_session, "session-1") is False
    await feedback_service.mark_pending(db_session, "session-1")
    assert await feedback_service.is_pending(db_session, "session-1") is True
    await feedback_service.clear_pending(db_session, "session-1")
    assert await feedback_service.is_pending(db_session, "session-1") is False


async def test_pending_survives_memory_cache_eviction_via_db(db_session):
    feedback_service.clear()
    await feedback_service.mark_pending(db_session, "session-restart")

    feedback_service.clear()  # simulates a fresh process - memory cache is empty

    assert await feedback_service.is_pending(db_session, "session-restart") is True


def test_map_sentiment_classifies_positive_negative_neutral():
    assert feedback_service.map_sentiment("happy") == "positive"
    assert feedback_service.map_sentiment("angry") == "negative"
    assert feedback_service.map_sentiment("urgent") == "negative"
    assert feedback_service.map_sentiment("neutral") == "neutral"
    assert feedback_service.map_sentiment("confused") == "neutral"


async def test_save_feedback_persists_row(db_session):
    await feedback_service.save_feedback(db_session, "session-1", "9876543210", "Loved it!", "positive")

    result = await db_session.execute(select(Feedback).where(Feedback.session_id == "session-1"))
    row = result.scalars().first()
    assert row is not None
    assert row.feedback_text == "Loved it!"
    assert row.sentiment == "positive"
    assert row.guest_phone == "9876543210"
