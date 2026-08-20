import asyncio

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.menu_item import MenuItem

IMAGE_URLS: dict[str, str] = {
    "Masala Chai": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601429/Chai_Masala_Tea_1200x1200_q6mlco.jpg",
    "Filter Coffee": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601471/Filter_1500x_qnb7te.jpg",
    "Cutting Chai": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601510/cutting-chai4-500x500_jph5aj.jpg",
    "Ginger Chai": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601660/ginger-milk-tea_1_y5e8cr.jpg",
    "Kesar Chai": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601701/What-is-Kesar-Chai_480x480_c987abfe-035a-4298-b3c1-6f0258988c24_ptiocq.jpg",
    "Samosa": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601808/61050397_ij0gcz.jpg",
    "Vada Pav": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601832/vada-pav-3_om8b03.jpg",
    "Kachori": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785601921/khasta-kachori-recipe-500x500_rvbzox.jpg",
    "Bread Pakora": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602113/bread-pakoda_t9acpo.jpg",
    "Aloo Tikki": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602154/1-1_r5qr51.jpg",
    "Dabeli": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602216/kutchi-dabeli-recipe-678x1024_yifusf.jpg",
    "Banana Bread": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602330/20144-banana-banana-bread-VAT-009-4x3-B-78f1cfc64bfa451e8a0fead814719b9f_h1tzgl.jpg",
    "Butter Croissant": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602382/How-to-make-Croissant-baked-2_locxlu.jpg",
    "Chocolate Muffin": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602407/vegan-chocolate-muffins-1_xrwfvo.jpg",
    "Cinnamon Roll": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602451/Crescent-Roll-Cinnamon-Rolls_ujftb4.jpg",
    "Whole Wheat Bread": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602558/20230728144103-md-100-whole-wheat-bread-11-1-of-1-scaled_wkv7r0.jpg",
    "Nankhatai Cookies": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602592/Nankhatai-Recipe_imsa9w.jpg",
    "Cold Coffee": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602642/Cafe-style-cold-coffee-with-icecream_u42uzh.jpg",
    "Cold Brew": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602680/Easy-Cold-Brew-Coffee-Recipe-Vegan-Dairy-Free-Paleo-Healthy_dymspq.jpg",
    "Iced Latte": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602714/220629.iced_.latte_.vanilla-8882_efzdpg.jpg",
    "Lemon Iced Tea": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602766/lemon_iced_tea_w7sfqd.jpg",
    "Mango Cooler": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602794/pha-che_mkivzx.jpg",
    "Virgin Mojito": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602819/Virgin-Mojito-Nojito-Recipe-web-6_odvyvo.jpg",
    "Watermelon Cooler": "https://res.cloudinary.com/ylmg17hu/image/upload/v1785602863/WatermelonCooler1_y4owey.jpg",
}


async def update_menu_images() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MenuItem.id, MenuItem.name))
        db_names = {name: item_id for item_id, name in result.all()}

        not_found = [name for name in IMAGE_URLS if name not in db_names]

        updated = 0
        for name, url in IMAGE_URLS.items():
            item_id = db_names.get(name)
            if item_id is None:
                continue
            item = await session.get(MenuItem, item_id)
            item.image_url = url
            updated += 1

        await session.commit()

    print(f"Updated {updated}/{len(IMAGE_URLS)} rows.")
    if not_found:
        print(f"No DB match for {len(not_found)} name(s):")
        for name in not_found:
            print(f"  - {name!r}")
    else:
        print("Every name matched a DB row.")


if __name__ == "__main__":
    asyncio.run(update_menu_images())
