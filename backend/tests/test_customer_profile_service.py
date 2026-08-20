from app.models.menu_item import MenuItem
from app.services import customer_profile_service, order_service


def test_detect_dietary_preference_matches_common_phrasings():
    assert customer_profile_service.detect_dietary_preference("I'm vegan, what do you have?") == "vegan"
    assert customer_profile_service.detect_dietary_preference("Anything gluten-free?") == "gluten_free"
    assert customer_profile_service.detect_dietary_preference("I'm vegetarian") == "veg"
    assert customer_profile_service.detect_dietary_preference("what's on the menu?") is None


def test_detect_seating_preference_matches_common_phrasings():
    assert customer_profile_service.detect_seating_preference("Can I get a window seat?") == "window seat"
    assert customer_profile_service.detect_seating_preference("Is there outdoor seating?") == "outdoor"
    assert customer_profile_service.detect_seating_preference("book a table for 2") is None


async def test_get_or_create_profile_persists_and_reuses(db_session):
    profile1 = await customer_profile_service.get_or_create_profile(db_session, "9876543210", name="Anshu")
    profile2 = await customer_profile_service.get_or_create_profile(db_session, "9876543210")

    assert profile1.id == profile2.id
    assert profile2.name == "Anshu"


async def test_remember_dietary_and_seating_preference(db_session):
    await customer_profile_service.remember_dietary_preference(db_session, "9876543210", "vegan")
    await customer_profile_service.remember_seating_preference(db_session, "9876543210", "window seat")

    profile = await customer_profile_service.get_profile(db_session, "9876543210")
    assert profile.dietary_preference == "vegan"
    assert profile.preferred_seating == "window seat"


async def _seed_menu(db_session):
    items = [
        MenuItem(name="Filter Coffee", price=70, category="Hot Beverages", available=True),
        MenuItem(name="Samosa", price=60, category="Snacks", available=True),
    ]
    db_session.add_all(items)
    await db_session.commit()
    for item in items:
        await db_session.refresh(item)
    return {item.name: item for item in items}


async def test_get_favorite_item_name_requires_minimum_repeat_volume(db_session):
    menu = await _seed_menu(db_session)
    phone = "9876543210"

    order = await order_service.get_or_create_draft_order(db_session, "profile-session-1")
    await order_service.add_item(db_session, order.id, menu["Filter Coffee"].id, 1)
    await order_service.checkout(db_session, order.id, guest_phone=phone)

    assert await customer_profile_service.get_favorite_item_name(db_session, phone) is None


async def test_get_favorite_item_name_returns_most_ordered(db_session):
    menu = await _seed_menu(db_session)
    phone = "9876543211"

    order1 = await order_service.get_or_create_draft_order(db_session, "profile-session-2")
    await order_service.add_item(db_session, order1.id, menu["Filter Coffee"].id, 2)
    await order_service.checkout(db_session, order1.id, guest_phone=phone)

    order2 = await order_service.get_or_create_draft_order(db_session, "profile-session-3")
    await order_service.add_item(db_session, order2.id, menu["Samosa"].id, 1)
    await order_service.checkout(db_session, order2.id, guest_phone=phone)

    favorite = await customer_profile_service.get_favorite_item_name(db_session, phone)
    assert favorite == "Filter Coffee"


async def test_build_welcome_back_message_none_for_unknown_phone(db_session):
    message = await customer_profile_service.build_welcome_back_message(db_session, "0000000000", "Anshu")
    assert message is None


async def test_build_welcome_back_message_includes_favorite_item(db_session):
    menu = await _seed_menu(db_session)
    phone = "9876543212"
    order = await order_service.get_or_create_draft_order(db_session, "profile-session-4")
    await order_service.add_item(db_session, order.id, menu["Filter Coffee"].id, 2)
    await order_service.checkout(db_session, order.id, guest_phone=phone)

    message = await customer_profile_service.build_welcome_back_message(db_session, phone, "Anshu")

    assert message is not None
    assert "Anshu" in message
    assert "Filter Coffee" in message
