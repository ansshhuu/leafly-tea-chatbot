from datetime import date, time

from app.services import reservation_draft_service as svc


def test_fresh_draft_next_step_is_location():
    assert svc.ReservationDraft().next_step() == "location"


def test_next_step_follows_the_full_order():
    draft = svc.ReservationDraft()
    assert draft.next_step() == "location"
    draft.location = "Bandra West, Mumbai"
    assert draft.next_step() == "date"
    draft.date = date(2026, 8, 3)
    assert draft.next_step() == "time"
    draft.time = time(19, 0)
    assert draft.next_step() == "guests"
    draft.guests = 2
    assert draft.next_step() == "name"
    draft.name = "Anshu"
    assert draft.next_step() == "phone"
    draft.phone = "9876543210"
    assert draft.next_step() == "email"
    draft.email = "anshu@example.com"
    assert draft.next_step() == "special_requests"
    draft.special_requests = "window seat"
    assert draft.next_step() == "confirm"


def test_next_step_asks_special_requests_after_email():
    draft = svc.ReservationDraft(
        location="Bandra West, Mumbai",
        date=date(2026, 8, 3), time=time(19, 0), guests=2, name="Anshu", phone="9876543210"
    )
    assert draft.next_step() == "email"
    draft.email = "anshu@example.com"
    assert draft.next_step() == "special_requests"


def test_special_requests_skip_flag_advances_past_it_without_a_value():
    draft = svc.ReservationDraft(
        location="Bandra West, Mumbai",
        date=date(2026, 8, 3),
        time=time(19, 0),
        guests=2,
        name="Anshu",
        phone="9876543210",
        email="anshu@example.com",
    )
    assert draft.next_step() == "special_requests"
    draft.special_requests_skipped = True
    assert draft.next_step() == "confirm"


async def test_get_or_create_draft_persists_across_calls(db_session):
    svc.clear()
    d1 = await svc.get_or_create_draft(db_session, "session-x")
    d1.date = date(2026, 8, 3)
    d2 = await svc.get_or_create_draft(db_session, "session-x")
    assert d2 is d1
    assert d2.date == date(2026, 8, 3)
    svc.clear()


async def test_clear_draft_removes_only_that_session(db_session):
    svc.clear()
    await svc.get_or_create_draft(db_session, "session-a")
    await svc.get_or_create_draft(db_session, "session-b")
    svc.clear_draft("session-a")
    assert await svc.get_draft(db_session, "session-a") is None
    assert await svc.get_draft(db_session, "session-b") is not None
    svc.clear()


async def test_draft_survives_memory_cache_eviction_via_db(db_session):
    svc.clear()
    draft = await svc.get_or_create_draft(db_session, "session-restart")
    draft.date = date(2026, 8, 3)
    draft.time = time(19, 0)
    draft.guests = 4
    await svc.sync_draft(db_session, "session-restart")

    svc.clear()  # simulates a fresh process - memory cache is empty

    reloaded = await svc.get_draft(db_session, "session-restart")
    assert reloaded is not None
    assert reloaded.date == date(2026, 8, 3)
    assert reloaded.time == time(19, 0)
    assert reloaded.guests == 4
    svc.clear()


def test_describe_progress_lists_collected_fields_and_next_step():
    draft = svc.ReservationDraft(location="Bandra West, Mumbai", date=date(2026, 8, 3), time=time(19, 0))
    description = svc.describe_progress(draft)
    assert "2026-08-03" in description
    assert "07:00 PM" in description
    assert "guests" in description


def test_describe_progress_mentions_confirm_once_everything_else_is_collected():
    draft = svc.ReservationDraft(
        location="Bandra West, Mumbai",
        date=date(2026, 8, 3),
        time=time(19, 0),
        guests=2,
        name="Anshu",
        phone="9876543210",
        email="anshu@example.com",
        is_birthday=False,
        special_requests_skipped=True,
    )
    assert draft.next_step() == "confirm"
    description = svc.describe_progress(draft)
    assert description is not None
    assert "confirm" in description
