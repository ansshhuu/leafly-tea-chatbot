from pydantic import BaseModel


class AddressSuggestion(BaseModel):
    display_name: str
    lat: float
    lon: float


class ReverseGeocodeResult(BaseModel):
    display_name: str | None = None
