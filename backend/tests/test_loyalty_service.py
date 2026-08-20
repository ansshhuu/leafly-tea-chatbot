from app.services import loyalty_service


def test_is_loyalty_question_matches_common_phrasings():
    assert loyalty_service.is_loyalty_question("what are my points") is True
    assert loyalty_service.is_loyalty_question("How many loyalty points do I have?") is True
    assert loyalty_service.is_loyalty_question("show me my rewards") is True
    assert loyalty_service.is_loyalty_question("I'd like to order a samosa") is False


async def test_award_points_credits_one_point_per_hundred_rupees(db_session):
    earned = await loyalty_service.award_points(db_session, "9876543210", 235.0)
    assert earned == 2

    total = await loyalty_service.get_points(db_session, "9876543210")
    assert total == 2


async def test_award_points_accumulates_across_orders(db_session):
    await loyalty_service.award_points(db_session, "9876543211", 100.0)
    await loyalty_service.award_points(db_session, "9876543211", 150.0)

    total = await loyalty_service.get_points(db_session, "9876543211")
    assert total == 2


async def test_award_points_below_one_point_earns_nothing(db_session):
    earned = await loyalty_service.award_points(db_session, "9876543212", 50.0)
    assert earned == 0
    assert await loyalty_service.get_points(db_session, "9876543212") == 0


def test_get_newly_unlocked_tier_fires_when_crossing_a_threshold():
    tier = loyalty_service.get_newly_unlocked_tier(90, 110)
    assert tier is not None
    assert tier["points"] == 100


def test_get_newly_unlocked_tier_returns_none_when_no_threshold_crossed():
    assert loyalty_service.get_newly_unlocked_tier(110, 120) is None


def test_get_newly_unlocked_tier_returns_none_for_already_crossed_threshold():
    assert loyalty_service.get_newly_unlocked_tier(100, 110) is None


def test_get_newly_unlocked_tier_returns_highest_when_multiple_crossed_at_once():
    tier = loyalty_service.get_newly_unlocked_tier(10, 500)
    assert tier["points"] == 500


async def test_get_points_for_unknown_phone_is_zero(db_session):
    assert await loyalty_service.get_points(db_session, "0000000000") == 0


def test_get_progress_before_first_tier():
    progress = loyalty_service.get_progress(60)
    assert progress["current_points"] == 60
    assert progress["next_reward_points"] == 100
    assert progress["next_reward_label"] == "Free Samosa"
    assert progress["points_needed"] == 40
    assert "60/100" in progress["progress_label"]


def test_get_progress_between_tiers():
    progress = loyalty_service.get_progress(150)
    assert progress["next_reward_points"] == 250
    assert progress["next_reward_label"] == "Free Filter Coffee"
    assert progress["points_needed"] == 100


def test_get_progress_past_every_tier():
    progress = loyalty_service.get_progress(500)
    assert progress["points_needed"] == 0
    assert progress["next_reward_points"] == 500
    assert "unlocked" in progress["progress_label"].lower()


def test_format_loyalty_card_shape_matches_schema_fields():
    card = loyalty_service.format_loyalty_card(150)
    assert set(card.keys()) == {
        "current_points",
        "next_reward",
        "next_reward_points",
        "points_needed",
        "progress_label",
    }
