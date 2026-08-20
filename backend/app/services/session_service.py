from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_session import ChatSession

_DEFAULTS = {
    "known_name": None,
    "known_phone": None,
    "known_email": None,
}

_cache: dict[str, dict] = {}


def _row_to_state(row: ChatSession) -> dict:
    return {
        "known_name": row.known_name,
        "known_phone": row.known_phone,
        "known_email": row.known_email,
    }


async def get_state(db: AsyncSession, session_id: str) -> dict:
    if session_id in _cache:
        return _cache[session_id]

    row = await db.get(ChatSession, session_id)
    state = _row_to_state(row) if row is not None else dict(_DEFAULTS)
    _cache[session_id] = state
    return state


async def update_state(db: AsyncSession, session_id: str, **fields) -> dict:
    state = await get_state(db, session_id)
    state = {**state, **fields}
    _cache[session_id] = state

    row = await db.get(ChatSession, session_id)
    if row is None:
        row = ChatSession(session_id=session_id, **state)
        db.add(row)
    else:
        for key, value in fields.items():
            setattr(row, key, value)
    await db.commit()
    return state


def clear() -> None:
    _cache.clear()
