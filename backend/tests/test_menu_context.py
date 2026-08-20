from app.models.menu_item import MenuItem
from app.schemas.chat import Filters
from app.services import menu_context


async def _seed(db_session):
    db_session.add_all(
        [
            MenuItem(name="Masala Chai", price=80, category="Hot Beverages", is_veg=True, spice_level=0, tags=["chai"]),
            MenuItem(name="Filter Coffee", price=90, category="Hot Beverages", is_veg=True, spice_level=0, tags=["coffee"]),
            MenuItem(name="Samosa", price=60, category="Snacks", is_veg=True, is_vegan=True, spice_level=2, tags=["spicy"]),
            MenuItem(name="Cold Brew", price=160, category="Cold Beverages", is_veg=True, is_vegan=True, spice_level=0, tags=["cold"]),
            MenuItem(name="Unavailable Item", price=10, category="Snacks", is_veg=True, spice_level=0, available=False),
        ]
    )
    await db_session.commit()


async def test_get_popular_items_excludes_unavailable_and_respects_limit(db_session):
    await _seed(db_session)

    items = await menu_context.get_popular_items(db_session, limit=2)

    assert len(items) == 2
    assert all(item["name"] != "Unavailable Item" for item in items)


async def test_get_filtered_items_applies_dietary_and_price_filters(db_session):
    await _seed(db_session)

    items = await menu_context.get_filtered_items(db_session, Filters(is_vegan=True, max_price=100))

    names = {item["name"] for item in items}
    assert names == {"Samosa"}


async def test_get_filtered_items_min_spice_level_excludes_mild_items(db_session):
    await _seed(db_session)

    items = await menu_context.get_filtered_items(db_session, Filters(min_spice_level=2))

    names = {item["name"] for item in items}
    assert names == {"Samosa"}


async def test_get_filtered_items_spice_level_ceiling_still_excludes_spicy_items(db_session):
    await _seed(db_session)

    items = await menu_context.get_filtered_items(db_session, Filters(spice_level=0))

    names = {item["name"] for item in items}
    assert "Samosa" not in names
    assert "Masala Chai" in names


async def test_get_filtered_items_category_match_is_fuzzy(db_session):
    await _seed(db_session)

    items = await menu_context.get_filtered_items(db_session, Filters(category="hot"))

    names = {item["name"] for item in items}
    assert names == {"Masala Chai", "Filter Coffee"}


async def test_get_filtered_items_with_no_filters_returns_available_items(db_session):
    await _seed(db_session)

    items = await menu_context.get_filtered_items(db_session, None)

    assert len(items) == 4


def test_format_items_block_handles_empty_list():
    block = menu_context.format_items_block([], "Matching menu items")
    assert block == "Matching menu items: none found matching those criteria."


def test_format_items_block_includes_price_and_category():
    block = menu_context.format_items_block(
        [{"name": "Masala Chai", "price": 80.0, "category": "Hot Beverages", "tags": ["chai"], "spice_level": 0}],
        "Popular items",
    )
    assert "Masala Chai" in block
    assert "Rs.80.0" in block
    assert "Hot Beverages" in block


async def test_get_closest_items_relaxes_price_and_sorts_cheapest_first(db_session):
    await _seed(db_session)

    items, relaxed_field = await menu_context.get_closest_items(db_session, Filters(is_vegan=True, max_price=10))

    assert relaxed_field == "max_price"
    assert [item["name"] for item in items] == ["Samosa", "Cold Brew"]


async def test_get_closest_items_relaxes_spice_level_and_sorts_mildest_first(db_session):
    await _seed(db_session)

    items, relaxed_field = await menu_context.get_closest_items(
        db_session, Filters(category="Snacks", spice_level=0)
    )

    assert relaxed_field == "spice_level"
    assert items[0]["name"] == "Samosa"


async def test_get_closest_items_relaxes_min_spice_level_and_sorts_spiciest_first(db_session):
    await _seed(db_session)

    items, relaxed_field = await menu_context.get_closest_items(
        db_session, Filters(category="Hot Beverages", min_spice_level=2)
    )

    assert relaxed_field == "min_spice_level"
    assert items
    assert items == sorted(items, key=lambda i: -i["spice_level"])


async def test_get_closest_items_relaxes_cumulatively_until_something_matches(db_session):
    await _seed(db_session)

    items, relaxed_field = await menu_context.get_closest_items(
        db_session, Filters(category="Hot Beverages", is_gluten_free=True, max_price=1)
    )

    assert relaxed_field == "is_gluten_free"
    assert items


async def test_get_closest_items_returns_empty_when_nothing_in_db_at_all(db_session):
    items, relaxed_field = await menu_context.get_closest_items(db_session, Filters(is_vegan=True, max_price=10))
    assert items == []
    assert relaxed_field is None


async def test_get_closest_items_with_no_filters_returns_empty_no_relaxation_needed(db_session):
    await _seed(db_session)
    items, relaxed_field = await menu_context.get_closest_items(db_session, None)
    assert items == []
    assert relaxed_field is None


def test_fallback_intro_uses_field_specific_caveat():
    assert "gentlest option" in menu_context.fallback_intro("spice_level")
    assert "closest match" in menu_context.fallback_intro("min_spice_level")
    assert "not gluten-free" in menu_context.fallback_intro("is_gluten_free")
