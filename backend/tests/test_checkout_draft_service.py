from app.services import checkout_draft_service as svc


def test_fresh_draft_next_step_is_name():
    assert svc.CheckoutDraft().next_step() == "name"


def test_next_step_follows_pickup_order_skipping_address():
    draft = svc.CheckoutDraft()
    assert draft.next_step() == "name"
    draft.name = "Anshu"
    assert draft.next_step() == "phone"
    draft.phone = "9876543210"
    assert draft.next_step() == "email"
    draft.email = "anshu@example.com"
    assert draft.next_step() == "fulfillment"
    draft.fulfillment = "pickup"
    assert draft.next_step() == "location"
    draft.location = "Bandra West, Mumbai"
    assert draft.next_step() == "payment"


def test_next_step_follows_delivery_order_including_address():
    draft = svc.CheckoutDraft(
        name="Anshu", phone="9876543210", email="anshu@example.com", fulfillment="delivery"
    )
    assert draft.next_step() == "address"
    draft.address = "123 MG Road"
    assert draft.next_step() == "flat_number"
    draft.flat_number_skipped = True
    assert draft.next_step() == "address_confirm"
    draft.address_confirmed = True
    assert draft.next_step() == "payment"


def test_next_step_flat_number_provided_instead_of_skipped_still_reaches_confirm():
    draft = svc.CheckoutDraft(
        name="Anshu", phone="9876543210", email="anshu@example.com", fulfillment="delivery", address="123 MG Road",
    )
    assert draft.next_step() == "flat_number"
    draft.flat_number = "A-302, Sunrise Apartments"
    assert draft.next_step() == "address_confirm"
    draft.address_confirmed = True
    assert draft.next_step() == "payment"


def test_next_step_asks_fulfillment_after_email():
    draft = svc.CheckoutDraft(name="Anshu", phone="9876543210")
    assert draft.next_step() == "email"
    draft.email = "anshu@example.com"
    assert draft.next_step() == "fulfillment"


async def test_get_or_create_draft_persists_across_calls(db_session):
    svc.clear()
    d1 = await svc.get_or_create_draft(db_session, "session-x")
    d1.name = "Anshu"
    d2 = await svc.get_or_create_draft(db_session, "session-x")
    assert d2 is d1
    assert d2.name == "Anshu"
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
    draft.name = "Anshu"
    draft.phone = "9876543210"
    await svc.sync_draft(db_session, "session-restart")

    svc.clear()  # simulates a fresh process - memory cache is empty

    reloaded = await svc.get_draft(db_session, "session-restart")
    assert reloaded is not None
    assert reloaded.name == "Anshu"
    assert reloaded.phone == "9876543210"
    svc.clear()
