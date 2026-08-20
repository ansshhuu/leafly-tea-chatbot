from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu_item import MenuItem
from app.prompts.menu_translations import translated_name_and_description
from app.schemas.chat import Filters
from app.services import menu_cache_service

POPULAR_LIMIT = 5
MATCH_LIMIT = 8
RECOMMENDATION_POOL_LIMIT = 50

CATEGORY_ORDER = ["Hot Beverages", "Cold Beverages", "Snacks", "Bakery"]


def _row_to_dict(row) -> dict:
    return {
        "name": row.name,
        "price": float(row.price),
        "category": row.category,
        "tags": row.tags or [],
        "spice_level": row.spice_level,
        "image_url": row.image_url,
    }


def _display_row_to_dict(row) -> dict:
    return {
        "name": row.name,
        "description": row.description,
        "price": float(row.price),
        "category": row.category,
        "is_veg": row.is_veg,
        "is_vegan": row.is_vegan,
        "is_gluten_free": row.is_gluten_free,
        "spice_level": row.spice_level,
        "tags": row.tags or [],
        "image_url": row.image_url,
    }


async def get_full_menu_display(db: AsyncSession) -> list[dict]:
    items = await menu_cache_service.get_available_items(db)

    grouped: dict[str, list[dict]] = {}
    for item in sorted(items, key=lambda i: (i.category, i.name)):
        grouped.setdefault(item.category, []).append(_display_row_to_dict(item))

    ordered_categories = [c for c in CATEGORY_ORDER if c in grouped]
    ordered_categories += [c for c in grouped if c not in CATEGORY_ORDER]

    return [{"category": category, "items": grouped[category]} for category in ordered_categories]


def translate_menu_display(categories: list[dict], lang: str) -> list[dict]:
    """Translates item names/descriptions in a get_full_menu_display() result
    to match the CURRENT message's language (see menu_translations) - called
    once per turn from ai_service, keyed off that turn's own detected
    language, so it never gets "stuck" reflecting an earlier turn's
    language. A no-op for "en"/"hinglish"."""
    if lang not in ("hi", "mr"):
        return categories
    return [
        {
            **category,
            "items": [
                {
                    **item,
                    **dict(
                        zip(
                            ("name", "description"),
                            translated_name_and_description(item["name"], item.get("description"), lang),
                        )
                    ),
                }
                for item in category["items"]
            ],
        }
        for category in categories
    ]


def translate_item_name(name: str, lang: str) -> str:
    """Single-name equivalent of translate_menu_display, for item names
    embedded directly into a template sentence (order confirmations, upsell
    suggestions, clarification prompts, etc.) rather than a menu_display/
    suggested_items card - see ai_service's order_action handling."""
    translated, _ = translated_name_and_description(name, None, lang)
    return translated


def translate_suggested_items(items: list[dict], lang: str) -> list[dict]:
    """Same as translate_menu_display but for the compact SuggestedItem shape
    (no description field)."""
    if lang not in ("hi", "mr"):
        return items
    translated = []
    for item in items:
        name, _ = translated_name_and_description(item["name"], None, lang)
        translated.append({**item, "name": name})
    return translated


async def get_popular_items(db: AsyncSession, limit: int = POPULAR_LIMIT) -> list[dict]:
    items = await menu_cache_service.get_available_items(db)
    ordered = sorted(items, key=lambda i: i.id)[:limit]
    return [_row_to_dict(item) for item in ordered]


def _matches_filters(item: MenuItem, filters: Filters | None) -> bool:
    if filters is None:
        return True
    if filters.is_veg and not item.is_veg:
        return False
    if filters.is_vegan and not item.is_vegan:
        return False
    if filters.is_gluten_free and not item.is_gluten_free:
        return False
    if filters.spice_level is not None and item.spice_level > filters.spice_level:
        return False
    if filters.min_spice_level is not None and item.spice_level < filters.min_spice_level:
        return False
    if filters.max_price is not None and float(item.price) > filters.max_price:
        return False
    if filters.min_price is not None and float(item.price) < filters.min_price:
        return False
    if filters.category and filters.category.lower() not in item.category.lower():
        return False
    if filters.tag and filters.tag.lower() not in {tag.lower() for tag in (item.tags or [])}:
        return False
    return True


async def get_filtered_items(db: AsyncSession, filters: Filters | None, limit: int = MATCH_LIMIT) -> list[dict]:
    items = await menu_cache_service.get_available_items(db)
    matched = [item for item in items if _matches_filters(item, filters)]
    matched.sort(key=lambda item: float(item.price))
    return [_row_to_dict(item) for item in matched[:limit]]


async def get_known_tags(db: AsyncSession) -> list[str]:
    items = await menu_cache_service.get_available_items(db)
    seen: set[str] = set()
    for item in items:
        seen.update(item.tags or [])
    return sorted(seen)


_RELAX_PRIORITY = [
    "spice_level",
    "min_spice_level",
    "max_price",
    "min_price",
    "is_gluten_free",
    "is_vegan",
    "is_veg",
    "tag",
    "category",
]
_NUMERIC_FIELDS = {"spice_level", "min_spice_level", "max_price", "min_price"}

_FALLBACK_INTROS = {
    "spice_level": "We don't have anything that mild right now, but here's our gentlest option:",
    "min_spice_level": "We don't have anything that spicy right now, but here's the closest match:",
    "max_price": "Nothing quite that cheap right now, but here's our most affordable option:",
    "min_price": "Nothing in that higher price range right now, but here's the closest match:",
    "is_gluten_free": "We don't have a gluten-free option there right now, but here's the closest match (not gluten-free):",
    "is_vegan": "We don't have a vegan option there right now, but here's the closest match (not vegan):",
    "is_veg": "We don't have a vegetarian option there right now, but here's the closest match (not vegetarian):",
    "tag": "Nothing quite matching that right now, but here's something close:",
    "category": "Nothing in that exact category right now, but here's what's popular instead:",
    "everything": "Nothing matched exactly, but here's what we do have:",
}


async def get_closest_items(db: AsyncSession, filters: Filters | None, limit: int = MATCH_LIMIT) -> tuple[list[dict], str | None]:
    if filters is None:
        return [], None

    relaxed = filters.model_copy()
    for field in _RELAX_PRIORITY:
        current = getattr(relaxed, field, None)
        is_unset = (current is None) if field in _NUMERIC_FIELDS else not current
        if is_unset:
            continue
        setattr(relaxed, field, None)

        items = await get_filtered_items(db, relaxed, limit=limit)
        if items:
            if field == "spice_level":
                items = sorted(items, key=lambda i: i["spice_level"])[:limit]
            elif field == "min_spice_level":
                items = sorted(items, key=lambda i: -i["spice_level"])[:limit]
            elif field == "max_price":
                items = sorted(items, key=lambda i: i["price"])[:limit]
            elif field == "min_price":
                items = sorted(items, key=lambda i: -i["price"])[:limit]
            return items, field

    fallback = await get_filtered_items(db, None, limit=limit)
    return fallback, ("everything" if fallback else None)


def fallback_intro(relaxed_field: str) -> str:
    return _FALLBACK_INTROS.get(relaxed_field, _FALLBACK_INTROS["everything"])


def format_items_block(items: list[dict], heading: str) -> str:
    if not items:
        return f"{heading}: none found matching those criteria."

    lines = "\n".join(
        "- {name} (Rs.{price}, {category}{spice}{tags})".format(
            name=item["name"],
            price=item["price"],
            category=item["category"],
            spice=f", spice level {item['spice_level']}" if item.get("spice_level") else "",
            tags=f", tags: {', '.join(item['tags'])}" if item.get("tags") else "",
        )
        for item in items
    )
    return f"{heading}:\n{lines}"
