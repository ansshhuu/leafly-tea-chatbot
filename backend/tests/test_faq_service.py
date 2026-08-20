from app.services import faq_service


def test_find_matches_returns_relevant_entry_for_wifi_question():
    matches = faq_service.find_matches("Do you have wifi here?")
    assert any(item["category"] == "wifi" for item in matches)


def test_find_matches_returns_empty_for_unrelated_message():
    matches = faq_service.find_matches("asdkjaslkdj qwoieqwoie")
    assert matches == []


def test_find_matches_respects_top_n():
    matches = faq_service.find_matches("hours parking wifi pets birthday payment", top_n=2)
    assert len(matches) <= 2


def test_find_matches_uses_hint_keywords_too():
    matches = faq_service.find_matches("tell me about that", hint_keywords=["parking"])
    assert any(item["category"] == "parking" for item in matches)


def test_find_matches_works_for_hindi_devanagari_script():
    matches = faq_service.find_matches("क्या यहाँ पार्किंग है और वाई-फाई है?")
    categories = {item["category"] for item in matches}
    assert "parking" in categories
    assert "wifi" in categories


def test_find_matches_works_for_marathi_devanagari_script():
    matches = faq_service.find_matches("तुमच्याकडे वाढदिवस बुकिंग आहे का?")
    assert any(item["category"] == "birthday" for item in matches)


def test_format_faq_block_includes_question_and_answer():
    block = faq_service.format_faq_block(
        [{"question": "Is parking available?", "answer": "Yes, free parking.", "category": "parking"}]
    )
    assert "Is parking available?" in block
    assert "Yes, free parking." in block
    assert "never invent" in block.lower()


def test_format_faq_block_empty_list_returns_empty_string():
    assert faq_service.format_faq_block([]) == ""
