from sqlalchemy.ext.asyncio import AsyncSession

from app.services import session_service

_names: dict[str, str] = {}
_phones: dict[str, str] = {}
_emails: dict[str, str] = {}


async def remember_name(db: AsyncSession, session_id: str, name: str) -> None:
    cleaned = name.strip()
    if cleaned:
        _names[session_id] = cleaned
        await session_service.update_state(db, session_id, known_name=cleaned)


async def get_name(db: AsyncSession, session_id: str) -> str | None:
    if session_id in _names:
        return _names[session_id]
    state = await session_service.get_state(db, session_id)
    if state.get("known_name"):
        _names[session_id] = state["known_name"]
    return state.get("known_name")


async def remember_phone(db: AsyncSession, session_id: str, phone: str) -> None:
    cleaned = phone.strip()
    if cleaned:
        _phones[session_id] = cleaned
        await session_service.update_state(db, session_id, known_phone=cleaned)


async def get_phone(db: AsyncSession, session_id: str) -> str | None:
    if session_id in _phones:
        return _phones[session_id]
    state = await session_service.get_state(db, session_id)
    if state.get("known_phone"):
        _phones[session_id] = state["known_phone"]
    return state.get("known_phone")


async def remember_email(db: AsyncSession, session_id: str, email: str) -> None:
    cleaned = email.strip()
    if cleaned:
        _emails[session_id] = cleaned
        await session_service.update_state(db, session_id, known_email=cleaned)


async def get_email(db: AsyncSession, session_id: str) -> str | None:
    if session_id in _emails:
        return _emails[session_id]
    state = await session_service.get_state(db, session_id)
    if state.get("known_email"):
        _emails[session_id] = state["known_email"]
    return state.get("known_email")


def clear() -> None:
    _names.clear()
    _phones.clear()
    _emails.clear()
