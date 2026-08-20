import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import CAFE_PHONE
from app.models.escalation import Escalation
from app.models.feedback import Feedback
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.prompts.system_prompt import build_system_prompt
from app.schemas.chat import Filters, GeminiChatOutput, OrderAction, OrderItemEntry, ReservationDetails
from app.services import (
    ai_service,
    cache_service,
    checkout_draft_service,
    customer_profile_service,
    feedback_service,
    loyalty_service,
    order_service,
    quick_reply_service,
    reservation_draft_service,
    session_context_service,
)
from app.services.rate_limiter import rate_limiter


def make_fake_call(output: GeminiChatOutput, tokens: int = 123):
    return AsyncMock(return_value=(output, tokens))


async def _seed_menu(db_session):
    db_session.add_all(
        [
            MenuItem(name="Masala Chai", price=80, category="Hot Beverages", is_veg=True, spice_level=0, tags=["chai", "hot"]),
            MenuItem(name="Samosa", price=60, category="Snacks", is_veg=True, spice_level=2, tags=["snack", "spicy"]),
            MenuItem(name="Cold Brew", price=160, category="Cold Beverages", is_veg=True, is_vegan=True, spice_level=0, tags=["coffee", "cold"]),
            MenuItem(name="Butter Croissant", price=120, category="Bakery", is_veg=False, spice_level=0, tags=["bakery"], available=True),
            MenuItem(name="Old Special", price=50, category="Snacks", is_veg=True, spice_level=0, tags=[], available=False),
        ]
    )
    await db_session.commit()


async def test_process_chat_message_happy_path_general_chat(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Hello, how can I help?", intent="general_chat", sentiment="happy")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-1", "hi there")

    assert result["reply_text"] == "Hello, how can I help?"
    assert result["intent"] == "general_chat"
    assert result["sentiment"] == "happy"

    history = await ai_service._fetch_recent_history(db_session, "session-1")
    assert [h.role for h in history] == ["user", "assistant"]
    assert history[0].message == "hi there"
    assert history[1].message == "Hello, how can I help?"


async def test_menu_search_reply_is_grounded_in_db_and_excludes_non_matching_items(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, here's what we've got!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(is_veg=True, max_price=100),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-2", "any cheap veg snacks?")

    assert "Sure, here's what we've got!" in result["reply_text"]
    names = {item["name"] for item in result["suggested_items"]}
    assert {"Masala Chai", "Samosa"} <= names
    assert "Cold Brew" not in names
    assert "Butter Croissant" not in names
    assert "Old Special" not in names


async def test_menu_search_reply_never_bakes_items_into_reply_text(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, here's what we've got!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(is_veg=True, max_price=100),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-2b", "any cheap veg snacks?")

    assert result["reply_text"] == "Sure, here's what we've got!"
    assert "\n-" not in result["reply_text"]
    assert "tags:" not in result["reply_text"]
    assert "Rs." not in result["reply_text"]
    assert result["suggested_items"]
    assert result["suggested_items"][0]["name"] == "Samosa"
    assert result["suggested_items"][0]["price"] == 60.0


async def test_menu_search_with_no_matches_falls_back_to_closest_available_item(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Let me check that for you.",
        intent="menu_search",
        sentiment="neutral",
        filters=Filters(is_vegan=True, max_price=10),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-3", "vegan food under 10 rupees")

    assert "Nothing quite that cheap right now" in result["reply_text"]
    assert result["suggested_items"][0]["name"] == "Cold Brew"


async def test_menu_search_no_matches_with_totally_empty_menu_gives_honest_message(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Let me check that for you.",
        intent="menu_search",
        sentiment="neutral",
        filters=Filters(is_vegan=True, max_price=10),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-3b", "vegan food under 10 rupees")

    assert "couldn't find anything on the menu matching that" in result["reply_text"]
    assert result.get("suggested_items") is None


async def test_menu_search_no_spicy_enough_match_falls_back_to_mildest_option(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Let me check.",
        intent="menu_search",
        sentiment="neutral",
        filters=Filters(category="Snacks", spice_level=0),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-3c", "any mild snacks?")

    assert "gentlest option" in result["reply_text"]
    assert result["suggested_items"][0]["name"] == "Samosa"


async def test_menu_search_spicy_request_returns_only_spicy_items(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Let me find something with a kick!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(min_spice_level=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-spicy", "I want something spicy")

    names = {item["name"] for item in result["suggested_items"]}
    assert names == {"Samosa"}
    assert "Masala Chai" not in names


async def test_menu_search_no_gluten_free_match_says_fallback_is_not_gluten_free(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Let me check.",
        intent="menu_search",
        sentiment="neutral",
        filters=Filters(category="Bakery", is_gluten_free=True),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-3d", "gluten-free bakery items?")

    assert "not gluten-free" in result["reply_text"]
    assert result["suggested_items"][0]["name"] == "Butter Croissant"


async def test_recommendation_uses_time_of_day_filter_not_literal_category(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Great pick for the morning!",
        intent="recommendation",
        sentiment="happy",
        filters=Filters(time_of_day="breakfast"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-4b", "recommend a breakfast item")

    assert "couldn't find anything" not in result["reply_text"]
    assert result["reply_text"] == "Great pick for the morning!"
    assert result["suggested_items"][0]["name"] == "Masala Chai"


async def test_recommendation_reply_applies_dietary_hard_filter(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Here's a suggestion!",
        intent="recommendation",
        sentiment="happy",
        filters=Filters(is_veg=True),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-4", "recommend something")

    suggested_names = {item["name"] for item in result["suggested_items"]}
    assert "Butter Croissant" not in suggested_names
    assert "Old Special" not in suggested_names


async def test_recommendation_budget_too_tight_for_combo_suggests_cheapest_single_item(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Let me see what fits!",
        intent="recommendation",
        sentiment="happy",
        filters=Filters(max_price=100),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-combo", "recommend a combo under 100 rupees")

    assert len(result["suggested_items"]) == 1
    assert result["suggested_items"][0]["name"] == "Samosa"


async def test_menu_search_result_is_served_from_cache_on_repeat_query(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(reply_text="Sure!", intent="menu_search", sentiment="happy", filters=Filters(is_veg=True))
    mock_call = make_fake_call(output)
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)

    await ai_service.process_chat_message(db_session, "session-5", "veg snacks please")
    await ai_service.process_chat_message(db_session, "session-5", "  Veg Snacks Please  ")

    assert mock_call.await_count == 1


async def test_menu_search_cache_hit_still_translates_item_names(db_session, monkeypatch):
    # Regression: a cache hit used to return the cached dict completely
    # as-is, bypassing translation - so an entry cached before the
    # translation step existed (or under a stale/differently-detected
    # language) would keep serving untranslated item names for its whole
    # TTL even after the underlying bug was fixed. Simulate exactly that:
    # seed a cache entry whose language says "hi" but whose menu_display
    # items were never translated.
    await _seed_menu(db_session)
    stale_cached_result = {
        "reply_text": "यहाँ हमारा मेनू है!",
        "intent": "menu_search",
        "sentiment": "happy",
        "language": "hi",
        "filters": None,
        "menu_display": [{"category": "Snacks", "items": [{"name": "Samosa", "description": None, "price": 60.0}]}],
    }
    cache_service.set_cached("menu dikhao", stale_cached_result)

    result = await ai_service.process_chat_message(db_session, "session-stale-cache", "menu dikhao")

    assert result["menu_display"][0]["items"][0]["name"] == "समोसा"


async def test_general_chat_is_never_cached(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Hi!", intent="general_chat", sentiment="happy")
    mock_call = make_fake_call(output)
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)

    await ai_service.process_chat_message(db_session, "session-6", "hello there")
    await ai_service.process_chat_message(db_session, "session-6", "hello there")

    assert mock_call.await_count == 2


async def test_general_chat_capability_question_offers_quick_actions(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="I can help you browse the menu, book a table, and more!",
        intent="general_chat",
        sentiment="happy",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-capability", "what can you do?")

    assert result["quick_reply_options"] == ["View Menu", "Café Location", "Book a Table", "Events & Offers"]


async def test_general_chat_plain_smalltalk_has_no_quick_actions(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Haha, glad to hear it!", intent="general_chat", sentiment="happy")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-smalltalk", "thanks, you're great")

    assert result.get("quick_reply_options") is None


async def test_general_chat_greeting_offers_quick_actions_mid_conversation(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Hey again!", intent="general_chat", sentiment="happy")
    mock_call = make_fake_call(output)
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)

    await ai_service.process_chat_message(db_session, "session-greeting", "what's on the menu")
    await ai_service.process_chat_message(db_session, "session-greeting", "thanks")
    result = await ai_service.process_chat_message(db_session, "session-greeting", "hi")

    assert mock_call.await_count == 3
    assert result["quick_reply_options"] == ["View Menu", "Café Location", "Book a Table", "Events & Offers"]


async def test_general_chat_capability_question_offers_quick_actions_mid_conversation(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Sure, here's what I can do!", intent="general_chat", sentiment="happy")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "session-capability-2", "hello")
    await ai_service.process_chat_message(db_session, "session-capability-2", "how much is a samosa")
    result = await ai_service.process_chat_message(db_session, "session-capability-2", "what can you do")

    assert result["quick_reply_options"] == ["View Menu", "Café Location", "Book a Table", "Events & Offers"]


async def test_emoji_only_message_gets_fixed_reply_without_calling_gemini(db_session, monkeypatch):
    mock_call = AsyncMock()
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)

    result = await ai_service.process_chat_message(db_session, "session-emoji", "🥰🥰🥰🥰")

    assert result["reply_text"] == ai_service.EMOJI_ONLY_REPLY
    assert result["intent"] == "general_chat"
    mock_call.assert_not_awaited()

    history = await ai_service._fetch_recent_history(db_session, "session-emoji")
    assert history[0].message == "🥰🥰🥰🥰"
    assert history[1].message == ai_service.EMOJI_ONLY_REPLY


async def test_is_emoji_only():
    assert ai_service._is_emoji_only("🥰🥰🥰🥰")
    assert ai_service._is_emoji_only("  😀 ")
    assert not ai_service._is_emoji_only("Anshu 🥰")
    assert not ai_service._is_emoji_only("hi")
    assert not ai_service._is_emoji_only("")
    assert not ai_service._is_emoji_only("   ")


async def test_detected_name_is_remembered_and_injected_into_later_context(db_session, monkeypatch):
    first_output = GeminiChatOutput(
        reply_text="Hi Anshu! Great to meet you 😊",
        intent="general_chat",
        sentiment="happy",
        detected_name="Anshu",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(first_output))

    await ai_service.process_chat_message(db_session, "session-name", "Anshu 🥰")

    assert await session_context_service.get_name(db_session, "session-name") == "Anshu"

    context = await ai_service._build_pre_call_context(db_session, "what's good today?", "session-name")
    assert "Anshu" in context


async def test_detected_name_not_re_extracted_stays_remembered(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Sure!", intent="general_chat", sentiment="happy", detected_name=None)
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await session_context_service.remember_name(db_session, "session-name-2", "Priya")
    await ai_service.process_chat_message(db_session, "session-name-2", "thanks")

    assert await session_context_service.get_name(db_session, "session-name-2") == "Priya"


async def test_rate_limit_returns_fallback_without_calling_gemini(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Sure!", intent="menu_search", sentiment="happy")
    mock_call = make_fake_call(output)
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)
    monkeypatch.setattr(rate_limiter, "is_within_limits", lambda: False)

    result = await ai_service.process_chat_message(db_session, "session-7", "hello")

    assert result["reply_text"] == ai_service.FALLBACK_MESSAGE
    assert result["intent"] == "general_chat"
    mock_call.assert_not_awaited()


async def test_gemini_error_returns_fallback_gracefully(db_session, monkeypatch):
    monkeypatch.setattr(ai_service, "_call_gemini", AsyncMock(side_effect=RuntimeError("boom")))

    result = await ai_service.process_chat_message(db_session, "session-8", "hello")

    assert result["reply_text"] == ai_service.FALLBACK_MESSAGE
    assert result["intent"] == "general_chat"
    assert result["sentiment"] == "neutral"


async def test_previous_order_hint_only_fetched_when_message_references_it(db_session, monkeypatch):
    """Regression test: the "previous order" hint used to be keyed by a
    client-supplied, unauthenticated `user_id` from the request body - since
    this app has no auth, ANY caller could pass an arbitrary user_id and get
    a hint of a stranger's order history injected into Gemini's context.
    Fixed to key off session_id instead (the one identifier this app
    actually trusts, since it's never client-supplied for someone else's
    conversation - see recommendation_service.get_previous_order_summary)."""
    await _seed_menu(db_session)
    order = Order(session_id="session-hint", status="confirmed")
    db_session.add(order)
    await db_session.flush()
    db_session.add(OrderItem(order_id=order.id, menu_item_id=1, quantity=2, price_at_order=80))
    await db_session.commit()

    output = GeminiChatOutput(reply_text="Sure, same as usual!", intent="order", sentiment="happy")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    context_with_hint = await ai_service._build_pre_call_context(
        db_session, "same as last time please", session_id="session-hint"
    )
    context_without_hint = await ai_service._build_pre_call_context(
        db_session, "hi there", session_id="session-hint"
    )
    context_other_session = await ai_service._build_pre_call_context(
        db_session, "same as last time please", session_id="session-someone-else"
    )

    assert "previous order included" in context_with_hint
    assert "previous order included" not in context_without_hint
    assert "previous order included" not in context_other_session


def test_build_system_prompt_includes_dynamic_context_when_present():
    prompt = build_system_prompt("Popular items right now:\n- Masala Chai (Rs.80, Hot Beverages)")
    assert "Masala Chai" in prompt

    prompt_without_context = build_system_prompt("")
    assert "Popular items" not in prompt_without_context


def test_system_prompt_separates_time_of_day_from_category():
    prompt = build_system_prompt("")
    assert "time_of_day" in prompt
    assert "NEVER put a time-of-day word there" in prompt


def test_system_prompt_requires_escalation_for_angry_or_urgent_sentiment():
    prompt = build_system_prompt("")
    assert "angry" in prompt and "urgent" in prompt
    assert "manager" in prompt or "staff" in prompt


def test_system_prompt_instructs_natural_reply_not_raw_data_dump():
    prompt = build_system_prompt("")
    assert "never" in prompt.lower()
    assert "(Rs.X, category, tags)" in prompt


def test_system_prompt_requires_english_phrases_for_order_and_reservation_extraction():
    prompt = build_system_prompt("")
    assert "item_name must stay in English/Romanized form" in prompt
    assert "IMPORTANT: date_phrase and\n  time_phrase must ALWAYS be in English/numeric form" in prompt


async def test_order_intent_add_item_reply_uses_python_computed_total(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, one moment!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa", quantity=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "order-session-1", "add 2 samosas")

    assert "Added 2 x Samosa" in result["reply_text"]
    assert "Rs.126.00" in result["reply_text"]


async def test_order_intent_add_multiple_distinct_items_in_one_message(db_session, monkeypatch):
    # Regression: "one cutting chai and two filter coffee" used to only add
    # the first item and silently drop the rest - order_action.items must
    # carry every distinct item named, and all of them must be added.
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, one moment!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(
            action="add",
            items=[
                OrderItemEntry(item_name="masala chai", quantity=1),
                OrderItemEntry(item_name="cold brew", quantity=2),
            ],
        ),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(
        db_session, "order-session-multi", "one masala chai and two cold brew"
    )

    assert "1 x Masala Chai" in result["reply_text"]
    assert "2 x Cold Brew" in result["reply_text"]
    assert "Rs.420.00" in result["reply_text"]  # (80 + 2*160) + 5% tax

    summary = await order_service.get_order_summary(
        db_session, (await order_service.get_or_create_draft_order(db_session, "order-session-multi", None)).id
    )
    names_and_qty = {item["name"]: item["quantity"] for item in summary["items"]}
    assert names_and_qty == {"Masala Chai": 1, "Cold Brew": 2}


async def test_order_intent_add_multiple_items_and_upsell_are_fully_in_hindi(db_session, monkeypatch):
    # Regression: item names inside order_added_multi and the upsell
    # suggestion suffix were never translated, so a Hindi reply ended up
    # mixed with raw English item names ("...जोड़ दिया गया है... Want to add
    # Butter Croissant with that?").
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="ज़रूर!",
        intent="order",
        sentiment="happy",
        language="hi",
        order_action=OrderAction(
            action="add",
            items=[
                OrderItemEntry(item_name="masala chai", quantity=1),
                OrderItemEntry(item_name="cold brew", quantity=1),
            ],
        ),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "order-session-multi-hi", "एक मसाला चाय और एक कोल्ड ब्रू")

    assert "मसाला चाय" in result["reply_text"]
    assert "कोल्ड ब्रू" in result["reply_text"]
    assert "बटर क्रोइसां" in result["reply_text"]
    assert "Masala Chai" not in result["reply_text"]
    assert "Cold Brew" not in result["reply_text"]
    assert "Butter Croissant" not in result["reply_text"]
    assert "Want to add" not in result["reply_text"]


async def test_order_intent_add_multiple_items_one_not_on_menu_still_adds_the_rest(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, one moment!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(
            action="add",
            items=[
                OrderItemEntry(item_name="samosa", quantity=1),
                OrderItemEntry(item_name="pizza", quantity=1),
            ],
        ),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "order-session-multi-partial", "a samosa and a pizza")

    assert "Added 1 x Samosa" in result["reply_text"]
    assert "couldn't find" in result["reply_text"].lower()
    assert "pizza" in result["reply_text"].lower()


async def test_order_intent_confirmation_respects_detected_language(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="ज़रूर, एक पल दीजिए!",
        intent="order",
        sentiment="happy",
        language="hi",
        order_action=OrderAction(action="add", item_name="samosa", quantity=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "order-session-hi", "मुझे 2 समोसे चाहिए")

    assert result["language"] == "hi"
    assert "समोसा" in result["reply_text"]
    assert "Samosa" not in result["reply_text"]
    assert "जोड़ दिया गया है" in result["reply_text"]
    assert "Rs.126.00" in result["reply_text"]


async def test_reservation_intent_confirmation_respects_detected_language(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="ज़रूर, देखते हैं!",
        intent="reservation",
        sentiment="happy",
        language="hi",
        reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "res-session-hi", "कल शाम 7 बजे 2 लोगों के लिए टेबल बुक करें")
    result = await ai_service.process_chat_message(db_session, "res-session-hi", "Bandra West, Mumbai")

    assert "नाम" in result["reply_text"]


async def test_order_intent_unknown_item_gives_clarifying_reply(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, one moment!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="add", item_name="pizza", quantity=1),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "order-session-2", "add a pizza")

    assert "couldn't find" in result["reply_text"]


async def test_order_intent_add_compound_typed_together_asks_for_clarification(db_session, monkeypatch):
    # "samosa pav" isn't a real menu item (Samosa and Vada Pav are separate),
    # and isn't itself an unambiguous request for TWO items either - it must
    # ask the customer to confirm rather than silently adding both (or
    # rejecting it as a fabricated "samosapav" that's "unavailable").
    await _seed_menu(db_session)
    db_session.add(MenuItem(name="Vada Pav", price=70, category="Snacks", is_veg=True, spice_level=2, tags=["snack"]))
    await db_session.commit()

    output = GeminiChatOutput(
        reply_text="Sure, one moment!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa pav", quantity=1),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "order-session-samosa-pav", "add samosa pav")

    assert "unavailable" not in result["reply_text"].lower()
    assert "samosapav" not in result["reply_text"].lower()
    assert "don't have" in result["reply_text"].lower()
    assert "Samosa" in result["reply_text"]
    assert "Vada Pav" in result["reply_text"]
    assert "both" in result["reply_text"].lower()

    order = await order_service.get_or_create_draft_order(db_session, "order-session-samosa-pav", None)
    summary = await order_service.get_order_summary(db_session, order.id)
    assert summary["items"] == []


async def test_order_intent_clear_cart_empties_order_and_drops_bill_card(db_session, monkeypatch):
    await _seed_menu(db_session)
    add_output = GeminiChatOutput(
        reply_text="Sure!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa", quantity=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(add_output))
    await ai_service.process_chat_message(db_session, "order-session-clear", "add 2 samosas")

    clear_output = GeminiChatOutput(
        reply_text="Sure!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="clear"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(clear_output))
    result = await ai_service.process_chat_message(db_session, "order-session-clear", "clear my cart")

    assert result["order_summary"] is None

    order = await order_service.get_or_create_draft_order(db_session, "order-session-clear", None)
    summary = await order_service.get_order_summary(db_session, order.id)
    assert summary["items"] == []
    assert summary["total"] == 0.0


async def test_order_intent_start_over_phrase_also_clears_cart(db_session, monkeypatch):
    # "start over"/"cancel my order" must resolve to the same clear action as
    # "clear my cart" - Python only sees whatever action Gemini extracted, so
    # this just confirms the "clear" action itself is wired up end to end.
    await _seed_menu(db_session)
    add_output = GeminiChatOutput(
        reply_text="Sure!", intent="order", sentiment="happy",
        order_action=OrderAction(action="add", item_name="masala chai", quantity=1),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(add_output))
    await ai_service.process_chat_message(db_session, "order-session-start-over", "one masala chai")

    clear_output = GeminiChatOutput(
        reply_text="No problem!", intent="order", sentiment="happy", order_action=OrderAction(action="clear"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(clear_output))
    result = await ai_service.process_chat_message(db_session, "order-session-start-over", "start over")

    assert result["order_summary"] is None


async def test_menu_display_language_matches_current_message_and_switches_back(db_session, monkeypatch):
    await _seed_menu(db_session)

    en_output = GeminiChatOutput(
        reply_text="Here's our full menu!", intent="menu_search", sentiment="happy", language="en", filters=None,
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(en_output))
    en_result = await ai_service.process_chat_message(db_session, "menu-lang-session", "what do you have?")
    en_names = {item["name"] for cat in en_result["menu_display"] for item in cat["items"]}
    assert "Samosa" in en_names
    assert "समोसा" not in en_names

    hi_output = GeminiChatOutput(
        reply_text="यह रहा हमारा पूरा मेनू!", intent="menu_search", sentiment="happy", language="hi", filters=None,
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(hi_output))
    hi_result = await ai_service.process_chat_message(db_session, "menu-lang-session", "मेनू दिखाओ")
    hi_names = {item["name"] for cat in hi_result["menu_display"] for item in cat["items"]}
    assert "समोसा" in hi_names
    assert "Samosa" not in hi_names

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(en_output))
    en_again_result = await ai_service.process_chat_message(db_session, "menu-lang-session", "show me the menu again")
    en_again_names = {item["name"] for cat in en_again_result["menu_display"] for item in cat["items"]}
    assert "Samosa" in en_again_names
    assert "समोसा" not in en_again_names


async def test_order_intent_view_summary_after_add_reflects_cart(db_session, monkeypatch):
    await _seed_menu(db_session)
    add_output = GeminiChatOutput(
        reply_text="Sure!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="add", item_name="masala chai", quantity=1),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(add_output))
    await ai_service.process_chat_message(db_session, "order-session-3", "add a masala chai")

    summary_output = GeminiChatOutput(
        reply_text="Sure!",
        intent="order",
        sentiment="happy",
        order_action=OrderAction(action="view_summary"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(summary_output))
    result = await ai_service.process_chat_message(db_session, "order-session-3", "what's in my order?")

    assert "Masala Chai" in result["reply_text"]
    assert "Total" in result["reply_text"]


def _order_output(reply_text="Got it!", intent="general_chat", **kwargs):
    return GeminiChatOutput(reply_text=reply_text, intent=intent, sentiment="happy", **kwargs)


async def test_checkout_flow_end_to_end_pickup_never_loses_state(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "order-session-4"

    add_output = GeminiChatOutput(
        reply_text="Sure!", intent="order", sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa", quantity=1),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(add_output))
    await ai_service.process_chat_message(db_session, session, "add a samosa")

    checkout_output = GeminiChatOutput(
        reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(checkout_output))
    r1 = await ai_service.process_chat_message(db_session, session, "checkout")
    assert "name" in r1["reply_text"].lower()

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))

    r2 = await ai_service.process_chat_message(db_session, session, "Anshu")
    assert "phone" in r2["reply_text"].lower() or "contact" in r2["reply_text"].lower()

    r3 = await ai_service.process_chat_message(db_session, session, "9876543210")
    assert "email" in r3["reply_text"].lower()

    r3b = await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    assert r3b["quick_reply_options"] == ["Pickup", "Delivery"]

    r4a = await ai_service.process_chat_message(db_session, session, "Pickup")
    assert "location" in r4a["reply_text"].lower()
    assert r4a["quick_reply_options"] == quick_reply_service.LOCATION_OPTIONS

    r4 = await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    assert r4["order_summary"] is not None
    assert r4["order_summary"]["items"]
    assert r4["payment_request"] == {
        "amount": r4["order_summary"]["total"], "label": "Order Total", "purpose": "order",
    }

    r5 = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)
    assert "Order confirmed!" in r5["reply_text"]
    assert "pickup" in r5["reply_text"].lower()
    assert r5["payment_request"] is None

    order = await order_service.get_active_draft_order(db_session, session)
    assert order is None
    assert await checkout_draft_service.get_draft(db_session, session) is None


async def test_checkout_flow_delivery_asks_for_address(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "order-session-delivery"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")

    result = await ai_service.process_chat_message(db_session, session, "Delivery")

    assert "address" in result["reply_text"].lower()
    assert result["order_summary"] is None


async def _start_delivery_checkout(db_session, monkeypatch, session):
    await _seed_menu(db_session)
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    return await ai_service.process_chat_message(db_session, session, "Delivery")


async def test_checkout_delivery_address_within_range_asks_flat_number_then_confirms_then_pays(db_session, monkeypatch):
    session = "order-session-delivery-ok"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    bandra = ai_service.CAFE_LOCATIONS[0]
    address_result = await ai_service.process_chat_message(
        db_session,
        session,
        "14th Road, Bandra West, Mumbai, Maharashtra, India",
        address_coords=(bandra["latitude"], bandra["longitude"]),
    )
    assert "flat" in address_result["reply_text"].lower() or "house" in address_result["reply_text"].lower()
    assert address_result["order_summary"] is None
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.location == bandra["name"]
    assert draft.address == "14th Road, Bandra West, Mumbai, Maharashtra, India"
    assert draft.address_lat == bandra["latitude"]

    flat_result = await ai_service.process_chat_message(db_session, session, "A-302, Sunrise Apartments")
    assert "correct" in flat_result["reply_text"].lower()
    assert "A-302, Sunrise Apartments" in flat_result["reply_text"]
    assert flat_result["quick_reply_options"] == ["Yes, confirm", "No, cancel"]

    confirm_result = await ai_service.process_chat_message(db_session, session, "Yes, confirm")
    assert confirm_result["order_summary"] is not None
    assert confirm_result["payment_request"] is not None
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address_confirmed is True

    paid_result = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)
    assert "Order confirmed!" in paid_result["reply_text"]

    profile = await customer_profile_service.get_profile(db_session, "9876543210")
    assert profile.last_delivery_address == "14th Road, Bandra West, Mumbai, Maharashtra, India"
    assert profile.last_delivery_lat == bandra["latitude"]

    from sqlalchemy import select

    from app.models.order import Order

    order = (await db_session.execute(select(Order).where(Order.session_id == session))).scalars().first()
    assert order.delivery_address == "A-302, Sunrise Apartments, 14th Road, Bandra West, Mumbai, Maharashtra, India"
    assert order.delivery_flat_number == "A-302, Sunrise Apartments"


async def test_checkout_delivery_address_out_of_range_asks_for_a_different_address(db_session, monkeypatch):
    # Regression: out-of-range delivery used to reset fulfillment and offer
    # pickup as an alternative - it must instead stay on the delivery/address
    # step and just ask for a closer address, with no pickup quick replies.
    session = "order-session-delivery-far"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    # Far from every branch (middle of the Arabian Sea) - a real coordinate
    # pair, no geocoding call involved (distance is pure math on the
    # autocomplete suggestion's own lat/lon).
    result = await ai_service.process_chat_message(
        db_session, session, "somewhere in the middle of the sea", address_coords=(15.0, 68.0)
    )

    assert "don't deliver that far" in result["reply_text"].lower()
    assert "+91 98200 12345" in result["reply_text"]
    assert "pickup" not in result["reply_text"].lower()
    assert result["quick_reply_options"] is None
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address is None
    assert draft.fulfillment == "delivery"
    assert draft.last_prompted_step == "address"


async def test_checkout_delivery_free_text_address_without_selecting_suggestion_is_rejected(db_session, monkeypatch):
    # CRITICAL: an address can only be set by picking a dropdown suggestion
    # (address_coords) - typing free text and hitting send must never be
    # accepted as a valid address, no matter how well-formed it looks.
    session = "order-session-delivery-freetext"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    result = await ai_service.process_chat_message(db_session, session, "asdkj not a real address")

    assert "suggestion" in result["reply_text"].lower() or "refin" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address is None
    assert draft.fulfillment == "delivery"
    assert draft.last_prompted_step == "address"


async def test_checkout_delivery_offers_saved_address_for_returning_customer(db_session, monkeypatch):
    await customer_profile_service.remember_delivery_address(
        db_session, "9876543210", "22 Carter Road, Bandra West, Mumbai", 19.05, 72.82
    )

    session = "order-session-reuse-address"
    result = await _start_delivery_checkout(db_session, monkeypatch, session)

    assert "22 Carter Road" in result["reply_text"]
    assert result["quick_reply_options"] == ["Use this address", "Search a new address"]
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address is None
    assert draft.last_prompted_step == "address_reuse"


async def test_checkout_delivery_accepting_saved_address_skips_reverification(db_session, monkeypatch):
    await customer_profile_service.remember_delivery_address(
        db_session, "9876543210", "22 Carter Road, Bandra West, Mumbai", 19.05, 72.82
    )
    session = "order-session-reuse-accept"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    called = False

    async def fail_if_called(address):
        nonlocal called
        called = True
        return {"status": "not_found"}

    monkeypatch.setattr(ai_service.geocoding_service, "resolve_delivery_location", fail_if_called)

    result = await ai_service.process_chat_message(db_session, session, "Use this address")

    assert called is False
    assert "flat" in result["reply_text"].lower() or "house" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address == "22 Carter Road, Bandra West, Mumbai"
    assert draft.address_source == "reuse"
    assert draft.address_lat == 19.05


async def test_checkout_delivery_declining_saved_address_asks_for_a_new_one(db_session, monkeypatch):
    await customer_profile_service.remember_delivery_address(
        db_session, "9876543210", "22 Carter Road, Bandra West, Mumbai", 19.05, 72.82
    )
    session = "order-session-reuse-decline"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    result = await ai_service.process_chat_message(db_session, session, "No, a different place")

    assert "address" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address is None
    assert draft.address_reuse_declined is True


async def test_checkout_delivery_autocomplete_coords_skip_geocoding_api_call(db_session, monkeypatch):
    session = "order-session-autocomplete"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    called = False

    async def fail_if_called(address):
        nonlocal called
        called = True
        return {"status": "not_found"}

    monkeypatch.setattr(ai_service.geocoding_service, "resolve_delivery_location", fail_if_called)

    bandra = ai_service.CAFE_LOCATIONS[0]
    result = await ai_service.process_chat_message(
        db_session,
        session,
        "14th Road, Bandra West, Mumbai, Maharashtra, India",
        address_coords=(bandra["latitude"], bandra["longitude"]),
    )

    assert called is False
    assert "flat" in result["reply_text"].lower() or "house" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address_source == "autocomplete"
    assert draft.address_lat == bandra["latitude"]


async def test_checkout_delivery_address_confirm_negative_lets_customer_re_enter(db_session, monkeypatch):
    session = "order-session-confirm-no"
    await _start_delivery_checkout(db_session, monkeypatch, session)

    bandra = ai_service.CAFE_LOCATIONS[0]
    await ai_service.process_chat_message(
        db_session,
        session,
        "14th Road, Bandra West, Mumbai",
        address_coords=(bandra["latitude"], bandra["longitude"]),
    )
    await ai_service.process_chat_message(db_session, session, "skip")

    result = await ai_service.process_chat_message(db_session, session, "No, cancel")

    assert "address" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.address is None
    assert draft.flat_number is None
    assert draft.flat_number_skipped is False
    assert draft.address_confirmed is False


async def test_checkout_flow_reuses_name_and_phone_already_known_this_session(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "order-session-reuse"
    await session_context_service.remember_name(db_session, session, "Priya")
    await session_context_service.remember_phone(db_session, session, "9123456789")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    result = await ai_service.process_chat_message(db_session, session, "checkout")

    assert "email" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.name == "Priya"
    assert draft.phone == "9123456789"


async def test_checkout_flow_empty_cart_ends_flow_without_asking_anything(db_session, monkeypatch):
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    result = await ai_service.process_chat_message(db_session, "order-session-empty", "checkout")

    assert "empty" in result["reply_text"].lower()
    assert await checkout_draft_service.get_draft(db_session, "order-session-empty") is None


async def test_checkout_flow_asks_phone_instead_of_treating_trigger_message_as_phone(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "order-session-name-only"
    await session_context_service.remember_name(db_session, session, "Anshu")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    result = await ai_service.process_chat_message(db_session, session, "checkout")

    assert "invalid" not in result["reply_text"].lower()
    assert "valid phone number" not in result["reply_text"].lower()
    assert "phone" in result["reply_text"].lower() or "contact" in result["reply_text"].lower()
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.name == "Anshu"
    assert draft.phone is None


async def test_order_view_summary_after_checkout_shows_completed_order_not_empty_draft(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "order-session-post-checkout"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=2),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add 2 samosas")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(GeminiChatOutput(
        reply_text="Glad to hear it!", intent="general_chat", sentiment="happy",
    )))
    await ai_service.process_chat_message(db_session, session, "It was great, thanks!")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="view_summary"),
        )),
    )
    result = await ai_service.process_chat_message(db_session, session, "what did I order")

    assert "empty" not in result["reply_text"].lower()
    assert "samosa" in result["reply_text"].lower()
    assert result["order_summary"]["status"] == "confirmed"
    assert result["order_summary"]["total"] > 0


async def test_order_summary_question_is_answered_deterministically_even_if_gemini_misclassifies_intent(
    db_session, monkeypatch
):
    await _seed_menu(db_session)
    session = "order-summary-deterministic-session"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=2),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add 2 samosas")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543211")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(GeminiChatOutput(
        reply_text="Glad to hear it!", intent="general_chat", sentiment="happy",
    )))
    await ai_service.process_chat_message(db_session, session, "It was great, thanks!")

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(GeminiChatOutput(
        reply_text="Not sure what you mean.", intent="general_chat", sentiment="neutral",
    )))
    result = await ai_service.process_chat_message(db_session, session, "what did I order??")

    assert "samosa" in result["reply_text"].lower()
    assert result["order_summary"]["status"] == "confirmed"


async def test_name_recall_question_reports_known_name(db_session, monkeypatch):
    session = "name-recall-session-1"
    await session_context_service.remember_name(db_session, session, "Anshu")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Not sure.", intent="general_chat", sentiment="neutral")),
    )
    result = await ai_service.process_chat_message(db_session, session, "who am I?")

    assert "Anshu" in result["reply_text"]


async def test_name_recall_question_without_known_name_asks_for_it(db_session, monkeypatch):
    session = "name-recall-session-2"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Not sure.", intent="general_chat", sentiment="neutral")),
    )
    result = await ai_service.process_chat_message(db_session, session, "what's my name?")

    assert "don't have a name" in result["reply_text"].lower()


async def test_reservation_intent_gives_all_upfront_moves_straight_to_name_step(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Let me check that for you!",
        intent="reservation",
        sentiment="happy",
        reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=4),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    first = await ai_service.process_chat_message(db_session, "res-session-1", "book a table for 4 tomorrow at 7pm")
    assert "location" in first["reply_text"].lower()
    assert first["quick_reply_options"] == quick_reply_service.LOCATION_OPTIONS

    result = await ai_service.process_chat_message(db_session, "res-session-1", "Bandra West, Mumbai")

    assert "name" in result["reply_text"].lower()
    assert result["quick_reply_options"] is None
    assert result["date_picker_options"] is None


async def test_reservation_intent_unparseable_datetime_asks_for_clarification(db_session, monkeypatch):
    session = "res-session-2"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Sure!", intent="reservation", sentiment="happy")),
    )
    await ai_service.process_chat_message(db_session, session, "book a table sometime")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")

    output = GeminiChatOutput(
        reply_text="Let me check that for you!",
        intent="reservation",
        sentiment="happy",
        reservation_details=ReservationDetails(date_phrase="blah blah", time_phrase="whenever", guests=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, session, "sometime, whenever")

    assert "couldn't quite understand" in result["reply_text"]
    assert result["quick_reply_options"] is None


async def test_reservation_intent_asks_for_location_first_when_nothing_given(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Sure, happy to help!",
        intent="reservation",
        sentiment="happy",
        reservation_details=None,
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "res-session-date", "I'd like to book a table")

    assert "location" in result["reply_text"].lower()
    assert result["quick_reply_options"] == quick_reply_service.LOCATION_OPTIONS
    assert result["date_picker_options"] is None


async def test_reservation_intent_asks_for_date_after_location_when_nothing_else_given(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Sure, happy to help!",
        intent="reservation",
        sentiment="happy",
        reservation_details=None,
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "res-session-date", "I'd like to book a table")
    result = await ai_service.process_chat_message(db_session, "res-session-date", "Bandra West, Mumbai")

    assert "date" in result["reply_text"].lower()
    assert result["quick_reply_options"] is None
    assert len(result["date_picker_options"]) == 7
    assert all("date" in day and "label" in day and "available" in day for day in result["date_picker_options"])


async def test_reservation_intent_asks_for_time_when_only_date_given(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Sure! I can help you with that.",
        intent="reservation",
        sentiment="happy",
        reservation_details=ReservationDetails(date_phrase="tomorrow", guests=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "res-session-time", "book a table for 2 tomorrow")
    result = await ai_service.process_chat_message(db_session, "res-session-time", "Bandra West, Mumbai")

    assert "time" in result["reply_text"].lower()
    assert result["quick_reply_options"] == ["11:00 AM", "1:00 PM", "4:00 PM", "7:00 PM"]
    assert result["date_picker_options"] is None


async def test_reservation_intent_ignores_gemini_own_duplicate_time_question(db_session, monkeypatch):
    # During a structured flow, the reply is entirely code-generated (a canned
    # "Got it!" + the one scripted question) - Gemini's own reply_text is never
    # used, so it can't inject a duplicate/hallucinated question anymore.
    output = GeminiChatOutput(
        reply_text="Got it, Anshu! What time would you like to come in on that day?",
        intent="reservation",
        sentiment="happy",
        reservation_details=ReservationDetails(date_phrase="tomorrow", guests=2),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "res-session-dup", "tomorrow")
    result = await ai_service.process_chat_message(db_session, "res-session-dup", "Bandra West, Mumbai")

    assert result["reply_text"] == "Got it! What time would you like to book for?"
    assert result["reply_text"].count("?") == 1
    assert result["reply_text"].count("What time") == 1


async def test_reservation_intent_asks_for_guests_when_only_date_and_time_given(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Sure!",
        intent="reservation",
        sentiment="happy",
        reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "res-session-guests", "book a table tomorrow at 7pm")
    result = await ai_service.process_chat_message(db_session, "res-session-guests", "Bandra West, Mumbai")

    assert "guest" in result["reply_text"].lower()
    assert result["quick_reply_options"] is None


async def test_reservation_guest_count_step_validates_server_side(db_session, monkeypatch):
    session = "res-session-guest-validation"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="reservation", sentiment="happy",
            reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm"),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "book a table tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")

    # Reset to a bare reply_text with no reservation_details so each answer below
    # is parsed purely from user_message by the "guests" step itself, not the AI.
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Sure!", intent="reservation", sentiment="happy")),
    )

    non_numeric = await ai_service.process_chat_message(db_session, session, "a lot")
    assert non_numeric["reply_text"] == "Please enter a number of guests between 1 and 40."
    assert (await reservation_draft_service.get_draft(db_session, session)).guests is None

    zero = await ai_service.process_chat_message(db_session, session, "0")
    assert zero["reply_text"] == "Please enter a number of guests between 1 and 40."
    assert (await reservation_draft_service.get_draft(db_session, session)).guests is None

    negative = await ai_service.process_chat_message(db_session, session, "-5")
    assert negative["reply_text"] == "Please enter a number of guests between 1 and 40."
    assert (await reservation_draft_service.get_draft(db_session, session)).guests is None

    too_many = await ai_service.process_chat_message(db_session, session, "100")
    assert too_many["reply_text"] == (
        "We can accommodate up to 40 guests per booking. "
        "For larger groups, please call us directly at +91 98200 12345."
    )
    assert (await reservation_draft_service.get_draft(db_session, session)).guests is None

    valid = await ai_service.process_chat_message(db_session, session, "8")
    assert "name" in valid["reply_text"].lower()
    assert (await reservation_draft_service.get_draft(db_session, session)).guests == 8


async def test_reservation_guest_count_ignores_ai_hallucinated_number_for_vague_reply(db_session, monkeypatch):
    # Regression: real Gemini has been observed extracting reservation_details.
    # guests=8 for the literal reply "a lot" instead of leaving it null - a
    # plausible-looking but entirely invented number that a range check alone
    # can't catch (8 is a valid party size). Once guests is specifically the
    # step being answered, the AI's structured extraction must be ignored in
    # favor of parsing the customer's actual raw text.
    session = "res-session-guest-hallucination"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="reservation", sentiment="happy",
            reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm"),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "book a table tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Got it!", intent="reservation", sentiment="happy",
            reservation_details=ReservationDetails(guests=8),
        )),
    )
    result = await ai_service.process_chat_message(db_session, session, "a lot")

    assert result["reply_text"] == "Please enter a number of guests between 1 and 40."
    assert (await reservation_draft_service.get_draft(db_session, session)).guests is None


def _res_output(reply_text="Got it!", **kwargs):
    return GeminiChatOutput(reply_text=reply_text, intent="reservation", sentiment="happy", **kwargs)


async def test_reservation_full_flow_end_to_end_never_loses_state(db_session, monkeypatch):
    session = "res-session-full"

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output(reservation_details=None)))
    r0 = await ai_service.process_chat_message(db_session, session, "I'd like to book a table")
    assert "location" in r0["reply_text"].lower()
    assert r0["quick_reply_options"] == quick_reply_service.LOCATION_OPTIONS

    r1 = await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    assert "date" in r1["reply_text"].lower()
    assert len(r1["date_picker_options"]) == 7

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(_res_output(reservation_details=ReservationDetails(date_phrase="tomorrow"))),
    )
    r2 = await ai_service.process_chat_message(db_session, session, "tomorrow")
    assert "time" in r2["reply_text"].lower()
    assert r2["quick_reply_options"] == ["11:00 AM", "1:00 PM", "4:00 PM", "7:00 PM"]

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(_res_output(reservation_details=ReservationDetails(time_phrase="4pm"))),
    )
    r3 = await ai_service.process_chat_message(db_session, session, "4:00 PM")
    assert r3["date_picker_options"] is None
    assert "guest" in r3["reply_text"].lower()
    assert r3["reply_text"].lower().count("how many guests") == 1

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    r4 = await ai_service.process_chat_message(db_session, session, "2")
    assert "name" in r4["reply_text"].lower()
    assert r4["reply_text"].lower().count("name") == 1

    r5 = await ai_service.process_chat_message(db_session, session, "Anshu")
    assert "phone" in r5["reply_text"].lower() or "contact" in r5["reply_text"].lower()
    assert r5["quick_reply_options"] is None

    r6a = await ai_service.process_chat_message(db_session, session, "not a phone number")
    assert "valid phone number" in r6a["reply_text"]
    r6b = await ai_service.process_chat_message(db_session, session, "9876543210")
    assert "email" in r6b["reply_text"].lower()

    r6c = await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    assert "special request" in r6c["reply_text"].lower()

    r6d = await ai_service.process_chat_message(db_session, session, "no")
    assert "confirm" in r6d["reply_text"].lower()
    assert "Anshu" in r6d["reply_text"]
    assert "9876543210" in r6d["reply_text"]

    r7 = await ai_service.process_chat_message(db_session, session, "yes")
    assert "₹50" in r7["reply_text"]
    assert "demo" not in r7["reply_text"].lower()
    assert r7["payment_request"] == {"amount": 50.0, "label": "Booking Fee", "purpose": "reservation"}
    assert (await reservation_draft_service.get_draft(db_session, session)).next_step() == "payment"

    r8 = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)
    assert "Booked!" in r8["reply_text"]
    assert "Anshu" in r8["reply_text"]
    assert "9876543210" in r8["reply_text"]
    assert r8["quick_reply_options"] is None
    assert r8["date_picker_options"] is None
    assert r8["payment_request"] is None

    assert await reservation_draft_service.get_draft(db_session, session) is None


async def test_reservation_confirm_step_hallucinated_reply_text_gets_neutralized(db_session, monkeypatch):
    session = "res-session-hallucination"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Got it, Anshu! Your table is all set for August 2nd at 11:00 AM. We look forward to seeing you!",
            intent="reservation", sentiment="happy",
        )),
    )
    result = await ai_service.process_chat_message(db_session, session, "yes")

    assert "all set" not in result["reply_text"].lower()
    assert "look forward" not in result["reply_text"].lower()
    assert result["payment_request"] is not None
    assert (await reservation_draft_service.get_draft(db_session, session)).next_step() == "payment"


async def test_reservation_payment_step_reshows_card_without_booking_if_not_completion_signal(db_session, monkeypatch):
    session = "res-session-payment-noise"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "yes")

    result = await ai_service.process_chat_message(db_session, session, "wait, hold on")

    assert result["payment_request"] is not None
    assert "Booked!" not in result["reply_text"]
    draft = await reservation_draft_service.get_draft(db_session, session)
    assert draft is not None
    assert draft.next_step() == "payment"


async def test_reservation_flow_routes_free_text_replies_even_when_gemini_misclassifies_intent(db_session, monkeypatch):
    session = "res-session-misclassified"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Nice to meet you!", intent="general_chat", sentiment="happy", detected_name="Priya")),
    )
    result = await ai_service.process_chat_message(db_session, session, "Priya")

    assert "phone" in result["reply_text"].lower() or "contact" in result["reply_text"].lower()
    draft = await reservation_draft_service.get_draft(db_session, session)
    assert draft.name == "Priya"


async def test_reservation_confirm_step_negative_cancels_and_clears_draft(db_session, monkeypatch):
    session = "res-session-cancel"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")

    result = await ai_service.process_chat_message(db_session, session, "no, cancel that")

    assert "cancelled" in result["reply_text"].lower()
    assert await reservation_draft_service.get_draft(db_session, session) is None


async def test_reservation_confirm_step_ambiguous_reply_reshows_summary_without_booking(db_session, monkeypatch):
    session = "res-session-ambiguous"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")

    result = await ai_service.process_chat_message(db_session, session, "hmm what does that mean")

    assert "confirm" in result["reply_text"].lower()
    assert await reservation_draft_service.get_draft(db_session, session) is not None
    assert (await reservation_draft_service.get_draft(db_session, session)).next_step() == "confirm"


async def test_reservation_confirm_step_shows_tappable_yes_no_buttons(db_session, monkeypatch):
    session = "res-session-confirm-buttons"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    result = await ai_service.process_chat_message(db_session, session, "no")

    assert result["quick_reply_options"] == ["Yes, confirm", "No, cancel"]


async def test_reservation_confirm_step_broadened_affirmative_phrasing_advances(db_session, monkeypatch):
    session = "res-session-confirm-broad"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")

    result = await ai_service.process_chat_message(db_session, session, "theek hai, go for it")

    assert (await reservation_draft_service.get_draft(db_session, session)).next_step() == "payment"
    assert result["payment_request"] is not None


async def test_escalation_replaces_reply_with_honest_message_and_real_phone_number(db_session, monkeypatch):
    from app.core.config import CAFE_PHONE

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="I've flagged this for our manager immediately so a staff member can look into this.",
                intent="complaint", sentiment="angry",
            )
        ),
    )
    result = await ai_service.process_chat_message(db_session, "escalation-session", "this is unacceptable")

    assert CAFE_PHONE in result["reply_text"]
    assert "flagged" not in result["reply_text"].lower()
    assert "immediately" not in result["reply_text"].lower()
    assert "manager" not in result["reply_text"].lower()

    stmt = select(Escalation).where(Escalation.session_id == "escalation-session")
    escalation = (await db_session.execute(stmt)).scalars().first()
    assert escalation is not None


async def test_reservation_capacity_second_identical_booking_reduces_remaining_room(db_session, monkeypatch):
    monkeypatch.setattr(ai_service.rate_limiter, "is_within_limits", lambda: True)

    async def _book(session_id: str, guests: int):
        monkeypatch.setattr(
            ai_service, "_call_gemini",
            make_fake_call(
                GeminiChatOutput(
                    reply_text="Sure!", intent="reservation", sentiment="happy",
                    reservation_details=ReservationDetails(date_phrase="August 20 2099", time_phrase="7pm", guests=guests),
                )
            ),
        )
        await ai_service.process_chat_message(db_session, session_id, f"book a table for {guests} on August 20 2099 at 7pm")
        await ai_service.process_chat_message(db_session, session_id, "Bandra West, Mumbai")
        monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
        await ai_service.process_chat_message(db_session, session_id, "Guest")
        await ai_service.process_chat_message(db_session, session_id, "9876543210")
        await ai_service.process_chat_message(db_session, session_id, "anshu@example.com")
        await ai_service.process_chat_message(db_session, session_id, "no")
        await ai_service.process_chat_message(db_session, session_id, "yes")
        return await ai_service.process_chat_message(db_session, session_id, ai_service.PAYMENT_COMPLETE_MESSAGE)

    from app.core.config import MAX_CAPACITY_PER_SLOT

    first = await _book("res-capacity-1", MAX_CAPACITY_PER_SLOT - 5)
    assert "Booked!" in first["reply_text"]

    second_fits = await _book("res-capacity-2", 5)
    assert "Booked!" in second_fits["reply_text"]

    third_over = await _book("res-capacity-3", 1)
    assert "Booked!" not in third_over["reply_text"]
    assert "fully booked" in third_over["reply_text"].lower() or "not available" in third_over["reply_text"].lower() or "isn't available" in third_over["reply_text"].lower()


def test_is_location_question_matches_common_phrasings():
    assert ai_service._is_location_question("Where is the café located?")
    assert ai_service._is_location_question("what's your address")
    assert not ai_service._is_location_question("do you have wifi?")
    assert not ai_service._is_location_question("add 2 samosas")


def test_parse_phone_accepts_valid_indian_mobile_numbers():
    assert ai_service._parse_phone("9876543210") == "9876543210"
    assert ai_service._parse_phone("+91 9876543210") == "9876543210"
    assert ai_service._parse_phone("91-9876543210") == "9876543210"


def test_parse_phone_rejects_invalid_numbers():
    assert ai_service._parse_phone("12345") is None
    assert ai_service._parse_phone("Anshu") is None
    assert ai_service._parse_phone("1234567890") is None


def test_is_affirmative_matches_common_confirmations():
    for text in ["yes", "Yes!", "yeah", "sure", "confirm", "go ahead", "book it", "yes please book it"]:
        assert ai_service._is_affirmative(text), text
    assert not ai_service._is_affirmative("no")
    assert not ai_service._is_affirmative("what")


def test_is_negative_matches_common_cancellations():
    for text in ["no", "No.", "cancel", "no, cancel that", "nevermind"]:
        assert ai_service._is_negative(text), text
    assert not ai_service._is_negative("yes")
    assert not ai_service._is_negative("sure, go ahead")


async def test_faq_matches_are_injected_into_pre_call_context(db_session):
    context_with_faq = await ai_service._build_pre_call_context(db_session, "do you have wifi?", "session-faq")
    context_without_faq = await ai_service._build_pre_call_context(
        db_session, "asdkjaslkdj qwoieqwoie", "session-faq"
    )

    assert "wifi" in context_with_faq.lower()
    assert "wifi" not in context_without_faq.lower()


async def test_faq_matches_are_injected_for_hindi_devanagari_questions(db_session):
    context = await ai_service._build_pre_call_context(db_session, "क्या यहाँ पार्किंग है?", "session-faq-hi")
    assert "parking" in context.lower()


async def test_faq_intent_reply_is_not_post_call_grounded(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Yes, we have free WiFi - just ask a staff member for the password!",
        intent="faq",
        sentiment="happy",
        faq_match="wifi",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-1", "do you have wifi?")

    assert result["reply_text"] == output.reply_text


async def test_faq_location_question_returns_all_locations_as_cards(db_session, monkeypatch):
    from app.core.config import CAFE_LOCATIONS

    output = GeminiChatOutput(
        reply_text="We're somewhere downtown, I think!",
        intent="faq",
        sentiment="happy",
        faq_match="location",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-location", "Where is the café located?")

    assert "downtown" not in result["reply_text"]
    assert result["location_cards"] == CAFE_LOCATIONS
    assert len(result["location_cards"]) == 3


async def test_faq_location_question_respects_language(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="हमारा पता...",
        intent="faq",
        sentiment="happy",
        language="hi",
        faq_match="location",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-location-hi", "कैफे का पता क्या है?")

    assert result["reply_text"] == "हमारे पास आपके लिए तीन आरामदायक जगहें हैं!"
    assert result["location_cards"] is not None


async def test_faq_about_question_returns_brand_story_and_locations(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="We're just a regular café, nothing special.",
        intent="faq",
        sentiment="happy",
        faq_match="about",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-about", "Tell me about Rasa Café")

    assert "regular café, nothing special" not in result["reply_text"]
    assert "Rasa Café was born" in result["reply_text"]
    assert "workshops" in result["reply_text"]
    assert "Bandra West" in result["reply_text"]
    assert "Indiranagar" in result["reply_text"]
    assert "Koregaon Park" in result["reply_text"]
    assert result.get("location_cards") is None


async def test_non_location_faq_is_unaffected_by_location_override(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Yes, free WiFi is available!",
        intent="faq",
        sentiment="happy",
        faq_match="wifi",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-wifi", "do you have wifi?")

    assert result["reply_text"] == output.reply_text
    assert "98200" not in result["reply_text"]


async def test_angry_sentiment_logs_escalation(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="I'm so sorry - I've flagged this for our manager right away.",
        intent="complaint",
        sentiment="angry",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "escalate-session-1", "this is unacceptable!")

    result = await db_session.execute(select(Escalation).where(Escalation.session_id == "escalate-session-1"))
    row = result.scalars().first()
    assert row is not None
    assert row.message == "this is unacceptable!"
    assert row.sentiment == "angry"


async def test_happy_sentiment_does_not_log_escalation(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Glad to help!", intent="general_chat", sentiment="happy")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    await ai_service.process_chat_message(db_session, "escalate-session-2", "thanks so much!")

    result = await db_session.execute(select(Escalation).where(Escalation.session_id == "escalate-session-2"))
    assert result.scalars().first() is None


async def test_checkout_flow_sends_order_confirmation_and_birthday_email(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "order-session-email"

    fake_confirmation = AsyncMock(return_value=True)
    fake_birthday = AsyncMock(return_value=True)
    monkeypatch.setattr(ai_service.email_service, "send_order_confirmation", fake_confirmation)
    monkeypatch.setattr(ai_service.email_service, "send_birthday_wish", fake_birthday)

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "it's my birthday today!")
    await ai_service.process_chat_message(db_session, session, "Pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    await asyncio.sleep(0)

    fake_confirmation.assert_awaited_once()
    confirmation_args = fake_confirmation.await_args.args
    assert confirmation_args[0] == "anshu@example.com"
    assert confirmation_args[1] == "Anshu"
    fake_birthday.assert_awaited_once_with("anshu@example.com", "Anshu")


async def test_checkout_flow_email_cannot_be_skipped(db_session, monkeypatch):
    # Email is now a mandatory field - "skip"/"no"/etc. are not valid answers,
    # the flow must stay on the email step and re-ask rather than advance.
    await _seed_menu(db_session)
    session = "order-session-no-email"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")

    skip_attempt = await ai_service.process_chat_message(db_session, session, "skip")
    assert "valid email" in skip_attempt["reply_text"].lower()
    assert "skip" not in skip_attempt["reply_text"].lower()
    assert (await checkout_draft_service.get_draft(db_session, session)).email is None

    no_attempt = await ai_service.process_chat_message(db_session, session, "no")
    assert "valid email" in no_attempt["reply_text"].lower()
    assert (await checkout_draft_service.get_draft(db_session, session)).email is None

    valid = await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    assert "pickup" in valid["reply_text"].lower() or "delivery" in valid["reply_text"].lower()
    assert (await checkout_draft_service.get_draft(db_session, session)).email == "anshu@example.com"


async def test_reservation_flow_sends_confirmation_and_birthday_email(db_session, monkeypatch):
    session = "res-session-email"

    fake_confirmation = AsyncMock(return_value=True)
    fake_birthday = AsyncMock(return_value=True)
    monkeypatch.setattr(ai_service.email_service, "send_reservation_confirmation", fake_confirmation)
    monkeypatch.setattr(ai_service.email_service, "send_birthday_wish", fake_birthday)

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="Sure!", intent="reservation", sentiment="happy",
                reservation_details=ReservationDetails(date_phrase="tomorrow", time_phrase="7pm", guests=2),
            )
        ),
    )
    await ai_service.process_chat_message(db_session, session, "book a table for 2 tomorrow at 7pm")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_res_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876543210")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "it's my birthday today!")
    await ai_service.process_chat_message(db_session, session, "yes")
    await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)
    await asyncio.sleep(0)

    fake_confirmation.assert_awaited_once()
    fake_birthday.assert_awaited_once_with("anshu@example.com", "Anshu")


async def test_add_item_first_add_suggests_missing_dessert(db_session, monkeypatch):
    await _seed_menu(db_session)
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    result = await ai_service.process_chat_message(db_session, "upsell-session-1", "add a samosa")

    assert "Butter Croissant" in result["reply_text"]
    assert "☕" not in result["reply_text"]


async def test_add_item_only_suggests_upsell_once_per_order(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "upsell-session-2"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    first = await ai_service.process_chat_message(db_session, session, "add a samosa")
    assert "Butter Croissant" in first["reply_text"]

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="masala chai", quantity=1),
        )),
    )
    second = await ai_service.process_chat_message(db_session, session, "add a chai too")

    assert "Butter Croissant" not in second["reply_text"]
    assert "☕" not in second["reply_text"]


async def test_addon_suggestion_auto_adds_only_on_clear_affirmative_reply(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "upsell-affirmative-session"
    fake_call = make_fake_call(GeminiChatOutput(
        reply_text="Sure!", intent="order", sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa", quantity=1),
    ))
    monkeypatch.setattr(ai_service, "_call_gemini", fake_call)

    first = await ai_service.process_chat_message(db_session, session, "add a samosa")
    assert "Butter Croissant" in first["reply_text"]

    # A plain "yes" confirms the just-suggested add-on directly - no second
    # Gemini call needed, and the reply/cart total reflect the addon item.
    second = await ai_service.process_chat_message(db_session, session, "yes")
    fake_call.assert_awaited_once()
    assert "Butter Croissant" in second["reply_text"]
    assert second["order_summary"] is not None
    item_names = {item["name"] for item in second["order_summary"]["items"]}
    assert "Butter Croissant" in item_names


async def test_addon_suggestion_offers_quick_reply_buttons_and_button_tap_confirms(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "upsell-quickreply-session"
    fake_call = make_fake_call(GeminiChatOutput(
        reply_text="Sure!", intent="order", sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa", quantity=1),
    ))
    monkeypatch.setattr(ai_service, "_call_gemini", fake_call)

    first = await ai_service.process_chat_message(db_session, session, "add a samosa")
    assert first["quick_reply_options"] == ["Add Butter Croissant", "No thanks"]

    # Tapping the button sends its exact label text as the chat message
    # (see frontend QuickReplyOptions.jsx) - this must confirm the add-on
    # directly, same as typing "yes", without a second Gemini call.
    second = await ai_service.process_chat_message(db_session, session, "Add Butter Croissant")
    fake_call.assert_awaited_once()
    assert second["order_summary"] is not None
    item_names = {item["name"] for item in second["order_summary"]["items"]}
    assert "Butter Croissant" in item_names


async def test_addon_suggestion_hedge_word_reply_never_reaches_gemini_or_cart(db_session, monkeypatch, caplog):
    await _seed_menu(db_session)
    session = "upsell-hedge-session"
    fake_call = make_fake_call(GeminiChatOutput(
        reply_text="Sure!", intent="order", sentiment="happy",
        order_action=OrderAction(action="add", item_name="samosa", quantity=1),
    ))
    monkeypatch.setattr(ai_service, "_call_gemini", fake_call)
    first = await ai_service.process_chat_message(db_session, session, "add a samosa")
    assert "Butter Croissant" in first["reply_text"]

    # Regression: "maybe" was previously falling through to Gemini after the
    # pending flag cleared, and Gemini - biased by its own "Want to add
    # Butter Croissant?" turn still sitting in chat history - would emit a
    # genuine order_action=add for the item, actually adding it to the cart
    # (not just replying with the wrong text). A hedge word must never reach
    # Gemini at all for this turn, so the mock call count must stay at 1.
    with caplog.at_level("INFO"):
        second = await ai_service.process_chat_message(db_session, session, "maybe")

    fake_call.assert_awaited_once()
    assert "addon.ambiguous_filler_not_auto_added" in caplog.text
    assert second["reply_text"] != "Sure!"
    assert "Butter Croissant" in second["reply_text"]

    draft_order = await order_service.get_active_draft_order(db_session, session)
    summary = await order_service.get_order_summary(db_session, draft_order.id)
    item_names = {item["name"] for item in summary["items"]}
    assert "Butter Croissant" not in item_names


async def test_addon_suggestion_ambiguous_reply_does_not_auto_add(db_session, monkeypatch, caplog):
    await _seed_menu(db_session)
    session = "upsell-ambiguous-session"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    first = await ai_service.process_chat_message(db_session, session, "add a samosa")
    assert "Butter Croissant" in first["reply_text"]

    # A reply that just happens to mention the suggested item's name (but
    # isn't a clear "yes") must NOT be auto-added - this is the exact false
    # positive the old loose keyword match produced.
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Butter Croissant is a great choice for breakfast!",
            intent="general_chat", sentiment="neutral",
        )),
    )
    with caplog.at_level("INFO"):
        second = await ai_service.process_chat_message(
            db_session, session, "does the butter croissant have nuts in it?"
        )

    assert "addon.reply_not_auto_added" in caplog.text
    draft_order = await order_service.get_active_draft_order(db_session, session)
    summary = await order_service.get_order_summary(db_session, draft_order.id)
    item_names = {item["name"] for item in summary["items"]}
    assert "Butter Croissant" not in item_names
    assert second["reply_text"] == "Butter Croissant is a great choice for breakfast!"


async def test_checkout_flow_awards_loyalty_points_and_shows_card(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "loyalty-session-1"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="masala chai", quantity=2),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add two chai")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876500001")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    result = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    assert "loyalty points" in result["reply_text"].lower()
    assert result["loyalty_card"] is not None
    assert result["loyalty_card"]["current_points"] > 0


async def test_checkout_crossing_reward_tier_triggers_milestone_celebration(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "loyalty-milestone-session-1"
    await loyalty_service.award_points(db_session, "9876500003", 9500.0)

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="cold brew", quantity=4),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add 4 cold brews")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876500003")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    result = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    assert "unlocked" in result["reply_text"].lower()
    assert result["loyalty_card"]["milestone"] is not None
    assert result["loyalty_card"]["milestone"]["reward"] == "Free Samosa"
    assert result["loyalty_card"]["milestone"]["tier_points"] == 100


async def test_loyalty_question_reports_points_when_phone_known(db_session, monkeypatch):
    session = "loyalty-session-2"
    await session_context_service.remember_phone(db_session, session, "9876500002")
    await loyalty_service.award_points(db_session, "9876500002", 1000.0)

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Sure!", intent="general_chat", sentiment="happy")),
    )
    result = await ai_service.process_chat_message(db_session, session, "what are my points?")

    assert "10" in result["reply_text"]
    assert result["loyalty_card"]["current_points"] == 10


async def test_feedback_request_feature_is_disabled(db_session, monkeypatch):
    # Feedback-request is intentionally disabled (was producing broken/errored
    # turns) - order confirmation must not mention it, and it must never mark
    # itself pending, so no later message gets silently swallowed as feedback.
    await _seed_menu(db_session)
    session = "feedback-session-1"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876500003")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    confirm_result = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    assert "feedback" not in confirm_result["reply_text"].lower()
    assert await feedback_service.is_pending(db_session, session) is False

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Glad!", intent="general_chat", sentiment="happy")),
    )
    next_result = await ai_service.process_chat_message(db_session, session, "Everything was great, thanks!")

    assert "thank you for your feedback" not in next_result["reply_text"].lower()
    stmt = select(Feedback).where(Feedback.session_id == session)
    assert (await db_session.execute(stmt)).scalars().first() is None


async def test_order_history_question_answered_even_mid_checkout(db_session, monkeypatch):
    # An informational lookup like "what did I order?" must always be answered
    # directly - never hijacked by an in-progress checkout flow into re-asking
    # its own next scripted question instead.
    await _seed_menu(db_session)
    session = "feedback-vs-order-history"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    # Mid-flow, waiting on the phone number - not a completed order yet.
    await ai_service.process_chat_message(db_session, session, "Anshu")

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(reply_text="Sure!", intent="order", sentiment="neutral")),
    )
    result = await ai_service.process_chat_message(db_session, session, "What did I order?")

    assert "samosa" in result["reply_text"].lower()
    assert result["order_summary"] is not None
    assert "phone" not in result["reply_text"].lower()
    assert "contact number" not in result["reply_text"].lower()

    # The checkout draft is untouched by the detour - phone is still pending.
    draft = await checkout_draft_service.get_draft(db_session, session)
    assert draft.phone is None


async def test_checkout_shows_coupon_discount_before_payment_not_only_after(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "coupon-before-payment"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="cold brew", quantity=4),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add 4 cold brews")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876500005")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    payment_prompt = await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")

    # Discount must already be visible on the bill shown before the customer pays.
    assert payment_prompt["order_summary"]["discount"] > 0
    assert payment_prompt["order_summary"]["coupon_code"] is not None
    assert "save" in payment_prompt["reply_text"].lower()

    result = await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)
    assert "Order confirmed!" in result["reply_text"]


async def test_ambiguous_item_name_asks_for_clarification_instead_of_guessing(db_session, monkeypatch):
    db_session.add_all(
        [
            MenuItem(name="Cutting Chai", price=50, category="Hot Beverages", is_veg=True, spice_level=0, tags=["chai"]),
            MenuItem(name="Ginger Chai", price=60, category="Hot Beverages", is_veg=True, spice_level=0, tags=["chai"]),
            MenuItem(name="Masala Chai", price=80, category="Hot Beverages", is_veg=True, spice_level=0, tags=["chai"]),
            MenuItem(name="Kesar Chai", price=90, category="Hot Beverages", is_veg=True, spice_level=0, tags=["chai"]),
        ]
    )
    await db_session.commit()

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="chai", quantity=1),
        )),
    )
    result = await ai_service.process_chat_message(db_session, "ambiguous-chai-session", "add a chai")

    assert "which one" in result["reply_text"].lower()
    assert "Cutting Chai" in result["reply_text"]
    assert "Ginger Chai" in result["reply_text"]
    assert "Masala Chai" in result["reply_text"]
    assert "Kesar Chai" in result["reply_text"]

    summary = await order_service.get_order_summary(
        db_session, (await order_service.get_active_draft_order(db_session, "ambiguous-chai-session")).id
    )
    assert summary["items"] == []


async def test_checkout_phone_step_re_asks_instead_of_validating_when_not_actually_prompted(db_session, monkeypatch):
    await _seed_menu(db_session)
    session = "phone-desync-session"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")

    # Simulate the phone question never actually reaching the customer (e.g. clobbered
    # by an escalation override elsewhere) - the draft is mid-flow but was never told
    # its "phone" prompt was delivered.
    draft = await checkout_draft_service.get_draft(db_session, session)
    draft.last_prompted_step = None

    result = await ai_service.process_chat_message(db_session, session, "actually can I get extra chutney")

    assert "valid phone number" not in result["reply_text"].lower()
    assert "phone" in result["reply_text"].lower() or "contact" in result["reply_text"].lower()
    assert (await checkout_draft_service.get_draft(db_session, session)).phone is None


async def test_angry_message_after_order_still_escalates_without_feedback_capture(db_session, monkeypatch):
    # Escalation is independent of the (disabled) feedback feature - an angry
    # complaint right after an order still escalates normally, but since
    # feedback-request is disabled, it's never captured as a Feedback row.
    await _seed_menu(db_session)
    session = "feedback-session-2"

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    await ai_service.process_chat_message(db_session, session, "9876500004")
    await ai_service.process_chat_message(db_session, session, "anshu@example.com")
    await ai_service.process_chat_message(db_session, session, "no")
    await ai_service.process_chat_message(db_session, session, "pickup")
    await ai_service.process_chat_message(db_session, session, "Bandra West, Mumbai")
    await ai_service.process_chat_message(db_session, session, ai_service.PAYMENT_COMPLETE_MESSAGE)

    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="I'm upset", intent="complaint", sentiment="angry",
        )),
    )

    result = await ai_service.process_chat_message(db_session, session, "This was terrible, my order was cold!")

    assert CAFE_PHONE in result["reply_text"]
    escalation_row = (
        await db_session.execute(select(Escalation).where(Escalation.session_id == session))
    ).scalars().first()
    assert escalation_row is not None

    feedback_row = (
        await db_session.execute(select(Feedback).where(Feedback.session_id == session))
    ).scalars().first()
    assert feedback_row is None


async def test_welcome_back_message_never_fires_during_active_checkout(db_session, monkeypatch):
    # The returning-customer greeting was getting stapled onto the checkout
    # flow mid-transaction - it must never appear there, even for a phone
    # number with a clear favorite item on record. Entering the phone number
    # should produce ONLY the next step's question.
    await _seed_menu(db_session)
    phone = "9876500005"

    menu_row = await db_session.execute(select(MenuItem).where(MenuItem.name == "Masala Chai"))
    masala_chai = menu_row.scalars().first()

    order = await order_service.get_or_create_draft_order(db_session, "welcome-session-setup")
    await order_service.add_item(db_session, order.id, masala_chai.id, 2)
    await order_service.checkout(db_session, order.id, guest_phone=phone)

    session = "welcome-session-new"
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy",
            order_action=OrderAction(action="add", item_name="samosa", quantity=1),
        )),
    )
    await ai_service.process_chat_message(db_session, session, "add a samosa")
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(GeminiChatOutput(
            reply_text="Sure!", intent="order", sentiment="happy", order_action=OrderAction(action="checkout")
        )),
    )
    await ai_service.process_chat_message(db_session, session, "checkout")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(_order_output()))
    await ai_service.process_chat_message(db_session, session, "Anshu")
    result = await ai_service.process_chat_message(db_session, session, phone)

    assert "Welcome back" not in result["reply_text"]
    assert "Masala Chai" not in result["reply_text"]
    assert "email" in result["reply_text"].lower()


async def test_gemini_call_is_never_actually_invoked_when_test_mode_is_on(db_session):
    """settings.test_mode is forced True for every test (see conftest.py's
    _enforce_test_mode) - this is the belt-and-suspenders check that the
    flag itself works, WITHOUT monkeypatching _call_gemini at all, so a
    future test that forgets to mock the Gemini call still can't reach the
    real API."""
    result = await ai_service.process_chat_message(db_session, "test-mode-session", "hello")

    assert "[TEST_MODE]" in result["reply_text"]
    assert result["intent"] == "general_chat"


async def test_vision_call_is_never_actually_invoked_when_test_mode_is_on(db_session):
    from app.services import vision_service

    result = await vision_service.analyze_menu_image(db_session, "test-mode-vision-session", b"fake", "image/jpeg", None)

    # The mocked response (see vision_service._call_vision's test_mode guard)
    # is image_type="other", which analyze_menu_image maps to its own fixed
    # out-of-scope reply rather than echoing the mock's description text -
    # this still proves the real network call never happened (a real vision
    # call would classify a 4-byte fake image very differently, or error).
    assert result["reply_text"] == vision_service.OUT_OF_SCOPE_REPLY
