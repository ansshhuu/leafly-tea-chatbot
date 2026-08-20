import pytest

from app.models.menu_item import MenuItem
from app.services import order_service


async def _seed_menu(db_session):
    items = [
        MenuItem(name="Masala Chai", price=80, category="Hot Beverages", available=True),
        MenuItem(name="Cutting Chai", price=50, category="Hot Beverages", available=True),
        MenuItem(name="Samosa", price=60, category="Snacks", available=True),
        MenuItem(name="Old Special", price=40, category="Snacks", available=False),
    ]
    db_session.add_all(items)
    await db_session.commit()
    for item in items:
        await db_session.refresh(item)
    return {item.name: item for item in items}


async def test_get_or_create_draft_order_reuses_existing_draft(db_session):
    order1 = await order_service.get_or_create_draft_order(db_session, "session-1")
    order2 = await order_service.get_or_create_draft_order(db_session, "session-1")

    assert order1.id == order2.id
    assert order1.status == "draft"


async def test_resolve_menu_item_exact_and_substring_match(db_session):
    menu = await _seed_menu(db_session)

    exact = await order_service.resolve_menu_item(db_session, "Samosa")
    assert exact.id == menu["Samosa"].id

    substring = await order_service.resolve_menu_item(db_session, "samosas")
    assert substring.id == menu["Samosa"].id


async def test_resolve_menu_item_fuzzy_typo(db_session):
    menu = await _seed_menu(db_session)

    fuzzy = await order_service.resolve_menu_item(db_session, "masala chay")
    assert fuzzy.id == menu["Masala Chai"].id


async def test_resolve_menu_item_ignores_unavailable_items(db_session):
    await _seed_menu(db_session)

    result = await order_service.resolve_menu_item(db_session, "Old Special")
    assert result is None


async def test_resolve_menu_item_returns_none_for_nonsense(db_session):
    await _seed_menu(db_session)

    result = await order_service.resolve_menu_item(db_session, "xyzzy quux")
    assert result is None


async def test_add_item_creates_then_increments_quantity(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-2")

    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 2)
    order_item = await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)

    assert order_item.quantity == 3


async def test_add_item_rejects_unavailable_menu_item(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-3")

    with pytest.raises(order_service.OrderError):
        await order_service.add_item(db_session, order.id, menu["Old Special"].id, 1)


async def test_resolve_order_line_item_scoped_to_cart_not_whole_menu(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-chai")
    await order_service.add_item(db_session, order.id, menu["Masala Chai"].id, 1)

    resolved = await order_service.resolve_order_line_item(db_session, order.id, "the chai")

    assert resolved.id == menu["Masala Chai"].id


async def test_resolve_order_line_item_returns_none_when_not_in_cart(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-empty-cart")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)

    resolved = await order_service.resolve_order_line_item(db_session, order.id, "masala chai")

    assert resolved is None


async def test_clear_cart_empties_all_items(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-clear")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 2)
    await order_service.add_item(db_session, order.id, menu["Masala Chai"].id, 1)

    cleared_count = await order_service.clear_cart(db_session, order.id)
    summary = await order_service.get_order_summary(db_session, order.id)

    assert cleared_count == 2
    assert summary["items"] == []
    assert summary["total"] == 0.0


async def test_clear_cart_on_already_empty_cart_is_a_noop(db_session):
    await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-clear-empty")

    cleared_count = await order_service.clear_cart(db_session, order.id)

    assert cleared_count == 0


async def test_resolve_add_entry_normalizes_spacing_and_case(db_session):
    menu = await _seed_menu(db_session)

    resolved = await order_service.resolve_add_entry(db_session, "  MASALA   chai  ")

    assert resolved["type"] == "match"
    assert resolved["item"].id == menu["Masala Chai"].id


async def test_resolve_add_entry_splits_two_real_items_typed_together(db_session):
    menu = await _seed_menu(db_session)
    vada_pav = MenuItem(name="Vada Pav", price=70, category="Snacks", available=True)
    db_session.add(vada_pav)
    await db_session.commit()
    await db_session.refresh(vada_pav)

    # "samosa pav" isn't a real menu item, but is unambiguously Samosa + Vada
    # Pav typed together - must be offered as a split, not rejected as a
    # fabricated "samosapav" being unavailable.
    resolved = await order_service.resolve_add_entry(db_session, "samosa pav")

    assert resolved["type"] == "split"
    assert {item.id for item in resolved["items"]} == {menu["Samosa"].id, vada_pav.id}


async def test_resolve_add_entry_vague_category_term_does_not_auto_add(db_session):
    # Regression: "cold drink" is a category, not an item name, but scored
    # close enough to "Cold Brew" under the old single fuzzy-match cutoff to
    # get silently auto-added. It must fall to "not_found" (with that item
    # only offered as a clarifying suggestion) instead of being auto-matched.
    menu = await _seed_menu(db_session)
    db_session.add(MenuItem(name="Cold Brew", price=160, category="Cold Beverages", available=True))
    await db_session.commit()

    resolved = await order_service.resolve_add_entry(db_session, "cold drink")

    assert resolved["type"] == "not_found"
    assert menu["Samosa"].id not in {item.id for item in resolved["suggestions"]}


async def test_resolve_add_entry_no_match_or_split_returns_close_suggestions(db_session):
    await _seed_menu(db_session)

    resolved = await order_service.resolve_add_entry(db_session, "xyzzy quux")

    assert resolved["type"] == "not_found"


async def test_resolve_add_entry_long_description_gets_no_garbled_suggestions(db_session):
    # Regression: a long, sentence-like item_name (e.g. an image description
    # like "vegetable stir-fried noodles with tofu" that leaked into an
    # order_action from conversation context) must not fuzzy-match against
    # unrelated short menu item names just by coincidental character overlap.
    await _seed_menu(db_session)

    resolved = await order_service.resolve_add_entry(db_session, "vegetable stir-fried noodles with tofu")

    assert resolved["type"] == "not_found"
    assert resolved["suggestions"] == []


async def test_remove_item(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-4")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)

    removed = await order_service.remove_item(db_session, order.id, menu["Samosa"].id)
    removed_again = await order_service.remove_item(db_session, order.id, menu["Samosa"].id)

    assert removed is True
    assert removed_again is False


async def test_update_quantity_zero_removes_item(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-5")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 2)

    result = await order_service.update_quantity(db_session, order.id, menu["Samosa"].id, 0)

    summary = await order_service.get_order_summary(db_session, order.id)
    assert result is None
    assert summary["items"] == []


async def test_calculate_totals_applies_tax_rate(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-6")
    await order_service.add_item(db_session, order.id, menu["Masala Chai"].id, 2)
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)

    totals = await order_service.calculate_totals(db_session, order.id)

    assert totals["subtotal"] == 220.0
    assert totals["tax"] == 11.0
    assert totals["total"] == 231.0


async def test_get_order_summary_includes_line_totals(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-7")
    await order_service.add_item(db_session, order.id, menu["Cutting Chai"].id, 3)

    summary = await order_service.get_order_summary(db_session, order.id)

    assert summary["items"][0]["line_total"] == 150.0
    assert summary["total"] == pytest.approx(157.5)


async def test_checkout_marks_order_confirmed_and_rejects_empty_order(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "session-8")

    with pytest.raises(order_service.OrderError):
        await order_service.checkout(db_session, order.id)

    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)
    summary = await order_service.checkout(db_session, order.id)

    assert summary["status"] == "confirmed"


def test_format_summary_text_empty_order():
    text = order_service.format_summary_text({"items": [], "subtotal": 0, "tax": 0, "total": 0})
    assert text == "Your order is currently empty."


def test_format_summary_text_lists_items_and_totals():
    summary = {
        "items": [{"quantity": 2, "name": "Masala Chai"}],
        "subtotal": 160.0,
        "tax": 8.0,
        "total": 168.0,
    }
    text = order_service.format_summary_text(summary)
    assert "2 x Masala Chai" in text
    assert "Rs.168.00" in text


def test_pick_best_coupon_picks_the_highest_discount():
    best = order_service.pick_best_coupon(600.0, is_first_order=False)
    assert best == {"code": "SAVE10", "discount": 60.0}


def test_pick_best_coupon_below_every_minimum_returns_none():
    assert order_service.pick_best_coupon(100.0, is_first_order=False) is None


def test_pick_best_coupon_first_order_only_requires_first_order():
    assert order_service.pick_best_coupon(150.0, is_first_order=True) == {"code": "WELCOME20", "discount": 30.0}
    assert order_service.pick_best_coupon(150.0, is_first_order=False) is None


async def test_has_prior_confirmed_order_true_only_after_a_real_checkout(db_session):
    menu = await _seed_menu(db_session)
    phone = "9876543210"

    assert await order_service.has_prior_confirmed_order(db_session, phone) is False

    order = await order_service.get_or_create_draft_order(db_session, "coupon-session-1")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)
    await order_service.checkout(db_session, order.id, guest_phone=phone)

    assert await order_service.has_prior_confirmed_order(db_session, phone) is True


async def test_checkout_applies_best_coupon_and_recomputes_totals(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "coupon-session-2")
    await order_service.add_item(db_session, order.id, menu["Masala Chai"].id, 5)

    summary = await order_service.checkout(db_session, order.id, guest_phone="9111111111")

    assert summary["coupon_code"] == "WELCOME20"
    assert summary["discount"] == 80.0
    discounted_subtotal = 400.0 - 80.0
    assert summary["tax"] == pytest.approx(round(discounted_subtotal * 0.05, 2))
    assert summary["total"] == pytest.approx(discounted_subtotal + summary["tax"])


async def test_checkout_never_reapplies_coupon_on_second_call(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "coupon-session-3")
    await order_service.add_item(db_session, order.id, menu["Masala Chai"].id, 5)

    first = await order_service.checkout(db_session, order.id, guest_phone="9222222222")
    second = await order_service.checkout(db_session, order.id, guest_phone="9222222222")

    assert first["coupon_code"] == second["coupon_code"]
    assert first["discount"] == second["discount"]


async def test_checkout_without_phone_skips_first_order_only_coupon(db_session):
    menu = await _seed_menu(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "coupon-session-4")
    await order_service.add_item(db_session, order.id, menu["Masala Chai"].id, 2)

    summary = await order_service.checkout(db_session, order.id)

    assert summary["coupon_code"] is None
    assert summary["discount"] == 0.0


async def _seed_menu_with_bakery(db_session):
    menu = await _seed_menu(db_session)
    bakery = MenuItem(name="Chocolate Muffin", price=90, category="Bakery", available=True)
    db_session.add(bakery)
    await db_session.commit()
    await db_session.refresh(bakery)
    menu["Chocolate Muffin"] = bakery
    return menu


async def test_pick_upsell_item_suggests_dessert_when_missing(db_session):
    menu = await _seed_menu_with_bakery(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "upsell-session-1")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)

    suggestion = await order_service.pick_upsell_item(db_session, order.id)

    assert suggestion is not None
    assert suggestion.category == "Bakery"


async def test_pick_upsell_item_suggests_snack_when_dessert_present_but_snack_missing(db_session):
    menu = await _seed_menu_with_bakery(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "upsell-session-2")
    await order_service.add_item(db_session, order.id, menu["Chocolate Muffin"].id, 1)

    suggestion = await order_service.pick_upsell_item(db_session, order.id)

    assert suggestion is not None
    assert suggestion.category == "Snacks"


async def test_pick_upsell_item_returns_none_when_both_covered(db_session):
    menu = await _seed_menu_with_bakery(db_session)
    order = await order_service.get_or_create_draft_order(db_session, "upsell-session-3")
    await order_service.add_item(db_session, order.id, menu["Samosa"].id, 1)
    await order_service.add_item(db_session, order.id, menu["Chocolate Muffin"].id, 1)

    suggestion = await order_service.pick_upsell_item(db_session, order.id)

    assert suggestion is None
