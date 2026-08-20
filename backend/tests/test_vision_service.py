from unittest.mock import AsyncMock

from app.models.menu_item import MenuItem
from app.schemas.vision import ImageAnalysisOutput
from app.services import vision_service
from app.services.rate_limiter import rate_limiter


def make_fake_vision_call(output: ImageAnalysisOutput, tokens: int = 200):
    return AsyncMock(return_value=(output, tokens))


async def _seed_menu(db_session):
    db_session.add_all(
        [
            MenuItem(name="Chocolate Muffin", price=110, category="Bakery", tags=["bakery", "sweet", "chocolate"]),
            MenuItem(name="Cold Brew", price=160, category="Cold Beverages", tags=["coffee", "cold"]),
            MenuItem(name="Samosa", price=60, category="Snacks", tags=["snack", "fried", "spicy"]),
        ]
    )
    await db_session.commit()


async def test_analyze_menu_image_exact_name_match(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(
        image_type="menu_item",
        description="That looks like a rich chocolate baked treat!",
        identified_name="Chocolate Muffin",
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-1", b"fake-bytes", "image/jpeg", None)

    assert "rich chocolate baked treat" in result["reply_text"]
    assert result["intent"] == "menu_search"
    assert [item["name"] for item in result["suggested_items"]] == ["Chocolate Muffin"]


async def test_analyze_menu_image_near_exact_name_typo_still_matches(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(
        image_type="menu_item", description="Looks like a samosa.", identified_name="Samoza"
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-2", b"fake-bytes", "image/jpeg", None)

    assert [item["name"] for item in result["suggested_items"]] == ["Samosa"]


async def test_analyze_menu_image_off_menu_food_gives_honest_message_no_similar_item(db_session, monkeypatch):
    # Regression: a photo of food we don't serve (stir-fried noodles, Coke,
    # etc.) must never get "similar item" suggestions based on loose
    # category/tag overlap - only an exact/near-exact NAME match counts, so
    # anything else must fall to the honest "not on our menu" message.
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(
        image_type="menu_item",
        description="That looks like a delicious bowl of stir-fried noodles with vegetables.",
        identified_name="Vegetable Fried Noodles",
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-noodles", b"fake-bytes", "image/jpeg", None)

    assert "not on our menu" in result["reply_text"]
    assert "+91 98200 12345" in result["reply_text"]
    assert result["suggested_items"] is None


async def test_analyze_menu_image_coke_gives_honest_message(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(
        image_type="menu_item", description="That looks like a can of Coca-Cola.", identified_name="Coca-Cola"
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-coke", b"fake-bytes", "image/jpeg", None)

    assert "not on our menu" in result["reply_text"]
    assert result["suggested_items"] is None


async def test_analyze_menu_image_no_match_gives_honest_message(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(image_type="menu_item", description="That looks like a bowl of ramen.", identified_name="Ramen")
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-3", b"fake-bytes", "image/jpeg", None)

    assert "bowl of ramen" in result["reply_text"]
    assert "not on our menu" in result["reply_text"]
    assert "+91 98200 12345" in result["reply_text"]
    assert result["suggested_items"] is None


async def test_analyze_menu_image_missing_identified_name_gives_honest_message(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(image_type="menu_item", description="Hard to tell what this is.", identified_name=None)
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-noname", b"fake-bytes", "image/jpeg", None)

    assert "not on our menu" in result["reply_text"]
    assert result["suggested_items"] is None


async def test_analyze_menu_image_special_request_skips_matching(db_session, monkeypatch):
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(
        image_type="menu_item",
        description="That looks like a fancy layered rainbow cake.",
        identified_name="Rainbow Cake",
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(
        db_session, "vision-session-special", b"fake-bytes", "image/jpeg", "can you make this for me?"
    )

    assert "fancy layered rainbow cake" in result["reply_text"]
    assert "isn't on our regular menu" in result["reply_text"]
    assert "+91 98200 12345" in result["reply_text"]
    assert result["suggested_items"] is None


async def test_analyze_menu_image_plain_identification_question_still_matches_menu(db_session, monkeypatch):
    # "is this on your menu?" should NOT trigger the special-request path -
    # only explicit custom/special-order phrasing should.
    await _seed_menu(db_session)
    output = ImageAnalysisOutput(
        image_type="menu_item",
        description="That looks like a rich chocolate baked treat!",
        identified_name="Chocolate Muffin",
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(
        db_session, "vision-session-plain", b"fake-bytes", "image/jpeg", "is this on your menu?"
    )

    assert any(item["name"] == "Chocolate Muffin" for item in result["suggested_items"])


async def test_analyze_menu_image_bot_avatar_gets_fixed_reply(db_session, monkeypatch):
    output = ImageAnalysisOutput(image_type="bot_avatar", description="A cartoon robot illustration.", identified_name=None)
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-avatar", b"fake-bytes", "image/jpeg", None)

    assert result["reply_text"] == vision_service.BOT_AVATAR_REPLY
    assert "Rumi" in result["reply_text"]


async def test_analyze_menu_image_out_of_scope_gets_fixed_reply(db_session, monkeypatch):
    output = ImageAnalysisOutput(image_type="other", description="That's a picture of a dog!", identified_name=None)
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-other", b"fake-bytes", "image/jpeg", None)

    assert result["reply_text"] == vision_service.OUT_OF_SCOPE_REPLY
    assert "picture of a dog" not in result["reply_text"]
    assert result.get("suggested_items") is None


async def test_analyze_menu_image_receipt_uses_model_description(db_session, monkeypatch):
    output = ImageAnalysisOutput(
        image_type="receipt",
        description="I can see this is a receipt! What would you like to know about this order?",
        identified_name=None,
    )
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-receipt", b"fake-bytes", "image/jpeg", None)

    assert result["reply_text"] == output.description
    assert result["intent"] == "faq"


async def test_analyze_menu_image_defaults_caption_when_none_given(db_session, monkeypatch):
    output = ImageAnalysisOutput(image_type="menu_item", description="A cup of coffee.", identified_name="Filter Coffee")
    mock_call = make_fake_vision_call(output)
    monkeypatch.setattr(vision_service, "_call_vision", mock_call)

    await vision_service.analyze_menu_image(db_session, "vision-session-caption", b"fake-bytes", "image/jpeg", None)

    mock_call.assert_awaited_once_with(db_session, b"fake-bytes", "image/jpeg", vision_service.DEFAULT_CAPTION)

    from app.services.ai_service import _fetch_recent_history

    history = await _fetch_recent_history(db_session, "vision-session-caption")
    assert history[0].message == f"[image uploaded] {vision_service.DEFAULT_CAPTION}"


async def test_analyze_menu_image_saves_chat_history_with_caption(db_session, monkeypatch):
    output = ImageAnalysisOutput(image_type="menu_item", description="A cup of coffee.", identified_name="Filter Coffee")
    monkeypatch.setattr(vision_service, "_call_vision", make_fake_vision_call(output))

    await vision_service.analyze_menu_image(db_session, "vision-session-4", b"fake-bytes", "image/jpeg", "is this on your menu?")

    from app.services.ai_service import _fetch_recent_history

    history = await _fetch_recent_history(db_session, "vision-session-4")
    assert history[0].message == "[image uploaded] is this on your menu?"
    assert history[1].role == "assistant"


async def test_analyze_menu_image_respects_rate_limit(db_session, monkeypatch):
    output = ImageAnalysisOutput(image_type="menu_item", description="A cup of coffee.", identified_name="Filter Coffee")
    mock_call = make_fake_vision_call(output)
    monkeypatch.setattr(vision_service, "_call_vision", mock_call)
    monkeypatch.setattr(rate_limiter, "is_within_limits", lambda: False)

    result = await vision_service.analyze_menu_image(db_session, "vision-session-5", b"fake-bytes", "image/jpeg", None)

    assert result["reply_text"] == vision_service.FALLBACK_MESSAGE
    mock_call.assert_not_awaited()


async def test_analyze_menu_image_handles_gemini_error_gracefully(db_session, monkeypatch):
    monkeypatch.setattr(vision_service, "_call_vision", AsyncMock(side_effect=RuntimeError("boom")))

    result = await vision_service.analyze_menu_image(db_session, "vision-session-6", b"fake-bytes", "image/jpeg", None)

    assert result["reply_text"] == vision_service.FALLBACK_MESSAGE
