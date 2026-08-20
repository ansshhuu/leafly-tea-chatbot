from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Smart Cafe Assistant"
    env: str = "development"

    database_url: str = "postgresql+asyncpg://cafe_user:cafe_password@localhost:5432/cafe_db"
    sync_database_url: str = "postgresql+psycopg2://cafe_user:cafe_password@localhost:5432/cafe_db"

    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"

    gemini_rpm_limit: int = 12
    gemini_rpd_limit: int = 450

    brevo_api_key: str | None = None

    test_mode: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:3000,https://cafe-chatbot-seven.vercel.app"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


MAX_CAPACITY_PER_SLOT = 40
SLOT_DURATION_MINUTES = 90
TAX_RATE = 0.05
DELIVERY_RADIUS_KM = 10

CAFE_LOCATIONS = [
    {
        "name": "Bandra West, Mumbai",
        "address": "14th Road, Off Linking Rd, Bandra West, Mumbai, Maharashtra – 400050",
        "hours": "8:00 AM – 11:00 PM",
        "phone": "+91 98200 12345",
        "latitude": 19.0596,
        "longitude": 72.8295,
    },
    {
        "name": "Indiranagar, Bengaluru",
        "address": "100 Feet Rd, 12th Main, Indiranagar, Bengaluru, Karnataka – 560038",
        "hours": "7:30 AM – 10:30 PM",
        "phone": "+91 98450 67890",
        "latitude": 12.9716,
        "longitude": 77.6412,
    },
    {
        "name": "Koregaon Park, Pune",
        "address": "Lane 6, North Main Rd, Koregaon Park, Pune, Maharashtra – 411001",
        "hours": "8:00 AM – 10:30 PM",
        "phone": "+91 98220 54321",
        "latitude": 18.5362,
        "longitude": 73.8938,
    },
]

# Legacy singular constants (e.g. escalation/reservation-capacity messages
# that aren't branch-specific) still default to the original Bandra West
# location - reservation/pickup flows now ask which branch explicitly (see
# reservation_draft_service/checkout_draft_service "location" step).
CAFE_ADDRESS = CAFE_LOCATIONS[0]["address"]
CAFE_PHONE = CAFE_LOCATIONS[0]["phone"]
DEFAULT_LOCATION_NAME = CAFE_LOCATIONS[0]["name"]

# Per-weekday open/close hours, keyed by CAFE_LOCATIONS "name". Bandra keeps
# its original varying weekday schedule (later close Fri/Sat, later open
# Sun); the two newer branches only have a single flat hours range each
# (see CAFE_LOCATIONS "hours" strings), so the same range is applied to
# every day of the week for those two.
CAFE_HOURS_BY_LOCATION: dict[str, dict[str, dict[str, str]]] = {
    "Bandra West, Mumbai": {
        "monday": {"open": "08:00", "close": "22:00"},
        "tuesday": {"open": "08:00", "close": "22:00"},
        "wednesday": {"open": "08:00", "close": "22:00"},
        "thursday": {"open": "08:00", "close": "22:00"},
        "friday": {"open": "08:00", "close": "23:00"},
        "saturday": {"open": "08:00", "close": "23:00"},
        "sunday": {"open": "09:00", "close": "22:00"},
    },
    "Indiranagar, Bengaluru": {
        day: {"open": "07:30", "close": "22:30"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    },
    "Koregaon Park, Pune": {
        day: {"open": "08:00", "close": "22:30"}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    },
}

# Back-compat alias for any code that still wants "the" cafe hours (Bandra).
CAFE_HOURS = CAFE_HOURS_BY_LOCATION[DEFAULT_LOCATION_NAME]


def get_location(name: str | None) -> dict:
    """Looks up a CAFE_LOCATIONS entry by name, falling back to the default
    (Bandra West) branch for None/unrecognized names."""
    for location in CAFE_LOCATIONS:
        if location["name"] == name:
            return location
    return CAFE_LOCATIONS[0]


EMAIL_FROM_NAME = "Rasa Café"
EMAIL_FROM_ADDRESS = "anshupanwar20005@gmail.com"

CAFE_INTERNAL_EMAIL = "xqoratechnologies.ai.ap@gmail.com"

COUPONS = [
    {"code": "SAVE10", "min_order": 200, "discount_type": "percent", "value": 10},
    {"code": "FLAT50", "min_order": 400, "discount_type": "flat", "value": 50},
    {"code": "WELCOME20", "min_order": 150, "discount_type": "percent", "value": 20, "first_order_only": True},
]

LOYALTY_POINTS_PER_RUPEES = 100

LOYALTY_REWARD_TIERS = [
    {"points": 100, "reward": "Free Samosa"},
    {"points": 250, "reward": "Free Filter Coffee"},
    {"points": 500, "reward": "₹100 off next order"},
]
