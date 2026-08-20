from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import Escalation

ESCALATION_SENTIMENTS = {"angry", "urgent"}


async def log_escalation(db: AsyncSession, session_id: str, message: str, sentiment: str) -> Escalation:
    escalation = Escalation(session_id=session_id, message=message, sentiment=sentiment)
    db.add(escalation)
    await db.commit()
    await db.refresh(escalation)
    return escalation
