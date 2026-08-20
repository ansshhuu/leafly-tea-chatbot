import re
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import CAFE_LOCATIONS
from app.services import reservation_service

DATE_PICKER_DAYS_AHEAD = 7
_CANDIDATE_TIME_SLOTS = ["11:00 AM", "1:00 PM", "4:00 PM", "7:00 PM"]

QUICK_ACTION_OPTIONS = ["View Menu", "Café Location", "Book a Table", "Events & Offers"]

LOCATION_OPTIONS = [loc["name"] for loc in CAFE_LOCATIONS]


def match_location(user_message: str) -> str | None:
    """Matches free text (a picked button label, or the customer just typing
    a city/area name) to a CAFE_LOCATIONS entry - by full name or by a short
    keyword from it (e.g. "bandra", "indiranagar", "koregaon", "pune")."""
    normalized = re.sub(r"[^\w\s]", " ", user_message.lower())
    for location in CAFE_LOCATIONS:
        name_lower = location["name"].lower()
        if name_lower in user_message.lower():
            return location["name"]
        keywords = re.split(r"[,\s]+", name_lower)
        if any(keyword and keyword in normalized.split() for keyword in keywords):
            return location["name"]
    return None

_CAPABILITY_PHRASES = (
    "what can you do",
    "what do you do",
    "how can you help",
    "how do you help",
    "what can i ask you",
    "what can this bot do",
    "what are you",
    "who are you",
    "what is this",
    "what services",
    "help me",
)


def is_capability_question(user_message: str) -> bool:
    normalized = re.sub(r"[^\w\s]", "", user_message.lower())
    return any(phrase in normalized for phrase in _CAPABILITY_PHRASES)


_GREETING_WORDS = {
    "hi",
    "hii",
    "hiya",
    "hello",
    "hellow",
    "hey",
    "heya",
    "yo",
    "sup",
    "namaste",
    "namaskar",
    "namaskaar",
}
_GREETING_PHRASES = (
    "good morning",
    "good afternoon",
    "good evening",
    "whats up",
    "what s up",
    "kaise ho",
    "kaise ho aap",
    "kya haal hai",
    "kese ho",
)


def is_greeting(user_message: str) -> bool:
    normalized = re.sub(r"[^\w\s]", " ", user_message.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return False
    if any(normalized == phrase or normalized.startswith(phrase + " ") for phrase in _GREETING_PHRASES):
        return True
    words = normalized.split()
    return len(words) <= 3 and words[0] in _GREETING_WORDS


async def time_options(
    db: AsyncSession, slot_date: date, guests: int, now: datetime | None = None, location: str | None = None
) -> list[str]:
    available: list[str] = []
    for label in _CANDIDATE_TIME_SLOTS:
        slot_time = datetime.strptime(label, "%I:%M %p").time()
        availability = await reservation_service.check_availability(
            db, slot_date, slot_time, guests, now=now, location=location
        )
        if availability["available"]:
            available.append(label)
    return available


async def day_options(
    db: AsyncSession,
    guests: int = 1,
    days_ahead: int = DATE_PICKER_DAYS_AHEAD,
    now: datetime | None = None,
    location: str | None = None,
) -> list[dict]:
    now = now or datetime.now()
    today = now.date()

    days: list[dict] = []
    for offset in range(days_ahead):
        day = today + timedelta(days=offset)
        has_room = False
        for label in _CANDIDATE_TIME_SLOTS:
            slot_time = datetime.strptime(label, "%I:%M %p").time()
            availability = await reservation_service.check_availability(
                db, day, slot_time, guests, now=now, location=location
            )
            if availability["available"]:
                has_room = True
                break
        days.append({"date": day.isoformat(), "label": f"{day.strftime('%a')} {day.day}", "available": has_room})

    return days
