from dataclasses import dataclass
from datetime import date as date_type, time as time_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import session_service

STEPS = ["location", "date", "time", "guests", "name", "phone", "email", "special_requests", "confirm", "payment"]


@dataclass
class ReservationDraft:
    location: str | None = None
    date: date_type | None = None
    time: time_type | None = None
    guests: int | None = None
    name: str | None = None
    phone: str | None = None
    special_requests: str | None = None
    special_requests_skipped: bool = False
    email: str | None = None
    is_birthday: bool | None = None
    confirmed: bool = False
    last_prompted_step: str | None = None

    def next_step(self) -> str | None:
        if self.location is None:
            return "location"
        if self.date is None:
            return "date"
        if self.time is None:
            return "time"
        if self.guests is None:
            return "guests"
        if self.name is None:
            return "name"
        if self.phone is None:
            return "phone"
        if self.email is None:
            return "email"
        if self.special_requests is None and not self.special_requests_skipped:
            return "special_requests"
        if not self.confirmed:
            return "confirm"
        return "payment"


def _to_dict(draft: ReservationDraft) -> dict:
    return {
        "location": draft.location,
        "date": draft.date.isoformat() if draft.date else None,
        "time": draft.time.isoformat() if draft.time else None,
        "guests": draft.guests,
        "name": draft.name,
        "phone": draft.phone,
        "special_requests": draft.special_requests,
        "special_requests_skipped": draft.special_requests_skipped,
        "email": draft.email,
        "is_birthday": draft.is_birthday,
        "confirmed": draft.confirmed,
        "last_prompted_step": draft.last_prompted_step,
    }


def _from_dict(data: dict) -> ReservationDraft:
    return ReservationDraft(
        location=data.get("location"),
        date=date_type.fromisoformat(data["date"]) if data.get("date") else None,
        time=time_type.fromisoformat(data["time"]) if data.get("time") else None,
        guests=data.get("guests"),
        name=data.get("name"),
        phone=data.get("phone"),
        special_requests=data.get("special_requests"),
        special_requests_skipped=bool(data.get("special_requests_skipped", False)),
        email=data.get("email"),
        is_birthday=data.get("is_birthday"),
        confirmed=bool(data.get("confirmed", False)),
        last_prompted_step=data.get("last_prompted_step"),
    )


_drafts: dict[str, ReservationDraft] = {}


async def get_draft(db: AsyncSession, session_id: str) -> ReservationDraft | None:
    if session_id in _drafts:
        return _drafts[session_id]
    state = await session_service.get_state(db, session_id)
    if state.get("reservation_draft"):
        draft = _from_dict(state["reservation_draft"])
        _drafts[session_id] = draft
        return draft
    return None


async def get_or_create_draft(db: AsyncSession, session_id: str) -> ReservationDraft:
    draft = await get_draft(db, session_id)
    if draft is None:
        draft = ReservationDraft()
        _drafts[session_id] = draft
    return draft


async def sync_draft(db: AsyncSession, session_id: str) -> None:
    draft = _drafts.get(session_id)
    await session_service.update_state(
        db, session_id, reservation_draft=_to_dict(draft) if draft is not None else None
    )


def clear_draft(session_id: str) -> None:
    _drafts.pop(session_id, None)


def clear() -> None:
    _drafts.clear()


def describe_progress(draft: ReservationDraft) -> str | None:
    step = draft.next_step()
    if step is None:
        return None

    collected = []
    if draft.location:
        collected.append(f"location={draft.location}")
    if draft.date:
        collected.append(f"date={draft.date.isoformat()}")
    if draft.time:
        collected.append(f"time={draft.time.strftime('%I:%M %p')}")
    if draft.guests:
        collected.append(f"guests={draft.guests}")
    if draft.name:
        collected.append(f"name={draft.name}")
    if draft.phone:
        collected.append(f"phone={draft.phone}")
    collected_text = ", ".join(collected) if collected else "nothing yet"

    return (
        "The customer is in the middle of a table reservation. Already "
        f"collected (do NOT ask about these again): {collected_text}. Still "
        f"needed next: {step}. If reservation_details is relevant this turn, "
        "extract ONLY the still-needed field - Python tracks everything "
        "already collected on its own and will never lose it."
    )
