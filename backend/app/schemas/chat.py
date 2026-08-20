from datetime import datetime
from typing import Literal

from pydantic import BaseModel

IntentType = Literal[
    "menu_search",
    "recommendation",
    "faq",
    "general_chat",
    "complaint",
]
SentimentType = Literal["happy", "neutral", "angry", "confused", "urgent"]
LanguageType = Literal["en", "hi", "hinglish"]


class Filters(BaseModel):
    tea_type: str | None = None
    origin: str | None = None
    caffeine_level: str | None = None
    badge: str | None = None
    is_hamper: bool | None = None
    max_price: float | None = None
    min_price: float | None = None
    tag: str | None = None


class GeminiChatOutput(BaseModel):
    """Structured output requested from Gemini in a single call."""

    reply_text: str
    intent: IntentType
    sentiment: SentimentType
    language: LanguageType = "en"
    filters: Filters | None = None
    faq_match: str | None = None
    detected_name: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: int | None = None


class SizeOption(BaseModel):
    size: str
    price: float


class MenuDisplayItem(BaseModel):
    """A real DB row for the rich full-catalog view (see product_context.
    get_full_product_display) - never AI-authored, so a broad "show me
    everything" query can't hallucinate a product or price."""

    name: str
    description: str | None = None
    price: float
    compare_at_price: float | None = None
    origin: str | None = None
    tea_type: str | None = None
    caffeine_level: str | None = None
    size_options: list[SizeOption] = []
    badge: str | None = None
    is_hamper: bool = False
    hamper_contents: list[str] = []
    tags: list[str] = []
    image_url: str | None = None


class MenuDisplayCategory(BaseModel):
    category: str
    items: list[MenuDisplayItem]


class SuggestedItem(BaseModel):
    """A real DB row for a recommendation's compact card/list view (see
    ai_service._ground_reply's recommendation branch) - a curated few
    items, not the full catalog, grounded the same way as MenuDisplayItem so
    a "mood/budget/caffeine" suggestion can't hallucinate a product or price
    either. Shape matches product_context._row_to_dict exactly so it can be
    handed straight through with no extra DB query."""

    name: str
    price: float
    origin: str | None = None
    tea_type: str | None = None
    caffeine_level: str | None = None
    badge: str | None = None
    tags: list[str] = []
    image_url: str | None = None


class WelcomeResponse(BaseModel):
    reply: str
    quick_reply_options: list[str]


class ChatResponse(BaseModel):
    reply: str
    timestamp: datetime
    intent: IntentType
    sentiment: SentimentType
    language: LanguageType = "en"
    menu_display: list[MenuDisplayCategory] | None = None
    suggested_items: list[SuggestedItem] | None = None
    quick_reply_options: list[str] | None = None
