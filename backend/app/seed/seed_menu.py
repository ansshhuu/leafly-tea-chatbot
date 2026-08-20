import asyncio
import json
from pathlib import Path

from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.menu_item import MenuItem

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "menu_items.json"


async def seed_menu() -> None:
    items = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as session:
        await session.execute(delete(MenuItem))
        session.add_all(MenuItem(**item) for item in items)
        await session.commit()

    print(f"Seeded {len(items)} menu items from {FIXTURE_PATH.name}")


if __name__ == "__main__":
    asyncio.run(seed_menu())
