import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timing import timed
from app.models.product import Product

logger = logging.getLogger(__name__)

TTL_SECONDS = 10 * 60

_items: list[Product] | None = None
_cached_at: float = 0.0


async def _fetch(db: AsyncSession) -> list[Product]:
    async with timed("db.products_fetch"):
        stmt = select(Product).where(Product.available.is_(True))
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def get_available_items(db: AsyncSession) -> list[Product]:
    """Products rarely change - serve them from an in-memory cache instead of
    hitting the DB on every product-related turn. Refreshed on TTL expiry or
    via invalidate() (e.g. after an admin edit, if that ever exists)."""
    global _items, _cached_at
    now = time.monotonic()
    if _items is None or (now - _cached_at) > TTL_SECONDS:
        _items = await _fetch(db)
        _cached_at = now
        logger.info("product_cache.refreshed count=%d", len(_items))
    return _items


async def warm() -> None:
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            await get_available_items(db)
    except Exception:
        logger.exception("product_cache.warm_failed")


def invalidate() -> None:
    global _items, _cached_at
    _items = None
    _cached_at = 0.0


def clear() -> None:
    invalidate()
