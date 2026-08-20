import logging
import re
from datetime import date, datetime, time, timedelta

import dateparser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    CAFE_HOURS_BY_LOCATION,
    CAFE_PHONE,
    DEFAULT_LOCATION_NAME,
    MAX_CAPACITY_PER_SLOT,
    SLOT_DURATION_MINUTES,
    settings,
)
from app.db.session import AsyncSessionLocal
from app.models.reservation import Reservation
from app.services import email_service

logger = logging.getLogger(__name__)

_TIME_WORD_DEFAULTS = {
    "morning": time(9, 0),
    "breakfast": time(9, 0),
    "noon": time(12, 0),
    "lunch": time(13, 0),
    "afternoon": time(14, 0),
    "evening": time(19, 0),
    "dinner": time(20, 0),
    "night": time(20, 30),
    "midnight": time(0, 0),
}

_DATE_FILLER_RE = re.compile(r"\b(this|next|coming|upcoming)\b", re.IGNORECASE)


def _next_weekend_date(now: datetime) -> date:
    weekday = now.weekday()
    if weekday in (5, 6):
        return now.date()
    days_until_saturday = 5 - weekday
    return (now + timedelta(days=days_until_saturday)).date()


def _hours_for_date(d: date, location: str | None = None) -> tuple[time, time]:
    weekday_name = d.strftime("%A").lower()
    hours = CAFE_HOURS_BY_LOCATION.get(location or DEFAULT_LOCATION_NAME, CAFE_HOURS_BY_LOCATION[DEFAULT_LOCATION_NAME])[
        weekday_name
    ]
    open_h, open_m = (int(x) for x in hours["open"].split(":"))
    close_h, close_m = (int(x) for x in hours["close"].split(":"))
    return time(open_h, open_m), time(close_h, close_m)


def _parse_date_phrase(date_phrase: str, now: datetime) -> date | None:
    cleaned = _DATE_FILLER_RE.sub("", date_phrase).strip() or date_phrase
    if cleaned.lower() == "weekend":
        return _next_weekend_date(now)
    parsed = dateparser.parse(cleaned, settings={"PREFER_DATES_FROM": "future", "RELATIVE_BASE": now})
    return parsed.date() if parsed else None


def resolve_date_only(date_phrase: str | None, now: datetime | None = None) -> date | None:
    now = now or datetime.now()
    if not date_phrase:
        return now.date()
    return _parse_date_phrase(date_phrase, now)


def _parse_time_phrase(time_phrase: str, now: datetime) -> time | None:
    key = time_phrase.strip().lower()
    if key in _TIME_WORD_DEFAULTS:
        return _TIME_WORD_DEFAULTS[key]
    parsed = dateparser.parse(time_phrase, settings={"RELATIVE_BASE": now})
    return parsed.time() if parsed else None


def resolve_time_only(time_phrase: str | None, now: datetime | None = None) -> time | None:
    now = now or datetime.now()
    if not time_phrase:
        return None
    return _parse_time_phrase(time_phrase, now)


_GUEST_COUNT_RE = re.compile(r"-?\d+")

GUEST_COUNT_INVALID_MESSAGE = "Please enter a number of guests between 1 and 40."
GUEST_COUNT_TOO_HIGH_MESSAGE = (
    f"We can accommodate up to {MAX_CAPACITY_PER_SLOT} guests per booking. "
    f"For larger groups, please call us directly at {CAFE_PHONE}."
)


def parse_guest_count(text: str) -> int | None:
    """Pure extraction, no range check - a non-numeric message (e.g. "a lot",
    "many") returns None. Validation is a separate step (validate_guest_count)
    so the server, not the AI, decides what counts as an acceptable range."""
    match = _GUEST_COUNT_RE.search(text)
    return int(match.group()) if match else None


def validate_guest_count(guests: int | None) -> str | None:
    """Returns None if guests is a valid party size, otherwise a customer-
    facing message explaining why (and, over the cap, what to do instead)."""
    if guests is None or guests <= 0:
        return GUEST_COUNT_INVALID_MESSAGE
    if guests > MAX_CAPACITY_PER_SLOT:
        return GUEST_COUNT_TOO_HIGH_MESSAGE
    return None


def resolve_requested_datetime(
    date_phrase: str | None, time_phrase: str | None, now: datetime | None = None
) -> tuple[date, time] | None:
    now = now or datetime.now()

    if not date_phrase and not time_phrase:
        return None

    resolved_date = _parse_date_phrase(date_phrase, now) if date_phrase else now.date()
    resolved_time = _parse_time_phrase(time_phrase, now) if time_phrase else None

    if resolved_date is None or resolved_time is None:
        return None

    if not date_phrase and datetime.combine(resolved_date, resolved_time) < now:
        resolved_date = resolved_date + timedelta(days=1)

    return resolved_date, resolved_time


def _slot_bounds(slot_date: date, slot_time: time) -> tuple[datetime, datetime]:
    start = datetime.combine(slot_date, slot_time)
    return start, start + timedelta(minutes=SLOT_DURATION_MINUTES)


async def _guests_booked_in_window(
    db: AsyncSession, slot_date: date, start: datetime, end: datetime, location: str | None = None
) -> int:
    # Capacity is per-branch, not restaurant-wide - a booking at Indiranagar
    # must never count against Bandra's slot, and vice versa. Reservations
    # made before locations existed have location=None; treat those as the
    # default (Bandra) branch so old bookings still count there.
    location = location or DEFAULT_LOCATION_NAME
    stmt = select(Reservation).where(Reservation.date == slot_date, Reservation.status != "cancelled")
    result = await db.execute(stmt)
    total = 0
    for res in result.scalars().all():
        if (res.location or DEFAULT_LOCATION_NAME) != location:
            continue
        res_start, res_end = _slot_bounds(res.date, res.time)
        if res_start < end and res_end > start:
            total += res.guests
    return total


async def _find_alternative_slots(
    db: AsyncSession, slot_date: date, slot_time: time, guests: int, max_suggestions: int = 3, location: str | None = None
) -> list[dict]:
    open_time, close_time = _hours_for_date(slot_date, location)
    alternatives = []
    for step in range(1, 6):
        for delta_minutes in (step * SLOT_DURATION_MINUTES, -step * SLOT_DURATION_MINUTES):
            candidate_dt = datetime.combine(slot_date, slot_time) + timedelta(minutes=delta_minutes)
            if candidate_dt.date() != slot_date:
                continue
            if not (open_time <= candidate_dt.time() < close_time):
                continue

            start, end = _slot_bounds(candidate_dt.date(), candidate_dt.time())
            booked = await _guests_booked_in_window(db, candidate_dt.date(), start, end, location)
            if booked + guests <= MAX_CAPACITY_PER_SLOT:
                alternatives.append({"date": candidate_dt.date(), "time": candidate_dt.time()})
                if len(alternatives) >= max_suggestions:
                    return alternatives

    return alternatives


async def check_availability(
    db: AsyncSession, slot_date: date, slot_time: time, guests: int, now: datetime | None = None, location: str | None = None
) -> dict:
    now = now or datetime.now()

    if slot_date < now.date() or (slot_date == now.date() and slot_time < now.time()):
        return {"available": False, "reason": "that date/time is in the past", "alternatives": []}

    open_time, close_time = _hours_for_date(slot_date, location)
    if not (open_time <= slot_time < close_time):
        return {
            "available": False,
            "reason": f"outside operating hours ({open_time.strftime('%I:%M %p')}-{close_time.strftime('%I:%M %p')})",
            "alternatives": [],
        }

    start, end = _slot_bounds(slot_date, slot_time)
    booked = await _guests_booked_in_window(db, slot_date, start, end, location)

    if booked + guests > MAX_CAPACITY_PER_SLOT:
        alternatives = await _find_alternative_slots(db, slot_date, slot_time, guests, location=location)
        return {"available": False, "reason": "fully booked for that time slot", "alternatives": alternatives}

    return {"available": True, "reason": None, "alternatives": []}


async def create_reservation(
    db: AsyncSession,
    user_id: int | None,
    slot_date: date,
    slot_time: time,
    guests: int,
    special_requests: str | None = None,
    guest_name: str | None = None,
    guest_phone: str | None = None,
    now: datetime | None = None,
    payment_status: str = "pending",
    guest_email: str | None = None,
    is_birthday: bool = False,
    location: str | None = None,
) -> tuple[Reservation | None, dict]:
    availability = await check_availability(db, slot_date, slot_time, guests, now=now, location=location)
    if not availability["available"]:
        return None, availability

    reservation = Reservation(
        user_id=user_id,
        date=slot_date,
        time=slot_time,
        guests=guests,
        special_requests=special_requests,
        guest_name=guest_name,
        guest_phone=guest_phone,
        location=location or DEFAULT_LOCATION_NAME,
        guest_email=guest_email,
        is_birthday=is_birthday,
        status="confirmed",
        payment_status=payment_status,
    )
    db.add(reservation)
    await db.commit()
    await db.refresh(reservation)
    return reservation, availability


REMINDER_LEAD_MINUTES = 120
REMINDER_WINDOW_MINUTES = 30


async def check_and_send_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now()
    window_start = now + timedelta(minutes=REMINDER_LEAD_MINUTES - REMINDER_WINDOW_MINUTES)
    window_end = now + timedelta(minutes=REMINDER_LEAD_MINUTES + REMINDER_WINDOW_MINUTES)

    stmt = select(Reservation).where(
        Reservation.status == "confirmed",
        Reservation.reminder_sent.is_(False),
        Reservation.guest_email.isnot(None),
        Reservation.date.in_([window_start.date(), window_end.date()]),
    )
    result = await db.execute(stmt)

    sent = 0
    for reservation in result.scalars().all():
        reservation_dt = datetime.combine(reservation.date, reservation.time)
        if not (window_start <= reservation_dt <= window_end):
            continue

        reservation.reminder_sent = True
        await db.commit()

        logger.info("reminder.due reservation_id=%s reservation_at=%s", reservation.id, reservation_dt)
        await email_service.send_reservation_reminder(
            reservation.guest_email,
            reservation.guest_name,
            reservation.id,
            reservation.date.strftime("%b %d, %Y"),
            reservation.time.strftime("%I:%M %p"),
            reservation.guests,
        )
        sent += 1

    return sent


_last_reminder_check: datetime | None = None
_REMINDER_CHECK_MIN_INTERVAL_SECONDS = 60


async def run_reminder_check() -> None:
    if settings.test_mode:
        return

    global _last_reminder_check
    now = datetime.now()
    if _last_reminder_check is not None:
        elapsed = (now - _last_reminder_check).total_seconds()
        if elapsed < _REMINDER_CHECK_MIN_INTERVAL_SECONDS:
            return
    _last_reminder_check = now

    async with AsyncSessionLocal() as db:
        try:
            sent = await check_and_send_reminders(db, now=now)
            if sent:
                logger.info("reminder.check_complete sent=%s", sent)
        except Exception:
            logger.exception("reminder.check_failed")
