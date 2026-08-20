from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_history import ChatHistory

HISTORY_READ_LIMIT = 200


async def get_session_history(
    db: AsyncSession, session_id: str, limit: int = HISTORY_READ_LIMIT
) -> list[ChatHistory]:
    stmt = (
        select(ChatHistory)
        .where(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.created_at.asc(), ChatHistory.id.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
