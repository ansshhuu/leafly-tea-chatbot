from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Leafly Tea Assistant"
    env: str = "development"

    database_url: str = "postgresql+asyncpg://leafly_user:leafly_password@localhost:5432/leafly_db"
    sync_database_url: str = "postgresql+psycopg2://leafly_user:leafly_password@localhost:5432/leafly_db"

    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"

    gemini_rpm_limit: int = 12
    gemini_rpd_limit: int = 450

    brevo_api_key: str | None = None

    test_mode: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:3000,https://leafly-tea-store-ten.vercel.app"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


BRAND_NAME = "Leafly"
TAGLINES = [
    "Pure by Nature",
    "Better Tea. Better World. Better You.",
    "Rooted in care, crafted for you.",
]

# Brand pillars used in the assistant persona and about/FAQ content.
BRAND_PILLARS = [
    {
        "name": "Real Leaves",
        "description": "Whole, unbroken leaves for a pure, uncompromised flavor.",
    },
    {
        "name": "Single Origin",
        "description": "Teas sourced from distinct regions, each with its own clear character and story.",
    },
    {
        "name": "Ethical & Sustainable",
        "description": "Responsible sourcing, fair partnerships with growers, and a lighter footprint.",
    },
    {
        "name": "Crafted with Care",
        "description": "Small-batch blended and packed for freshness.",
    },
]

CONTACT_EMAIL = "hello@leafly.com"

EMAIL_FROM_NAME = "Leafly"
EMAIL_FROM_ADDRESS = "hello@leafly.com"
