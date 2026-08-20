from app.services import quick_reply_service


def test_is_capability_question_matches_common_phrasings():
    for message in [
        "What can you do?",
        "what do you do",
        "How can you help me?",
        "who are you",
        "What is this?",
        "Help me please",
    ]:
        assert quick_reply_service.is_capability_question(message), message


def test_is_capability_question_ignores_plain_smalltalk():
    for message in ["thanks so much", "haha nice", "add 2 teas to my cart", "track my order"]:
        assert not quick_reply_service.is_capability_question(message), message


def test_is_greeting_matches_bare_openers():
    for message in ["hi", "Hi!", "hello", "hey there", "hii", "good morning", "Good evening!", "namaste"]:
        assert quick_reply_service.is_greeting(message), message


def test_is_greeting_ignores_longer_messages_that_merely_start_with_a_greeting():
    for message in [
        "hi, can I get some green tea",
        "hello can you tell me about your low caffeine options",
        "hey, is my order shipped yet",
    ]:
        assert not quick_reply_service.is_greeting(message), message


def test_is_greeting_ignores_plain_smalltalk():
    for message in ["thanks so much", "add 2 teas to my cart", "track my order", ""]:
        assert not quick_reply_service.is_greeting(message), message
