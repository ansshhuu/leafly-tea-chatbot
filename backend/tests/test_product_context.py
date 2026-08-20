from app.models.product import Product
from app.schemas.chat import Filters
from app.services import product_context


async def _seed(db_session):
    db_session.add_all(
        [
            Product(name="Himalayan Green Tea", price=699, origin="Darjeeling", tea_type="green", caffeine_level="medium", tags=["green"]),
            Product(name="Silver Tips White Tea", price=899, origin="Darjeeling", tea_type="white", caffeine_level="low", tags=["white"]),
            Product(name="Assam Golden Black", price=649, origin="Assam", tea_type="black", caffeine_level="high", tags=["black"]),
            Product(name="Reserve Oolong", price=1299, origin="Darjeeling", tea_type="oolong", caffeine_level="medium", badge="premium", tags=["oolong"]),
            Product(name="Unavailable Tea", price=10, origin="Assam", tea_type="black", caffeine_level="high", available=False),
        ]
    )
    await db_session.commit()


async def test_get_popular_items_excludes_unavailable_and_respects_limit(db_session):
    await _seed(db_session)

    items = await product_context.get_popular_items(db_session, limit=2)

    assert len(items) == 2
    assert all(item["name"] != "Unavailable Tea" for item in items)


async def test_get_filtered_items_applies_caffeine_and_price_filters(db_session):
    await _seed(db_session)

    items = await product_context.get_filtered_items(db_session, Filters(caffeine_level="low", max_price=1000))

    names = {item["name"] for item in items}
    assert names == {"Silver Tips White Tea"}


async def test_get_filtered_items_tea_type_match_is_exact(db_session):
    await _seed(db_session)

    items = await product_context.get_filtered_items(db_session, Filters(tea_type="oolong"))

    names = {item["name"] for item in items}
    assert names == {"Reserve Oolong"}


async def test_get_filtered_items_badge_match(db_session):
    await _seed(db_session)

    items = await product_context.get_filtered_items(db_session, Filters(badge="premium"))

    names = {item["name"] for item in items}
    assert names == {"Reserve Oolong"}


async def test_get_filtered_items_with_no_filters_returns_available_items(db_session):
    await _seed(db_session)

    items = await product_context.get_filtered_items(db_session, None)

    assert len(items) == 4


def test_format_items_block_handles_empty_list():
    block = product_context.format_items_block([], "Matching products")
    assert block == "Matching products: none found matching those criteria."


def test_format_items_block_includes_price_and_origin():
    block = product_context.format_items_block(
        [{"name": "Himalayan Green Tea", "price": 699.0, "origin": "Darjeeling", "tea_type": "green", "caffeine_level": "medium", "badge": None, "tags": []}],
        "Popular items",
    )
    assert "Himalayan Green Tea" in block
    assert "Rs.699.0" in block
    assert "Darjeeling" in block


async def test_get_closest_items_relaxes_price_and_sorts_cheapest_first(db_session):
    await _seed(db_session)

    items, relaxed_field = await product_context.get_closest_items(db_session, Filters(tea_type="white", max_price=10))

    assert relaxed_field == "max_price"
    assert items[0]["name"] == "Silver Tips White Tea"


async def test_get_closest_items_relaxes_caffeine_level(db_session):
    await _seed(db_session)

    items, relaxed_field = await product_context.get_closest_items(
        db_session, Filters(tea_type="black", caffeine_level="low")
    )

    assert relaxed_field == "caffeine_level"
    assert items[0]["name"] == "Assam Golden Black"


async def test_get_closest_items_relaxes_cumulatively_until_something_matches(db_session):
    await _seed(db_session)

    items, relaxed_field = await product_context.get_closest_items(
        db_session, Filters(origin="Assam", badge="bestseller", max_price=1)
    )

    assert relaxed_field == "badge"
    assert items
    assert items[0]["name"] == "Assam Golden Black"


async def test_get_closest_items_returns_empty_when_nothing_in_db_at_all(db_session):
    items, relaxed_field = await product_context.get_closest_items(db_session, Filters(tea_type="white", max_price=10))
    assert items == []
    assert relaxed_field is None


async def test_get_closest_items_with_no_filters_returns_empty_no_relaxation_needed(db_session):
    await _seed(db_session)
    items, relaxed_field = await product_context.get_closest_items(db_session, None)
    assert items == []
    assert relaxed_field is None


def test_fallback_intro_uses_field_specific_caveat():
    assert "caffeine level" in product_context.fallback_intro("caffeine_level")
    assert "affordable" in product_context.fallback_intro("max_price")
    assert "Nothing matched exactly" in product_context.fallback_intro("unknown_field")
