"""One-off data wipe: clears every transactional/session table, leaving
products (and its image_urls) and the alembic_version schema tracker
completely untouched. Resets id sequences back to 1 so fresh data starts at
#1 again, not wherever testing left off.

Run with: python -m app.scripts.wipe_test_data
"""

import asyncio

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

# products and alembic_version are deliberately excluded - this is a data
# wipe, not a menu reset or schema rollback.
TABLES_TO_CLEAR = [
    "chat_history",
    "chat_sessions",
    "escalations",
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
