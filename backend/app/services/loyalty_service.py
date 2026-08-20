from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import LOYALTY_POINTS_PER_RUPEES, LOYALTY_REWARD_TIERS
from app.services import customer_profile_service

_LOYALTY_KEYWORDS = ("my points", "loyalty point", "loyalty program", "my rewards", "reward points")


def is_loyalty_question(text: str) -> bool:
    normalized = text.lower()
    return any(keyword in normalized for keyword in _LOYALTY_KEYWORDS)


async def award_points(db: AsyncSession, phone: str, amount_spent: float) -> int:
    points_earned = int(amount_spent // LOYALTY_POINTS_PER_RUPEES)
    if points_earned <= 0:
        return 0

    profile = await customer_profile_service.get_or_create_profile(db, phone)
    profile.loyalty_points += points_earned
    await db.commit()
    return points_earned


async def get_points(db: AsyncSession, phone: str) -> int:
    profile = await customer_profile_service.get_profile(db, phone)
    return profile.loyalty_points if profile is not None else 0


async def award_points_and_get_total(db: AsyncSession, phone: str, amount_spent: float) -> tuple[int, int]:
    """Like award_points() followed by get_points(), but without the redundant
    second DB round trip - the profile's new total is already known in memory
    right after the award."""
    points_earned = int(amount_spent // LOYALTY_POINTS_PER_RUPEES)
    profile = await customer_profile_service.get_or_create_profile(db, phone)
    if points_earned > 0:
        profile.loyalty_points += points_earned
        await db.commit()
    return points_earned, profile.loyalty_points


def get_progress(points: int) -> dict:
    tiers = sorted(LOYALTY_REWARD_TIERS, key=lambda tier: tier["points"])
    next_tier = next((tier for tier in tiers if tier["points"] > points), None)

    if next_tier is None:
        top = tiers[-1]
        return {
            "current_points": points,
            "next_reward_points": top["points"],
            "next_reward_label": top["reward"],
            "points_needed": 0,
            "progress_label": f"{points}/{top['points']} points - every reward tier unlocked! 🎉",
        }

    return {
        "current_points": points,
        "next_reward_points": next_tier["points"],
        "next_reward_label": next_tier["reward"],
        "points_needed": next_tier["points"] - points,
        "progress_label": f"{points}/{next_tier['points']} points to your next reward",
    }


def get_newly_unlocked_tier(points_before: int, points_after: int) -> dict | None:
    crossed = [tier for tier in LOYALTY_REWARD_TIERS if points_before < tier["points"] <= points_after]
    if not crossed:
        return None
    return max(crossed, key=lambda tier: tier["points"])


def format_loyalty_card(points: int) -> dict:
    progress = get_progress(points)
    return {
        "current_points": progress["current_points"],
        "next_reward": progress["next_reward_label"],
        "next_reward_points": progress["next_reward_points"],
        "points_needed": progress["points_needed"],
        "progress_label": progress["progress_label"],
    }
