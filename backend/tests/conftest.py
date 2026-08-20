import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.session import Base
from app.services import (
    addon_service,
    cache_service,
    checkout_draft_service,
    feedback_service,
    menu_cache_service,
    reservation_draft_service,
    reservation_service,
    session_context_service,
    session_service,
    weather_service,
)
from app.services.rate_limiter import rate_limiter


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def _enforce_test_mode(monkeypatch):
    monkeypatch.setattr(settings, "test_mode", True)
    yield


@pytest.fixture(autouse=True)
def _disable_real_email_sends(monkeypatch):
    # Regression guard: ai_service tests drive full checkout/reservation
    # flows through process_chat_message() without ever mocking
    # email_service, and settings loads the REAL BREVO_API_KEY from .env (it
    # isn't test-mode-gated - only Gemini calls are). Every test that
    # completes a checkout was therefore hitting the live Brevo API and
    # sending real emails on every test run, which silently burned through
    # the account's daily free-tier send quota and caused real customer
    # order-confirmation emails to fail with "insufficient credits" once
    # exhausted. Blanking the key here makes email_service._send() take its
    # already-existing "not configured" no-op path by default; tests that
    # actually need to exercise the Brevo call path (test_email_service.py)
    # explicitly re-set it themselves after this fixture runs.
    monkeypatch.setattr(settings, "brevo_api_key", None)
    yield


@pytest.fixture(autouse=True)
def _reset_shared_state():
    cache_service.clear()
    session_context_service.clear()
    reservation_draft_service.clear()
    checkout_draft_service.clear()
    feedback_service.clear()
    addon_service.clear()
    session_service.clear()
    weather_service.clear()
    menu_cache_service.clear()
    reservation_service._last_reminder_check = None
    rate_limiter._minute_key = None
    rate_limiter._minute_count = 0
    rate_limiter._day_key = None
    rate_limiter._day_count = 0
    yield
