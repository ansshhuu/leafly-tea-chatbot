from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import geocoding_service


async def test_suggest_endpoint_returns_shaped_suggestions(monkeypatch):
    async def fake_suggest(query, limit=5):
        return [{"display_name": "14th Road, Bandra West, Mumbai", "lat": 19.0596, "lon": 72.8295}]

    monkeypatch.setattr(geocoding_service, "suggest_addresses", fake_suggest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/geocode/suggest", params={"q": "14th Road Bandra"})

    assert response.status_code == 200
    body = response.json()
    assert body == [{"display_name": "14th Road, Bandra West, Mumbai", "lat": 19.0596, "lon": 72.8295}]


async def test_suggest_endpoint_never_errors_on_geocoding_failure(monkeypatch):
    async def fake_suggest(query, limit=5):
        return []

    monkeypatch.setattr(geocoding_service, "suggest_addresses", fake_suggest)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/geocode/suggest", params={"q": "asdkjaslkdj"})

    assert response.status_code == 200
    assert response.json() == []


async def test_suggest_endpoint_requires_query_param():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/geocode/suggest")

    assert response.status_code == 422


async def test_reverse_endpoint_returns_display_name(monkeypatch):
    async def fake_reverse(lat, lon):
        return {"display_name": "14th Road, Bandra West, Mumbai"}

    monkeypatch.setattr(geocoding_service, "reverse_geocode", fake_reverse)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/geocode/reverse", params={"lat": 19.0596, "lon": 72.8295})

    assert response.status_code == 200
    assert response.json() == {"display_name": "14th Road, Bandra West, Mumbai"}


async def test_reverse_endpoint_never_errors_on_geocoding_failure(monkeypatch):
    async def fake_reverse(lat, lon):
        return None

    monkeypatch.setattr(geocoding_service, "reverse_geocode", fake_reverse)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/geocode/reverse", params={"lat": 0.0, "lon": 0.0})

    assert response.status_code == 200
    assert response.json() == {"display_name": None}


async def test_reverse_endpoint_requires_lat_lon():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/geocode/reverse")

    assert response.status_code == 422
