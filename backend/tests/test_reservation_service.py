import asyncio
from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock

from app.models.reservation import Reservation
from app.services import email_service, reservation_service as rec

FUTURE_DATE = date(2099, 6, 15)
FUTURE_FRIDAY = date(2099, 6, 19)
FUTURE_SUNDAY = date(2099, 6, 21)


def test_resolve_requested_datetime_relative_date_and_clean_time():
    now = datetime(2026, 7, 30, 10, 0, 0)
    resolved = rec.resolve_requested_datetime("tomorrow", "7pm", now=now)
    assert resolved == (date(2026, 7, 31), time(19, 0))


def test_resolve_requested_datetime_strips_this_next_filler():
    now = datetime(2026, 7, 30, 10, 0, 0)
    resolved = rec.resolve_requested_datetime("this Saturday", "evening", now=now)
    assert resolved is not None
    resolved_date, resolved_time = resolved
    assert resolved_date.weekday() == 5
    assert resolved_time == time(19, 0)


def test_resolve_requested_datetime_time_only_rolls_to_tomorrow_if_past():
    now = datetime(2026, 7, 30, 21, 0, 0)
    resolved = rec.resolve_requested_datetime(None, "7pm", now=now)
    assert resolved == (date(2026, 7, 31), time(19, 0))


def test_resolve_requested_datetime_returns_none_when_unparseable():
    now = datetime(2026, 7, 30, 10, 0, 0)
    assert rec.resolve_requested_datetime("blah blah", "whenever", now=now) is None
    assert rec.resolve_requested_datetime(None, None, now=now) is None


async def test_check_availability_rejects_past_date(db_session):
    result = await rec.check_availability(db_session, date(2020, 1, 1), time(19, 0), 2)
    assert result["available"] is False
    assert "past" in result["reason"]


async def test_check_availability_rejects_outside_operating_hours(db_session):
    result = await rec.check_availability(db_session, FUTURE_DATE, time(6, 0), 2)
    assert result["available"] is False
    assert "operating hours" in result["reason"]


async def test_check_availability_uses_injected_now_not_the_real_wall_clock(db_session):
    morning = datetime(2026, 8, 1, 8, 0, 0)

    still_future = await rec.check_availability(db_session, date(2026, 8, 1), time(19, 0), 2, now=morning)
    assert still_future["available"] is True

    already_past = await rec.check_availability(db_session, date(2026, 8, 1), time(7, 0), 2, now=morning)
    assert already_past["available"] is False
    assert "past" in already_past["reason"]

    evening = datetime(2026, 8, 1, 21, 0, 0)
    now_past = await rec.check_availability(db_session, date(2026, 8, 1), time(19, 0), 2, now=evening)
    assert now_past["available"] is False


async def test_check_availability_accepts_open_slot(db_session):
    result = await rec.check_availability(db_session, FUTURE_DATE, time(19, 0), 2)
    assert result["available"] is True
    assert result["reason"] is None


async def test_check_availability_uses_later_friday_hours(db_session):
    monday_late = await rec.check_availability(db_session, FUTURE_DATE, time(22, 30), 2)
    assert monday_late["available"] is False

    friday_late = await rec.check_availability(db_session, FUTURE_FRIDAY, time(22, 30), 2)
    assert friday_late["available"] is True


async def test_check_availability_uses_later_sunday_opening(db_session):
    result = await rec.check_availability(db_session, FUTURE_SUNDAY, time(8, 30), 2)
    assert result["available"] is False
    assert "operating hours" in result["reason"]


async def test_check_availability_uses_per_location_hours(db_session):
    # Bandra (default) is closed at 7:00 AM and on Sunday before 9:00 AM;
    # Indiranagar opens at 7:30 AM every day, including Sunday.
    bandra_early = await rec.check_availability(db_session, FUTURE_DATE, time(7, 0), 2)
    assert bandra_early["available"] is False

    indiranagar_early = await rec.check_availability(
        db_session, FUTURE_DATE, time(7, 30), 2, location="Indiranagar, Bengaluru"
    )
    assert indiranagar_early["available"] is True

    bandra_sunday_early = await rec.check_availability(db_session, FUTURE_SUNDAY, time(8, 0), 2)
    assert bandra_sunday_early["available"] is False

    indiranagar_sunday_early = await rec.check_availability(
        db_session, FUTURE_SUNDAY, time(8, 0), 2, location="Indiranagar, Bengaluru"
    )
    assert indiranagar_sunday_early["available"] is True


async def test_capacity_is_isolated_per_location(db_session):
    db_session.add(
        Reservation(
            date=FUTURE_DATE, time=time(19, 0), guests=rec.MAX_CAPACITY_PER_SLOT,
            status="confirmed", location="Bandra West, Mumbai",
        )
    )
    await db_session.commit()

    bandra_full = await rec.check_availability(db_session, FUTURE_DATE, time(19, 0), 2, location="Bandra West, Mumbai")
    assert bandra_full["available"] is False

    koregaon_still_open = await rec.check_availability(
        db_session, FUTURE_DATE, time(19, 0), 2, location="Koregaon Park, Pune"
    )
    assert koregaon_still_open["available"] is True


async def test_check_availability_rejects_over_capacity_and_suggests_alternatives(db_session):
    db_session.add(
        Reservation(date=FUTURE_DATE, time=time(19, 0), guests=rec.MAX_CAPACITY_PER_SLOT, status="confirmed")
    )
    await db_session.commit()

    result = await rec.check_availability(db_session, FUTURE_DATE, time(19, 0), 2)

    assert result["available"] is False
    assert "fully booked" in result["reason"]
    assert len(result["alternatives"]) > 0


async def test_check_availability_ignores_cancelled_reservations(db_session):
    db_session.add(
        Reservation(date=FUTURE_DATE, time=time(19, 0), guests=rec.MAX_CAPACITY_PER_SLOT, status="cancelled")
    )
    await db_session.commit()

    result = await rec.check_availability(db_session, FUTURE_DATE, time(19, 0), 2)

    assert result["available"] is True


async def test_create_reservation_succeeds_when_available(db_session):
    reservation, availability = await rec.create_reservation(db_session, None, FUTURE_DATE, time(18, 0), 4, "birthday")

    assert availability["available"] is True
    assert reservation is not None
    assert reservation.guests == 4
    assert reservation.special_requests == "birthday"
    assert reservation.status == "confirmed"


async def test_create_reservation_fails_without_persisting_when_unavailable(db_session):
    reservation, availability = await rec.create_reservation(db_session, None, date(2020, 1, 1), time(18, 0), 2)

    assert reservation is None
    assert availability["available"] is False


def test_resolve_date_only_defaults_to_today_when_no_phrase():
    now = datetime(2026, 7, 30, 10, 0, 0)
    assert rec.resolve_date_only(None, now=now) == date(2026, 7, 30)


def test_resolve_date_only_parses_a_normal_phrase():
    now = datetime(2026, 7, 30, 10, 0, 0)
    assert rec.resolve_date_only("tomorrow", now=now) == date(2026, 7, 31)


def test_resolve_date_only_returns_none_when_unparseable():
    now = datetime(2026, 7, 30, 10, 0, 0)
    assert rec.resolve_date_only("blah blah", now=now) is None


def test_resolve_date_only_understands_bare_weekend():
    thursday = datetime(2026, 7, 30, 10, 0, 0)
    resolved = rec.resolve_date_only("weekend", now=thursday)
    assert resolved is not None
    assert resolved.weekday() == 5

    resolved_this_weekend = rec.resolve_date_only("this weekend", now=thursday)
    assert resolved_this_weekend == resolved

    saturday = datetime(2026, 8, 1, 10, 0, 0)
    assert rec.resolve_date_only("weekend", now=saturday) == saturday.date()


def test_parse_guest_count_extracts_digits():
    assert rec.parse_guest_count("4") == 4
    assert rec.parse_guest_count("8+") == 8
    assert rec.parse_guest_count("we are 6 people") == 6
    assert rec.parse_guest_count("no idea") is None
    assert rec.parse_guest_count("a lot") is None
    assert rec.parse_guest_count("0") == 0
    assert rec.parse_guest_count("-5") == -5


def test_validate_guest_count_accepts_valid_range():
    assert rec.validate_guest_count(1) is None
    assert rec.validate_guest_count(8) is None
    assert rec.validate_guest_count(40) is None


def test_validate_guest_count_rejects_non_numeric():
    assert rec.validate_guest_count(None) == rec.GUEST_COUNT_INVALID_MESSAGE


def test_validate_guest_count_rejects_zero_and_negative():
    assert rec.validate_guest_count(0) == rec.GUEST_COUNT_INVALID_MESSAGE
    assert rec.validate_guest_count(-5) == rec.GUEST_COUNT_INVALID_MESSAGE


def test_validate_guest_count_rejects_above_capacity_with_call_us_message():
    from app.core.config import CAFE_PHONE, MAX_CAPACITY_PER_SLOT

    error = rec.validate_guest_count(100)
    assert error == rec.GUEST_COUNT_TOO_HIGH_MESSAGE
    assert str(MAX_CAPACITY_PER_SLOT) in error
    assert CAFE_PHONE in error
    assert rec.validate_guest_count(MAX_CAPACITY_PER_SLOT + 1) == rec.GUEST_COUNT_TOO_HIGH_MESSAGE


async def _make_confirmed_reservation(db_session, reservation_datetime: datetime, **overrides) -> Reservation:
    defaults = dict(
        date=reservation_datetime.date(),
        time=reservation_datetime.time(),
        guests=2,
        guest_name="Anshu",
        guest_email="anshu@example.com",
        status="confirmed",
        payment_status="mock_paid",
        reminder_sent=False,
    )
    defaults.update(overrides)
    reservation = Reservation(**defaults)
    db_session.add(reservation)
    await db_session.commit()
    await db_session.refresh(reservation)
    return reservation


async def test_check_and_send_reminders_sends_for_booking_about_two_hours_out(db_session, monkeypatch):
    fake_send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_reservation_reminder", fake_send)

    now = datetime(2026, 8, 3, 10, 0, 0)
    reservation = await _make_confirmed_reservation(db_session, now + timedelta(hours=2))

    sent = await rec.check_and_send_reminders(db_session, now=now)
    await asyncio.sleep(0)

    assert sent == 1
    fake_send.assert_awaited_once()
    await db_session.refresh(reservation)
    assert reservation.reminder_sent is True


async def test_check_and_send_reminders_skips_bookings_outside_the_window(db_session, monkeypatch):
    fake_send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_reservation_reminder", fake_send)

    now = datetime(2026, 8, 3, 10, 0, 0)
    await _make_confirmed_reservation(db_session, now + timedelta(days=1))
    await _make_confirmed_reservation(db_session, now + timedelta(minutes=10))

    sent = await rec.check_and_send_reminders(db_session, now=now)

    assert sent == 0
    fake_send.assert_not_awaited()


async def test_check_and_send_reminders_never_resends_once_flagged(db_session, monkeypatch):
    fake_send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_reservation_reminder", fake_send)

    now = datetime(2026, 8, 3, 10, 0, 0)
    await _make_confirmed_reservation(db_session, now + timedelta(hours=2), reminder_sent=True)

    sent = await rec.check_and_send_reminders(db_session, now=now)

    assert sent == 0
    fake_send.assert_not_awaited()


async def test_check_and_send_reminders_skips_when_no_email_known(db_session, monkeypatch):
    fake_send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_service, "send_reservation_reminder", fake_send)

    now = datetime(2026, 8, 3, 10, 0, 0)
    await _make_confirmed_reservation(db_session, now + timedelta(hours=2), guest_email=None)

    sent = await rec.check_and_send_reminders(db_session, now=now)

    assert sent == 0
    fake_send.assert_not_awaited()
