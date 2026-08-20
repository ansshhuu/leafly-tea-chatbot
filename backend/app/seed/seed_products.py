import asyncio
import json
from pathlib import Path

from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.product import Product

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "products.json"


async def seed_products() -> None:
    items = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as session:
        await session.execute(delete(Product))
        session.add_all(Product(**item) for item in items)
        await session.commit()

    print(f"Seeded {len(items)} products from {FIXTURE_PATH.name}")


if __name__ == "__main__":
    asyncio.run(seed_products())
