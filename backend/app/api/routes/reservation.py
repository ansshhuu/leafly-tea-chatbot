from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.reservation import Reservation
from app.schemas.reservation import ReservationRead
from app.schemas.reservation_action import ReservationActionRequest, ReservationActionResponse
from app.services import reservation_service

router = APIRouter()


@router.post("/action", response_model=ReservationActionResponse)
async def reservation_action(
    payload: ReservationActionRequest, db: AsyncSession = Depends(get_db)
) -> ReservationActionResponse:
    if payload.date is not None and payload.time is not None:
        slot_date, slot_time = payload.date, payload.time
    else:
        resolved = reservation_service.resolve_requested_datetime(payload.date_phrase, payload.time_phrase)
        if resolved is None:
            raise HTTPException(status_code=422, detail="Could not resolve a date/time from the given input")
        slot_date, slot_time = resolved

    reservation, availability = await reservation_service.create_reservation(
        db,
        payload.user_id,
        slot_date,
        slot_time,
        payload.guests,
        payload.special_requests,
        payload.guest_name,
        payload.guest_phone,
    )

    return ReservationActionResponse(
        available=availability["available"],
        reason=availability["reason"],
        alternatives=availability["alternatives"],
        reservation=reservation,
    )


@router.get("/{reservation_id}", response_model=ReservationRead)
async def get_reservation(reservation_id: int, db: AsyncSession = Depends(get_db)) -> Reservation:
    reservation = await db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    return reservation
