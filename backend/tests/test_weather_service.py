from app.services import weather_service


async def test_get_condition_returns_rainy_for_rain_weather_code(monkeypatch):
    async def fake_fetch(latitude, longitude):
        return "rainy"

    monkeypatch.setattr(weather_service, "_fetch_condition", fake_fetch)

    assert await weather_service.get_condition() == "rainy"


async def test_get_condition_caches_result_across_calls(monkeypatch):
    calls = {"count": 0}

    async def fake_fetch(latitude, longitude):
        calls["count"] += 1
        return "hot"

    monkeypatch.setattr(weather_service, "_fetch_condition", fake_fetch)

    await weather_service.get_condition()
    await weather_service.get_condition()

    assert calls["count"] == 1


async def test_get_condition_returns_none_on_fetch_failure(monkeypatch):
    async def failing_fetch(latitude, longitude):
        return None

    monkeypatch.setattr(weather_service, "_fetch_condition", failing_fetch)

    assert await weather_service.get_condition() is None


async def test_get_condition_uses_user_coordinates_when_provided(monkeypatch):
    seen_coords = []

    async def fake_fetch(latitude, longitude):
        seen_coords.append((latitude, longitude))
        return "pleasant"

    monkeypatch.setattr(weather_service, "_fetch_condition", fake_fetch)

    await weather_service.get_condition(latitude=12.9716, longitude=77.5946)

    assert seen_coords == [(12.9716, 77.5946)]


async def test_get_condition_falls_back_to_cafe_coordinates_without_user_location(monkeypatch):
    seen_coords = []

    async def fake_fetch(latitude, longitude):
        seen_coords.append((latitude, longitude))
        return "pleasant"

    monkeypatch.setattr(weather_service, "_fetch_condition", fake_fetch)

    await weather_service.get_condition()

    assert seen_coords == [(weather_service.CAFE_LATITUDE, weather_service.CAFE_LONGITUDE)]


def test_get_weather_hint_matches_condition():
    assert "raining" in weather_service.get_weather_hint("rainy").lower()
    assert "warm" in weather_service.get_weather_hint("hot").lower()
    assert weather_service.get_weather_hint("pleasant") is None
    assert weather_service.get_weather_hint(None) is None
