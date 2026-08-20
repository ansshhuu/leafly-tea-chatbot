"""One-off data wipe: clears every transactional/session table, leaving
menu_items (and its image_urls) and the alembic_version schema tracker
completely untouched. Resets id sequences back to 1 so a fresh order/
reservation starts at #1 again, not wherever testing left off.

Run with: python -m app.scripts.wipe_test_data
"""

import asyncio

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

# menu_items and alembic_version are deliberately excluded - this is a data
# wipe, not a menu reset or schema rollback. TRUNCATE ... CASCADE only
# cascades to tables with an FK *pointing at* one of these (e.g. order_items
# -> orders), never backward to menu_items, so menu data is unaffected.
TABLES_TO_CLEAR = [
    "order_items",
    "orders",
    "reservations",
    "chat_history",
    "chat_sessions",
    "escalations",
    "feedback",
    "customer_profiles",
    "users",
]


async def wipe() -> None:
    async with AsyncSessionLocal() as db:
        table_list = ", ".join(f'"{t}"' for t in TABLES_TO_CLEAR)
        await db.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
        await db.commit()
        print(f"Truncated and reset sequences for: {', '.join(TABLES_TO_CLEAR)}")


if __name__ == "__main__":
    asyncio.run(wipe())
