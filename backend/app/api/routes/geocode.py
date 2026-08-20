from fastapi import APIRouter, Query

from app.schemas.geocode import AddressSuggestion, ReverseGeocodeResult
from app.services import geocoding_service

router = APIRouter()


@router.get("/suggest", response_model=list[AddressSuggestion])
async def suggest_addresses(q: str = Query(..., min_length=1)) -> list[dict]:
    """Live autocomplete suggestions for a delivery address, called by the
    frontend's debounced AddressAutocomplete widget as the customer types -
    intentionally separate from the /api/chat pipeline so keystrokes never
    create chat messages or touch the LLM. Never raises - a Nominatim
    failure just yields an empty suggestion list (see suggest_addresses)."""
    return await geocoding_service.suggest_addresses(q)


@router.get("/reverse", response_model=ReverseGeocodeResult)
async def reverse_geocode(lat: float = Query(...), lon: float = Query(...)) -> dict:
    """Resolves a map pin position back to a human-readable address, called
    by the frontend's AddressMap on drag-end (debounced) as the customer
    fine-tunes their pin - separate from /api/chat for the same reason as
    /suggest. Never raises - a Nominatim failure just yields display_name:
    null, so the frontend can show a "resolving..." state and let the
    customer confirm the pin anyway."""
    result = await geocoding_service.reverse_geocode(lat, lon)
    return result or {"display_name": None}
