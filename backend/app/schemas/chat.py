from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.order_action import OrderSummaryResponse

IntentType = Literal[
    "menu_search",
    "recommendation",
    "order",
    "reservation",
    "faq",
    "general_chat",
    "complaint",
]
SentimentType = Literal["happy", "neutral", "angry", "confused", "urgent"]
LanguageType = Literal["en", "hi", "mr", "hinglish"]


class Filters(BaseModel):
    is_veg: bool | None = None
    is_vegan: bool | None = None
    is_gluten_free: bool | None = None
    spice_level: int | None = None
    min_spice_level: int | None = None
    max_price: float | None = None
    min_price: float | None = None
    category: str | None = None
    tag: str | None = None
    time_of_day: Literal["breakfast", "afternoon", "evening"] | None = None


class OrderItemEntry(BaseModel):
    """One distinct item within a multi-item order_action (see OrderAction.
    items) - e.g. "one cutting chai and two filter coffee" needs two of
    these in a single message, not just the first one extracted."""

    item_name: str
    quantity: int | None = None


class OrderAction(BaseModel):
    action: Literal["add", "remove", "modify", "view_summary", "checkout", "clear"]
    # Singular shorthand for a single-item action - still populated (and
    # still works end to end) when the message names only one item. `items`
    # is for multiple distinct items in one message and takes priority over
    # these when both are present - see _handle_order_intent.
    item_name: str | None = None
    quantity: int | None = None
    items: list[OrderItemEntry] | None = None


class ReservationDetails(BaseModel):
    date_phrase: str | None = None
    time_phrase: str | None = None
    guests: int | None = None
    special_requests: str | None = None


class GeminiChatOutput(BaseModel):
    """Structured output requested from Gemini in a single call."""

    reply_text: str
    intent: IntentType
    sentiment: SentimentType
    language: LanguageType = "en"
    filters: Filters | None = None
    order_action: OrderAction | None = None
    reservation_details: ReservationDetails | None = None
    faq_match: str | None = None
    detected_name: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: int | None = None
    # Set only when `message` is an address the customer picked from the
    # frontend's Nominatim autocomplete dropdown (see AddressAutocomplete.jsx) -
    # both must be present together to be trusted; the backend then uses this
    # suggestion's own lat/lon directly for the delivery-radius check instead
    # of re-geocoding the free text (see ai_service._handle_checkout_flow).
    address_lat: float | None = None
    address_lon: float | None = None


class MenuDisplayItem(BaseModel):
    """A real DB row for the rich full-menu view (see menu_context.
    get_full_menu_display) - never AI-authored, so a broad "show me
    everything" query can't hallucinate an item or price."""

    name: str
    description: str | None = None
    price: float
    category: str
    is_veg: bool
    is_vegan: bool
    is_gluten_free: bool
    spice_level: int
    tags: list[str] = []
    image_url: str | None = None


class MenuDisplayCategory(BaseModel):
    category: str
    items: list[MenuDisplayItem]


class SuggestedItem(BaseModel):
    """A real DB row for a recommendation's compact card/list view (see
    ai_service._ground_reply's recommendation branch) - a curated few
    items, not the full menu, grounded the same way as MenuDisplayItem so a
    "mood/budget/weather" suggestion can't hallucinate an item or price
    either. Shape matches menu_context._row_to_dict exactly so it can be
    handed straight through with no extra DB query."""

    name: str
    price: float
    category: str
    tags: list[str] = []
    spice_level: int
    image_url: str | None = None


class DateOption(BaseModel):
    """One selectable day in the compact 7-day date-picker (see
    quick_reply_service.day_options) - deliberately generic in shape (an
    ISO date, a short display label, and an availability flag), not
    reservation-specific, so any other date-needing guided flow later can
    reuse the same field/frontend component."""

    date: str
    label: str
    available: bool


class LoyaltyMilestone(BaseModel):
    reward: str
    tier_points: int


class LoyaltyCard(BaseModel):
    """Small progress card for the loyalty points system (feature 14) - see
    loyalty_service.format_loyalty_card. Populated after a completed order,
    or whenever the customer asks about their points/rewards (see
    ai_service._resolve_chat_result / loyalty_service.is_loyalty_question)."""

    current_points: int
    next_reward: str
    next_reward_points: int
    points_needed: int
    progress_label: str
    milestone: LoyaltyMilestone | None = None


class LocationCard(BaseModel):
    """One branch's details for the location-cards list (see
    ai_service._is_location_question) - rendered by the frontend the same
    way as other card components (LoyaltyCard, BillCard, etc.)."""

    name: str
    address: str
    hours: str
    phone: str


class WelcomeResponse(BaseModel):
    reply: str
    quick_reply_options: list[str]


class PaymentRequest(BaseModel):
    """Attached to a bot message when a mock/demo payment step is due (see
    ai_service._handle_reservation_intent's "payment" step and
    _handle_checkout_flow) - the frontend renders MockPaymentCard from this,
    a single "Pay ₹{amount}" button with a simulated processing/success
    animation, entirely client-side. No real payment gateway is ever
    involved; clicking through it just sends PAYMENT_COMPLETE_MESSAGE back
    through the normal chat pipeline, which is what actually triggers the
    real DB write (see ai_service.PAYMENT_COMPLETE_MESSAGE)."""

    amount: float
    label: str
    purpose: Literal["reservation", "order"]


class ChatResponse(BaseModel):
    reply: str
    timestamp: datetime
    intent: IntentType
    sentiment: SentimentType
    language: LanguageType = "en"
    menu_display: list[MenuDisplayCategory] | None = None
    suggested_items: list[SuggestedItem] | None = None
    order_summary: OrderSummaryResponse | None = None
    quick_reply_options: list[str] | None = None
    date_picker_options: list[DateOption] | None = None
    payment_request: PaymentRequest | None = None
    loyalty_card: LoyaltyCard | None = None
    location_cards: list[LocationCard] | None = None
    # True when this reply is freshly asking for a delivery address - the
    # frontend uses this to enable the live Nominatim autocomplete dropdown
    # under the input box (see AddressAutocomplete.jsx), not on every turn.
    awaiting_address_input: bool = False
