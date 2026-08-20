import pytest

from app.core.config import CAFE_LOCATIONS, DELIVERY_RADIUS_KM
from app.services import geocoding_service


def test_haversine_km_zero_for_identical_points():
    assert geocoding_service.haversine_km(19.0596, 72.8295, 19.0596, 72.8295) == 0


def test_haversine_km_matches_known_distance_bandra_to_indiranagar():
    bandra = CAFE_LOCATIONS[0]
    indiranagar = CAFE_LOCATIONS[1]
    distance = geocoding_service.haversine_km(
        bandra["latitude"], bandra["longitude"], indiranagar["latitude"], indiranagar["longitude"]
    )
    # Mumbai to Bengaluru is roughly 840-980km as the crow flies.
    assert 800 < distance < 1000


def test_find_nearest_location_picks_closest_branch():
    bandra = CAFE_LOCATIONS[0]
    nearest, distance = geocoding_service.find_nearest_location(bandra["latitude"] + 0.01, bandra["longitude"] + 0.01)
    assert nearest["name"] == bandra["name"]
    assert distance < 5


async def test_resolve_delivery_location_within_range_returns_ok(monkeypatch):
    bandra = CAFE_LOCATIONS[0]

    async def fake_raw_search(query, limit):
        return [{"lat": str(bandra["latitude"] + 0.01), "lon": str(bandra["longitude"] + 0.01)}]

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    result = await geocoding_service.resolve_delivery_location("14th Road, Bandra West")

    assert result["status"] == "ok"
    assert result["location"]["name"] == bandra["name"]
    assert result["distance_km"] < DELIVERY_RADIUS_KM
    assert result["lat"] == pytest.approx(bandra["latitude"] + 0.01)
    assert result["lon"] == pytest.approx(bandra["longitude"] + 0.01)


async def test_resolve_delivery_location_beyond_radius_returns_too_far(monkeypatch):
    async def fake_raw_search(query, limit):
        # Far from every branch (middle of the Arabian Sea).
        return [{"lat": "15.0", "lon": "68.0"}]

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    result = await geocoding_service.resolve_delivery_location("somewhere far away")

    assert result["status"] == "too_far"
    assert result["distance_km"] > DELIVERY_RADIUS_KM
    assert "name" in result["location"]


async def test_resolve_delivery_location_empty_results_returns_not_found(monkeypatch):
    async def fake_raw_search(query, limit):
        return []

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    result = await geocoding_service.resolve_delivery_location("asdkjaslkdj not a real place")

    assert result["status"] == "not_found"


async def test_resolve_delivery_location_request_failure_returns_error_not_not_found(monkeypatch):
    # Distinct from "not_found": Nominatim itself failed to respond (timeout/
    # network/HTTP error) - callers must be able to tell this apart from a
    # genuinely unfindable address, since they react to it very differently
    # (don't block the customer vs. ask them to retype).
    async def fake_raw_search(query, limit):
        return None

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    result = await geocoding_service.resolve_delivery_location("somewhere, doesn't matter")

    assert result["status"] == "error"


async def test_geocode_address_returns_none_on_empty_results(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            return FakeResponse()

    import httpx

    async def _noop():
        return None

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: FakeClient())
    monkeypatch.setattr(geocoding_service, "_throttle", _noop)

    result = await geocoding_service.geocode_address("nonexistent place xyz")
    assert result is None


async def test_suggest_addresses_returns_shaped_candidates(monkeypatch):
    geocoding_service._suggest_cache.clear()

    async def fake_raw_search(query, limit):
        return [
            {"display_name": "14th Road, Bandra West, Mumbai, Maharashtra, India", "lat": "19.0596", "lon": "72.8295"},
            {"display_name": "14th Lane, Bandra West, Mumbai, Maharashtra, India", "lat": "19.0600", "lon": "72.8300"},
        ]

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    results = await geocoding_service.suggest_addresses("14th Road Bandra")

    assert len(results) == 2
    assert results[0]["display_name"] == "14th Road, Bandra West, Mumbai, Maharashtra, India"
    assert results[0]["lat"] == pytest.approx(19.0596)
    assert results[0]["lon"] == pytest.approx(72.8295)


async def test_suggest_addresses_too_short_query_skips_the_api_call(monkeypatch):
    geocoding_service._suggest_cache.clear()
    called = False

    async def fake_raw_search(query, limit):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    results = await geocoding_service.suggest_addresses("ab")

    assert results == []
    assert called is False


async def test_suggest_addresses_failure_returns_empty_list_not_error(monkeypatch):
    geocoding_service._suggest_cache.clear()

    async def fake_raw_search(query, limit):
        return None

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    results = await geocoding_service.suggest_addresses("some long enough query")

    assert results == []


async def test_suggest_addresses_caches_repeated_query(monkeypatch):
    geocoding_service._suggest_cache.clear()
    call_count = 0

    async def fake_raw_search(query, limit):
        nonlocal call_count
        call_count += 1
        return [{"display_name": "Somewhere", "lat": "1.0", "lon": "2.0"}]

    monkeypatch.setattr(geocoding_service, "_raw_search", fake_raw_search)

    first = await geocoding_service.suggest_addresses("14th Road Bandra")
    second = await geocoding_service.suggest_addresses("14th Road Bandra")

    assert first == second
    assert call_count == 1


class _FakeReverseResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeReverseClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        return _FakeReverseResponse(self._payload)


async def _noop_throttle():
    return None


async def test_reverse_geocode_returns_display_name(monkeypatch):
    import httpx

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: _FakeReverseClient({"display_name": "14th Road, Bandra West, Mumbai"})
    )
    monkeypatch.setattr(geocoding_service, "_throttle", _noop_throttle)

    result = await geocoding_service.reverse_geocode(19.0596, 72.8295)

    assert result == {"display_name": "14th Road, Bandra West, Mumbai"}


async def test_reverse_geocode_returns_none_when_nominatim_has_no_result(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _FakeReverseClient({}))
    monkeypatch.setattr(geocoding_service, "_throttle", _noop_throttle)

    result = await geocoding_service.reverse_geocode(0.0, 0.0)

    assert result is None


async def test_reverse_geocode_returns_none_on_request_failure(monkeypatch):
    class _RaisingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            raise RuntimeError("boom")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _RaisingClient())
    monkeypatch.setattr(geocoding_service, "_throttle", _noop_throttle)

    result = await geocoding_service.reverse_geocode(19.0596, 72.8295)

    assert result is None
