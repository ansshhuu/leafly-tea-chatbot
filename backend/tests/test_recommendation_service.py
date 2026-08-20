from app.services import recommendation_service as rec


def test_weather_bias_tea_types_from_keywords():
    assert rec.weather_bias_tea_types("it's so hot today") == rec.HOT_WEATHER_TEA_TYPES
    assert rec.weather_bias_tea_types("it's raining and cold") == rec.COLD_WEATHER_TEA_TYPES
    assert rec.weather_bias_tea_types("nothing special") is None


def test_shortlist_ranks_weather_matches_first():
    candidates = [
        {"name": "Assam Golden Black", "price": 649, "tea_type": "black", "badge": None, "tags": []},
        {"name": "Himalayan Green Tea", "price": 699, "tea_type": "green", "badge": None, "tags": []},
    ]

    ranked_hot = rec.shortlist(candidates, "it's really hot outside")
    assert ranked_hot[0]["name"] == "Himalayan Green Tea"

    ranked_cold = rec.shortlist(candidates, "it's raining and cold")
    assert ranked_cold[0]["name"] == "Assam Golden Black"


def test_shortlist_ranks_badged_items_above_unbadged_when_no_weather_signal():
    candidates = [
        {"name": "Assam Golden Black", "price": 649, "tea_type": "black", "badge": None, "tags": []},
        {"name": "Reserve Oolong", "price": 1299, "tea_type": "oolong", "badge": "premium", "tags": []},
    ]

    ranked = rec.shortlist(candidates, "surprise me")
    assert ranked[0]["name"] == "Reserve Oolong"


def test_combo_within_budget_stays_under_budget_and_picks_at_least_two_items():
    items = [
        {"name": "Assam Golden Black", "price": 649},
        {"name": "Himalayan Green Tea", "price": 699},
        {"name": "Kashmir White Reserve", "price": 1199},
    ]

    combo = rec.combo_within_budget(items, budget=1400)

    assert len(combo) >= 2
    assert sum(item["price"] for item in combo) <= 1400


def test_combo_within_budget_returns_empty_when_nothing_fits():
    items = [{"name": "Kashmir White Reserve", "price": 1199}]
    combo = rec.combo_within_budget(items, budget=100)
    assert combo == []
