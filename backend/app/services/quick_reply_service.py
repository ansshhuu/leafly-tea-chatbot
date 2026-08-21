import re

QUICK_ACTION_OPTIONS = ["Explore Tea Collections", "Wellness Benefits", "Ask About a Tea", "Gift Hampers"]

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
