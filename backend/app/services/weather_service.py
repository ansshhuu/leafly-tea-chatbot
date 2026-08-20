import logging
import time

import httpx

from app.core.timing import timed

logger = logging.getLogger(__name__)

CAFE_LATITUDE = 19.0596
CAFE_LONGITUDE = 72.8295

_TTL_SECONDS = 30 * 60
_HOT_TEMP_THRESHOLD_C = 30.0
_RAIN_WEATHER_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}

_RAIN_HINT = "It's raining outside ☔ — how about a hot Masala Chai to warm up?"
_HOT_HINT = "It's a warm one today ☀️ — maybe a Cold Brew or Mango Cooler?"

_cache: dict[str, tuple[float, str | None]] = {}


async def _fetch_condition(latitude: float, longitude: float) -> str | None:
    try:
        async with timed("http.open_meteo_fetch"):
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current": "temperature_2m,weather_code",
                    },
                )
                response.raise_for_status()
                data = response.json()
    except Exception:
        logger.warning("weather.fetch_failed", exc_info=True)
        return None

    current = data.get("current") or {}
    weather_code = current.get("weather_code")
    temperature = current.get("temperature_2m")

    if weather_code in _RAIN_WEATHER_CODES:
        return "rainy"
    if temperature is not None and temperature >= _HOT_TEMP_THRESHOLD_C:
        return "hot"
    return "pleasant"


def _cache_key(latitude: float, longitude: float) -> str:
    # Rounded to ~1km so nearby requests (repeat visits, GPS jitter) share a
    # cache entry instead of hitting Open-Meteo every time.
    return f"{latitude:.2f},{longitude:.2f}"


async def get_condition(latitude: float | None = None, longitude: float | None = None) -> str | None:
    """Fetches weather for the given coordinates (the user's actual browser
    geolocation, when granted), falling back to the cafe's own location
    (Bandra West) when the caller doesn't have/didn't get user coordinates -
    e.g. geolocation was denied or unavailable. Never blocks/raises on a
    missing location; always resolves to *some* condition or None."""
    lat = latitude if latitude is not None else CAFE_LATITUDE
    lon = longitude if longitude is not None else CAFE_LONGITUDE

    key = _cache_key(lat, lon)
    cached = _cache.get(key)
    if cached is not None:
        expires_at, condition = cached
        if time.monotonic() < expires_at:
            return condition

    condition = await _fetch_condition(lat, lon)
    _cache[key] = (time.monotonic() + _TTL_SECONDS, condition)
    return condition


def get_weather_hint(condition: str | None) -> str | None:
    if condition == "rainy":
        return _RAIN_HINT
    if condition == "hot":
        return _HOT_HINT
    return None


def clear() -> None:
    _cache.clear()
