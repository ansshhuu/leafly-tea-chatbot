import datetime as dt

from pydantic import BaseModel

from app.schemas.reservation import ReservationRead


class ReservationActionRequest(BaseModel):
    user_id: int | None = None
    date: dt.date | None = None
    time: dt.time | None = None
    date_phrase: str | None = None
    time_phrase: str | None = None
    guests: int = 1
    special_requests: str | None = None
    guest_name: str | None = None
    guest_phone: str | None = None


class AlternativeSlot(BaseModel):
    date: dt.date
    time: dt.time


class ReservationActionResponse(BaseModel):
    available: bool
    reason: str | None = None
    alternatives: list[AlternativeSlot] = []
    reservation: ReservationRead | None = None
