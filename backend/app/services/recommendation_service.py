HOT_WEATHER_WORDS = {"hot", "summer", "heat", "sunny", "humid"}
COLD_WEATHER_WORDS = {"cold", "rain", "rainy", "winter", "chilly", "monsoon"}

# Hot weather calls for lighter, more refreshing teas; cold/rainy weather
# calls for warmer, bolder ones - loosely mirrors how the site's own
# collection taglines describe each tea_type ("Fresh & Delicate" for green,
# "Rich & Bold" for black).
HOT_WEATHER_TEA_TYPES = {"green", "white"}
COLD_WEATHER_TEA_TYPES = {"black", "oolong", "pu-erh"}

SHORTLIST_SIZE = 8


def weather_bias_tea_types(user_message: str) -> set[str] | None:
    text = user_message.lower()
    if any(word in text for word in HOT_WEATHER_WORDS):
        return HOT_WEATHER_TEA_TYPES
    if any(word in text for word in COLD_WEATHER_WORDS):
        return COLD_WEATHER_TEA_TYPES
    return None


def _score(item: dict, weather_tea_types: set[str] | None) -> int:
    score = 0
    if item.get("badge"):
        score += 1
    if weather_tea_types and item.get("tea_type") in weather_tea_types:
        score += 3
    return score


def shortlist(candidates: list[dict], user_message: str) -> list[dict]:
    weather_tea_types = weather_bias_tea_types(user_message)
    ranked = sorted(candidates, key=lambda item: _score(item, weather_tea_types), reverse=True)
    return ranked[:SHORTLIST_SIZE]


def combo_within_budget(items: list[dict], budget: float, max_items: int = 3) -> list[dict]:
    sorted_items = sorted(items, key=lambda item: item["price"])
    best_combo: list[dict] = []
    best_total = 0.0

    def _search(start: int, chosen: list[dict], total: float) -> None:
        nonlocal best_combo, best_total
        if len(chosen) >= 2 and total > best_total:
            best_combo, best_total = list(chosen), total
        if len(chosen) == max_items:
            return
        for i in range(start, len(sorted_items)):
            price = sorted_items[i]["price"]
            if total + price > budget:
                continue
            _search(i + 1, chosen + [sorted_items[i]], total + price)

    _search(0, [], 0.0)
    return best_combo
