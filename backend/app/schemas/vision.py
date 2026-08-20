from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.chat import IntentType, LanguageType, SentimentType, SuggestedItem

ImageType = Literal["menu_item", "receipt", "bot_avatar", "other"]


class ImageAnalysisOutput(BaseModel):
    """Structured output from the vision call."""

    image_type: ImageType
    description: str
    # ONLY meaningful when image_type is "menu_item" - a plain, generic name
    # for the specific food/drink shown (e.g. "Coca-Cola", "vegetable fried
    # noodles", "masala chai") - NOT necessarily one of our menu items, just
    # an honest identification. The backend does a simple exact/near-exact
    # NAME match against the real menu from this - see vision_service.py.
    identified_name: str | None = None


class ChatImageResponse(BaseModel):
    reply: str
    timestamp: datetime
    intent: IntentType
    sentiment: SentimentType
    language: LanguageType = "en"
    suggested_items: list[SuggestedItem] | None = None
