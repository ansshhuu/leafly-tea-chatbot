from datetime import date, datetime, time

from app.models.reservation import Reservation
from app.services import quick_reply_service, reservation_service

FUTURE_DATE = date(2099, 6, 15)


def test_is_capability_question_matches_common_phrasings():
    for message in [
        "What can you do?",
        "what do you do",
        "How can you help me?",
        "who are you",
        "What is this?",
        "Help me please",
    ]:
        assert quick_reply_service.is_capability_question(message), message


def test_is_capability_question_ignores_plain_smalltalk():
    for message in ["thanks so much", "haha nice", "add 2 samosas", "book a table for 4"]:
        assert not quick_reply_service.is_capability_question(message), message


def test_is_greeting_matches_bare_openers():
    for message in ["hi", "Hi!", "hello", "hey there", "hii", "good morning", "Good evening!", "namaste"]:
        assert quick_reply_service.is_greeting(message), message


def test_is_greeting_ignores_longer_messages_that_merely_start_with_a_greeting():
    for message in [
        "hi, can I get 2 samosas",
        "hello can you tell me about your gluten free options",
        "hey, what time do you close today",
    ]:
        assert not quick_reply_service.is_greeting(message), message


def test_is_greeting_ignores_plain_smalltalk():
    for message in ["thanks so much", "add 2 samosas", "book a table for 4", ""]:
        assert not quick_reply_service.is_greeting(message), message


async def test_time_options_returns_all_candidates_when_all_available(db_session):
    options = await quick_reply_service.time_options(db_session, FUTURE_DATE, 2)

    assert options == ["11:00 AM", "1:00 PM", "4:00 PM", "7:00 PM"]


async def test_time_options_excludes_fully_booked_slot(db_session):
    db_session.add(
        Reservation(
            date=FUTURE_DATE, time=time(13, 0), guests=reservation_service.MAX_CAPACITY_PER_SLOT, status="confirmed"
        )
    )
    await db_session.commit()

    options = await quick_reply_service.time_options(db_session, FUTURE_DATE, 2)

    assert "1:00 PM" not in options
    assert "11:00 AM" in options
    assert len(options) == 3


async def test_time_options_ignores_cancelled_reservations(db_session):
    db_session.add(
        Reservation(
            date=FUTURE_DATE, time=time(16, 0), guests=reservation_service.MAX_CAPACITY_PER_SLOT, status="cancelled"
        )
    )
    await db_session.commit()

    options = await quick_reply_service.time_options(db_session, FUTURE_DATE, 2)

    assert "4:00 PM" in options


async def test_day_options_returns_seven_days_with_short_labels(db_session):
    now = datetime(2026, 8, 1, 10, 0, 0)
    days = await quick_reply_service.day_options(db_session, now=now)

    assert len(days) == 7
    assert days[0]["date"] == "2026-08-01"
    assert days[0]["label"] == "Sat 1"
    assert days[1]["date"] == "2026-08-02"
    assert days[1]["label"] == "Sun 2"
    assert all(day["available"] for day in days)


async def test_day_options_greys_out_a_fully_booked_day(db_session):
    now = datetime(2026, 8, 1, 10, 0, 0)
    target_day = date(2026, 8, 3)

    for hour, minute in [(11, 0), (13, 0), (16, 0), (19, 0)]:
        db_session.add(
            Reservation(
                date=target_day,
                time=time(hour, minute),
                guests=reservation_service.MAX_CAPACITY_PER_SLOT,
                status="confirmed",
            )
        )
    await db_session.commit()

    days = await quick_reply_service.day_options(db_session, now=now)
    by_date = {day["date"]: day["available"] for day in days}

    assert by_date["2026-08-03"] is False
    assert by_date["2026-08-01"] is True
