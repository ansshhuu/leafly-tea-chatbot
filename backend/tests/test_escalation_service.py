from sqlalchemy import select

from app.models.escalation import Escalation
from app.services import escalation_service


async def test_log_escalation_persists_row(db_session):
    escalation = await escalation_service.log_escalation(db_session, "session-1", "I'm furious!", "angry")

    assert escalation.id is not None
    assert escalation.resolved is False

    result = await db_session.execute(select(Escalation).where(Escalation.session_id == "session-1"))
    row = result.scalars().first()
    assert row.message == "I'm furious!"
    assert row.sentiment == "angry"


def test_escalation_sentiments_set():
    assert escalation_service.ESCALATION_SENTIMENTS == {"angry", "urgent"}
