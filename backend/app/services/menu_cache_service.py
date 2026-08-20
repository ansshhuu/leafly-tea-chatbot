import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timing import timed
from app.models.menu_item import MenuItem

logger = logging.getLogger(__name__)

TTL_SECONDS = 10 * 60

_items: list[MenuItem] | None = None
_cached_at: float = 0.0


async def _fetch(db: AsyncSession) -> list[MenuItem]:
    async with timed("db.menu_items_fetch"):
        stmt = select(MenuItem).where(MenuItem.available.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_available_items(db: AsyncSession) -> list[MenuItem]:
    """Menu items rarely change - serve them from an in-memory cache instead of
    hitting the DB on every menu-related turn. Refreshed on TTL expiry or via
    invalidate() (e.g. after an admin edit, if that ever exists)."""
    global _items, _cached_at
    now = time.monotonic()
    if _items is None or (now - _cached_at) > TTL_SECONDS:
        _items = await _fetch(db)
        _cached_at = now
        logger.info("menu_cache.refreshed count=%d", len(_items))
    return _items


async def warm() -> None:
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await get_available_items(db)
    except Exception:
        logger.exception("menu_cache.warm_failed")


def invalidate() -> None:
    global _items, _cached_at
    _items = None
    _cached_at = 0.0


def clear() -> None:
    invalidate()
