from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import CONTACT_EMAIL
from app.models.escalation import Escalation
from app.models.product import Product
from app.prompts.system_prompt import build_system_prompt
from app.schemas.chat import Filters, GeminiChatOutput
from app.services import ai_service, cache_service, quick_reply_service, session_context_service
from app.services.rate_limiter import rate_limiter


def make_fake_call(output: GeminiChatOutput, tokens: int = 123):
    return AsyncMock(return_value=(output, tokens))


async def _seed_products(db_session):
    db_session.add_all(
        [
            Product(name="Himalayan Green Tea", price=699, origin="Darjeeling", tea_type="green", caffeine_level="medium", tags=["green", "everyday"]),
            Product(name="Silver Tips White Tea", price=899, origin="Darjeeling", tea_type="white", caffeine_level="low", tags=["white", "low caffeine"]),
            Product(name="Assam Golden Black", price=649, origin="Assam", tea_type="black", caffeine_level="high", tags=["black", "everyday"]),
            Product(name="Reserve Oolong", price=1299, origin="Darjeeling", tea_type="oolong", caffeine_level="medium", badge="premium", tags=["oolong"], available=True),
            Product(name="Old Special", price=50, origin="Assam", tea_type="black", caffeine_level="high", tags=[], available=False),
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
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, here's what we've got!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(max_price=900),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-2", "anything under 900?")

    assert "Sure, here's what we've got!" in result["reply_text"]
    names = {item["name"] for item in result["suggested_items"]}
    assert {"Himalayan Green Tea", "Silver Tips White Tea", "Assam Golden Black"} <= names
    assert "Reserve Oolong" not in names
    assert "Old Special" not in names


async def test_menu_search_reply_never_bakes_items_into_reply_text(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Sure, here's what we've got!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(max_price=700),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-2b", "cheap teas please")

    assert result["reply_text"] == "Sure, here's what we've got!"
    assert "\n-" not in result["reply_text"]
    assert "tags:" not in result["reply_text"]
    assert "Rs." not in result["reply_text"]
    assert result["suggested_items"]
    assert result["suggested_items"][0]["name"] == "Assam Golden Black"
    assert result["suggested_items"][0]["price"] == 649.0


async def test_menu_search_with_no_matches_falls_back_to_closest_available_item(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Let me check that for you.",
        intent="menu_search",
        sentiment="neutral",
        filters=Filters(tea_type="white", max_price=10),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-3", "white tea under 10 rupees")

    assert "affordable" in result["reply_text"]
    assert result["suggested_items"][0]["name"] == "Silver Tips White Tea"


async def test_menu_search_no_matches_with_totally_empty_catalog_gives_honest_message(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Let me check that for you.",
        intent="menu_search",
        sentiment="neutral",
        filters=Filters(tea_type="white", max_price=10),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-3b", "white tea under 10 rupees")

    assert "couldn't find anything in the catalog matching that" in result["reply_text"]
    assert result.get("suggested_items") is None


async def test_menu_search_caffeine_filter_returns_only_matching_items(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Let me find something calming!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(caffeine_level="low"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-caffeine", "show me low caffeine tea")

    names = {item["name"] for item in result["suggested_items"]}
    assert names == {"Silver Tips White Tea"}
    assert "Assam Golden Black" not in names


async def test_menu_search_tea_type_filter_returns_only_matching_items(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Let me check what oolong we have!",
        intent="menu_search",
        sentiment="happy",
        filters=Filters(tea_type="oolong"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-oolong", "what oolong do you have?")

    names = {item["name"] for item in result["suggested_items"]}
    assert names == {"Reserve Oolong"}


async def test_recommendation_reply_applies_badge_hard_filter(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Here's a suggestion!",
        intent="recommendation",
        sentiment="happy",
        filters=Filters(badge="premium"),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-4", "recommend a premium tea")

    suggested_names = {item["name"] for item in result["suggested_items"]}
    assert suggested_names == {"Reserve Oolong"}


async def test_recommendation_budget_too_tight_for_combo_suggests_cheapest_single_item(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(
        reply_text="Let me see what fits!",
        intent="recommendation",
        sentiment="happy",
        filters=Filters(max_price=700),
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-combo", "recommend a combo under 700 rupees")

    assert len(result["suggested_items"]) == 1
    assert result["suggested_items"][0]["name"] == "Assam Golden Black"


async def test_menu_search_result_is_served_from_cache_on_repeat_query(db_session, monkeypatch):
    await _seed_products(db_session)
    output = GeminiChatOutput(reply_text="Sure!", intent="menu_search", sentiment="happy", filters=Filters(tea_type="green"))
    mock_call = make_fake_call(output)
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)

    await ai_service.process_chat_message(db_session, "session-5", "green tea please")
    await ai_service.process_chat_message(db_session, "session-5", "  Green Tea Please  ")

    assert mock_call.await_count == 1


async def test_menu_search_cache_hit_still_translates_item_names(db_session, monkeypatch):
    # Regression: a cache hit used to return the cached dict completely
    # as-is, bypassing translation - so an entry cached before the
    # translation step existed (or under a stale/differently-detected
    # language) would keep serving untranslated item names for its whole
    # TTL even after the underlying bug was fixed. Simulate exactly that:
    # seed a cache entry whose language says "hi" but whose menu_display
    # items were never translated.
    await _seed_products(db_session)
    stale_cached_result = {
        "reply_text": "यहाँ हमारी चाय है!",
        "intent": "menu_search",
        "sentiment": "happy",
        "language": "hi",
        "filters": None,
        "menu_display": [{"category": "Black Tea", "items": [{"name": "Assam Golden Black", "description": None, "price": 649.0}]}],
    }
    cache_service.set_cached("chai dikhao", stale_cached_result)

    result = await ai_service.process_chat_message(db_session, "session-stale-cache", "chai dikhao")

    assert result["menu_display"][0]["items"][0]["name"] == "असम गोल्डन ब्लैक"


async def test_general_chat_is_never_cached(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Hi!", intent="general_chat", sentiment="happy")
    mock_call = make_fake_call(output)
    monkeypatch.setattr(ai_service, "_call_gemini", mock_call)

    await ai_service.process_chat_message(db_session, "session-6", "hello there")
    await ai_service.process_chat_message(db_session, "session-6", "hello there")

    assert mock_call.await_count == 2


async def test_general_chat_capability_question_offers_quick_actions(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="I can help you browse the tea catalog and more!",
        intent="general_chat",
        sentiment="happy",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-capability", "what can you do?")

    assert result["quick_reply_options"] == list(quick_reply_service.QUICK_ACTION_OPTIONS)


async def test_general_chat_plain_smalltalk_has_no_quick_actions(db_session, monkeypatch):
    output = GeminiChatOutput(reply_text="Haha, glad to hear it!", intent="general_chat", sentiment="happy")
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "session-smalltalk", "thanks, you're great")

    assert result.get("quick_reply_options") is None


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


def test_build_system_prompt_includes_dynamic_context_when_present():
    prompt = build_system_prompt("Popular items right now:\n- Himalayan Green Tea (Rs.699, Darjeeling)")
    assert "Himalayan Green Tea" in prompt

    prompt_without_context = build_system_prompt("")
    assert "Popular items" not in prompt_without_context


def test_system_prompt_distinguishes_tea_type_from_free_text_tag():
    prompt = build_system_prompt("")
    assert "tea_type" in prompt
    assert "NOT {\"tag\": \"oolong\"}" in prompt


def test_system_prompt_requires_escalation_for_angry_or_urgent_sentiment():
    prompt = build_system_prompt("")
    assert "angry" in prompt and "urgent" in prompt
    assert "apology-and-contact-email" in prompt


def test_system_prompt_instructs_natural_reply_not_raw_data_dump():
    prompt = build_system_prompt("")
    assert "never" in prompt.lower()
    assert "(Rs.X, origin, tags)" in prompt


async def test_menu_display_language_matches_current_message_and_switches_back(db_session, monkeypatch):
    await _seed_products(db_session)

    en_output = GeminiChatOutput(
        reply_text="Here's our full range!", intent="menu_search", sentiment="happy", language="en", filters=None,
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(en_output))
    en_result = await ai_service.process_chat_message(db_session, "menu-lang-session", "what do you have?")
    en_names = {item["name"] for cat in en_result["menu_display"] for item in cat["items"]}
    assert "Assam Golden Black" in en_names
    assert "असम गोल्डन ब्लैक" not in en_names

    hi_output = GeminiChatOutput(
        reply_text="यह रहा हमारा पूरा कलेक्शन!", intent="menu_search", sentiment="happy", language="hi", filters=None,
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(hi_output))
    hi_result = await ai_service.process_chat_message(db_session, "menu-lang-session", "कलेक्शन दिखाओ")
    hi_names = {item["name"] for cat in hi_result["menu_display"] for item in cat["items"]}
    assert "असम गोल्डन ब्लैक" in hi_names
    assert "Assam Golden Black" not in hi_names

    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(en_output))
    en_again_result = await ai_service.process_chat_message(db_session, "menu-lang-session", "show me the catalog again")
    en_again_names = {item["name"] for cat in en_again_result["menu_display"] for item in cat["items"]}
    assert "Assam Golden Black" in en_again_names
    assert "असम गोल्डन ब्लैक" not in en_again_names


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


async def test_escalation_replaces_reply_with_honest_message_and_contact_email(db_session, monkeypatch):
    monkeypatch.setattr(
        ai_service, "_call_gemini",
        make_fake_call(
            GeminiChatOutput(
                reply_text="I've flagged this for our team immediately so someone can look into this.",
                intent="complaint", sentiment="angry",
            )
        ),
    )
    result = await ai_service.process_chat_message(db_session, "escalation-session", "this is unacceptable")

    assert CONTACT_EMAIL in result["reply_text"]
    assert "flagged" not in result["reply_text"].lower()
    assert "immediately" not in result["reply_text"].lower()

    stmt = select(Escalation).where(Escalation.session_id == "escalation-session")
    escalation = (await db_session.execute(stmt)).scalars().first()
    assert escalation is not None


async def test_faq_matches_are_injected_into_pre_call_context(db_session):
    context_with_faq = await ai_service._build_pre_call_context(db_session, "what sizes are available?", "session-faq")
    context_without_faq = await ai_service._build_pre_call_context(
        db_session, "asdkjaslkdj qwoieqwoie", "session-faq"
    )

    assert "100g" in context_with_faq
    assert "100g" not in context_without_faq


async def test_faq_intent_reply_is_not_post_call_grounded(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Most teas come in 100g and 250g sizes!",
        intent="faq",
        sentiment="happy",
        faq_match="sizes",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-1", "what sizes do you offer?")

    assert result["reply_text"] == output.reply_text


async def test_faq_about_question_returns_brand_story(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="We're just a regular tea shop, nothing special.",
        intent="faq",
        sentiment="happy",
        faq_match="about",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-about", "Tell me about Leafly")

    assert "regular tea shop, nothing special" not in result["reply_text"]
    assert "Leafly" in result["reply_text"]
    assert "Real Leaves" in result["reply_text"] or "whole, unbroken leaves" in result["reply_text"]
    assert CONTACT_EMAIL in result["reply_text"]


async def test_non_about_faq_is_unaffected_by_about_override(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="Yes, we offer four core collections!",
        intent="faq",
        sentiment="happy",
        faq_match="collections",
    )
    monkeypatch.setattr(ai_service, "_call_gemini", make_fake_call(output))

    result = await ai_service.process_chat_message(db_session, "faq-session-collections", "what collections do you have?")

    assert result["reply_text"] == output.reply_text


async def test_angry_sentiment_logs_escalation(db_session, monkeypatch):
    output = GeminiChatOutput(
        reply_text="I'm so sorry - I've flagged this for our team right away.",
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


async def test_gemini_call_is_never_actually_invoked_when_test_mode_is_on(db_session):
    """settings.test_mode is forced True for every test (see conftest.py's
    _enforce_test_mode) - this is the belt-and-suspenders check that the
    flag itself works, WITHOUT monkeypatching _call_gemini at all, so a
    future test that forgets to mock the Gemini call still can't reach the
    real API."""
    result = await ai_service.process_chat_message(db_session, "test-mode-session", "hello")

    assert "[TEST_MODE]" in result["reply_text"]
    assert result["intent"] == "general_chat"
