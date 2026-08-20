import asyncio
import logging
import math
import time

import httpx

from app.core.config import CAFE_LOCATIONS, DELIVERY_RADIUS_KM
from app.core.timing import timed

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "RasaCafeAssistant/1.0 (contact: xqoratechnologies.ai.ap@gmail.com)"
_EARTH_RADIUS_KM = 6371.0

# Nominatim's usage policy caps unauthenticated use at 1 request/sec - this
# lock + timestamp serializes calls across concurrent requests so we never
# burst past that, rather than trusting callers to space themselves out.
_rate_lock = asyncio.Lock()
_last_request_at = 0.0
_MIN_INTERVAL_SECONDS = 1.0

# Short-lived cache for autocomplete suggestion queries, keyed by the exact
# normalized query string. Live-typing naturally repeats queries (backspace
# then retype, refocusing the input, etc.), and each keystroke pause already
# costs a real Nominatim request under the 1req/sec throttle above - this
# cuts that further without needing a heavier cache/eviction policy for what
# is, in practice, a handful of entries per session.
_SUGGEST_CACHE_TTL_SECONDS = 5 * 60
_suggest_cache: dict[str, tuple[float, list[dict]]] = {}


async def _throttle() -> None:
    global _last_request_at
    async with _rate_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < _MIN_INTERVAL_SECONDS:
            await asyncio.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        _last_request_at = time.monotonic()


async def _raw_search(query: str, limit: int) -> list[dict] | None:
    """Low-level Nominatim /search call. Returns the raw JSON results list,
    or None specifically when the REQUEST ITSELF failed (network error,
    timeout, non-2xx status) - distinct from an empty list, which means
    Nominatim responded fine but simply found nothing. Callers use that
    distinction to tell "genuinely unfindable address" (ask to retype) apart
    from "Nominatim is slow/down right now" (don't block the customer)."""
    await _throttle()
    try:
        async with timed("http.nominatim_search"):
            async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": _USER_AGENT}) as client:
                response = await client.get(
                    _NOMINATIM_URL,
                    params={"q": query, "format": "json", "limit": limit},
                )
                response.raise_for_status()
                return response.json()
    except Exception:
        logger.warning("geocoding.fetch_failed query=%r", query, exc_info=True)
        return None


async def geocode_address(address: str) -> tuple[float, float] | None:
    """Resolves a free-text address to (latitude, longitude) via Nominatim.
    Returns None if the address can't be found/is too ambiguous, OR if the
    request itself failed - callers that need to tell those two cases apart
    (see resolve_delivery_location) should use _raw_search directly instead."""
    results = await _raw_search(address, limit=1)
    if not results:
        return None

    try:
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None


async def suggest_addresses(query: str, limit: int = 5) -> list[dict]:
    """Live-typing autocomplete: returns up to `limit` real Nominatim search
    candidates for a still-being-typed address, each shaped
    {"display_name": str, "lat": float, "lon": float}. Always returns a list
    (never None/raises) - on a Nominatim failure this is just an empty list,
    so the frontend dropdown simply shows no suggestions rather than erroring,
    and the customer can still fall back to typing/submitting free text."""
    normalized = query.strip()
    if len(normalized) < 3:
        return []

    cache_key = normalized.lower()
    cached = _suggest_cache.get(cache_key)
    now = time.monotonic()
    if cached is not None and (now - cached[0]) < _SUGGEST_CACHE_TTL_SECONDS:
        return cached[1]

    results = await _raw_search(normalized, limit=limit)
    if not results:
        return []

    suggestions = []
    for row in results:
        try:
            suggestions.append(
                {"display_name": row["display_name"], "lat": float(row["lat"]), "lon": float(row["lon"])}
            )
        except (KeyError, ValueError, TypeError):
            continue

    _suggest_cache[cache_key] = (now, suggestions)
    return suggestions


async def reverse_geocode(lat: float, lon: float) -> dict | None:
    """Resolves a pin position (lat/lon - typically from the map's
    geolocation-first drag-to-adjust pin) back to a human-readable address
    via Nominatim's reverse endpoint, for the live "resolved address" text
    shown under the map as the customer drags. Returns
    {"display_name": str}, or None on failure/no result - never raises, so
    the frontend can just show nothing rather than erroring out mid-drag."""
    await _throttle()
    try:
        async with timed("http.nominatim_reverse"):
            async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": _USER_AGENT}) as client:
                response = await client.get(
                    _REVERSE_URL,
                    params={"lat": lat, "lon": lon, "format": "json"},
                )
                response.raise_for_status()
                result = response.json()
    except Exception:
        logger.warning("geocoding.reverse_failed lat=%s lon=%s", lat, lon, exc_info=True)
        return None

    if not isinstance(result, dict) or not result.get("display_name"):
        return None
    return {"display_name": result["display_name"]}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def find_nearest_location(latitude: float, longitude: float) -> tuple[dict, float]:
    """Returns (location, distance_km) for the CAFE_LOCATIONS entry closest
    to the given coordinates."""
    nearest = min(
        CAFE_LOCATIONS,
        key=lambda loc: haversine_km(latitude, longitude, loc["latitude"], loc["longitude"]),
    )
    distance = haversine_km(latitude, longitude, nearest["latitude"], nearest["longitude"])
    return nearest, distance


async def resolve_delivery_location(address: str) -> dict:
    """Geocodes `address` and checks it against the delivery radius. Returns
    a dict shaped one of:
    - {"status": "ok", "location": <CAFE_LOCATIONS entry>, "distance_km": float, "lat": float, "lon": float}
    - {"status": "too_far", "location": <nearest entry>, "distance_km": float}
    - {"status": "not_found"} - Nominatim responded fine, genuinely no match -
      ask the customer to retype more specifically (existing behavior).
    - {"status": "error"} - the Nominatim REQUEST itself failed (timeout/
      network/HTTP error), not a "no results" answer - callers should not
      block the customer on this, just proceed without verified coordinates.
    """
    results = await _raw_search(address, limit=1)
    if results is None:
        return {"status": "error"}
    if not results:
        return {"status": "not_found"}

    try:
        coords = float(results[0]["lat"]), float(results[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return {"status": "error"}

    nearest, distance = find_nearest_location(*coords)
    if distance > DELIVERY_RADIUS_KM:
        return {"status": "too_far", "location": nearest, "distance_km": distance}
    return {"status": "ok", "location": nearest, "distance_km": distance, "lat": coords[0], "lon": coords[1]}
