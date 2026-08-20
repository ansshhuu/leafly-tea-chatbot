from datetime import date, time

from pydantic import BaseModel, ConfigDict


class ReservationBase(BaseModel):
    user_id: int | None = None
    date: date
    time: time
    guests: int = 1
    special_requests: str | None = None
    guest_name: str | None = None
    guest_phone: str | None = None
    status: str = "pending"


class ReservationCreate(ReservationBase):
    pass


class ReservationRead(ReservationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
