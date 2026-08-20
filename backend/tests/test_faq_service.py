from app.services import faq_service


def test_find_matches_returns_relevant_entry_for_sizes_question():
    matches = faq_service.find_matches("What sizes are available?")
    assert any(item["category"] == "sizes" for item in matches)


def test_find_matches_returns_empty_for_unrelated_message():
    matches = faq_service.find_matches("asdkjaslkdj qwoieqwoie")
    assert matches == []


def test_find_matches_respects_top_n():
    matches = faq_service.find_matches("contact gifting sizes caffeine shipping returns", top_n=2)
    assert len(matches) <= 2


def test_find_matches_uses_hint_keywords_too():
    matches = faq_service.find_matches("tell me about that", hint_keywords=["gifting"])
    assert any(item["category"] == "gifting" for item in matches)


def test_find_matches_works_for_hindi_devanagari_script():
    matches = faq_service.find_matches("क्या आप कॉर्पोरेट गिफ्टिंग करते हैं?")
    categories = {item["category"] for item in matches}
    assert "gifting" in categories


def test_find_matches_flags_shipping_as_a_todo_placeholder():
    matches = faq_service.find_matches("what is your shipping policy?")
    assert any(item["category"] == "shipping" and "TODO" in item["answer"] for item in matches)


def test_format_faq_block_includes_question_and_answer():
    block = faq_service.format_faq_block(
        [{"question": "What sizes are available?", "answer": "Most teas are available in 100g and 250g sizes.", "category": "sizes"}]
    )
    assert "What sizes are available?" in block
    assert "100g and 250g" in block
    assert "never invent" in block.lower()


def test_format_faq_block_empty_list_returns_empty_string():
    assert faq_service.format_faq_block([]) == ""
