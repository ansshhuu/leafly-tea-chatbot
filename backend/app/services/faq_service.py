import json
import re
from functools import lru_cache
from pathlib import Path

FAQ_PATH = Path(__file__).resolve().parents[1] / "data" / "faq_knowledge.json"

_STOPWORDS = {
    "a", "an", "the", "is", "are", "do", "does", "you", "your", "i", "we",
    "have", "has", "can", "to", "of", "for", "in", "on", "and", "or", "it",
    "what", "how", "any", "at", "with", "there", "this", "that",
}


_CATEGORY_ALIASES: dict[str, list[str]] = {
    "hours": ["घंटे", "समय", "खुलने", "वेळ", "तास"],
    "parking": ["पार्किंग"],
    "wifi": ["वाई-फाई", "वाईफाई", "वाय-फाय"],
    "events": ["इवेंट", "कार्यक्रम"],
    "pets": ["पालतू", "कुत्ता", "पाळीव"],
    "birthday": ["जन्मदिन", "वाढदिवस"],
    "payment": ["भुगतान", "पेमेंट", "पैसे"],
    "delivery": ["डिलीवरी", "टेकअवे"],
    "group_bookings": ["ग्रुप", "समूह", "गट"],
    "allergens": ["एलर्जी"],
    "location": ["पता", "जगह", "ठिकाण"],
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _alias_categories(text: str) -> set[str]:
    return {category for category, aliases in _CATEGORY_ALIASES.items() if any(alias in text for alias in aliases)}


@lru_cache
def _load_faq() -> list[dict]:
    data = json.loads(FAQ_PATH.read_text(encoding="utf-8"))
    return data["items"]


def find_matches(user_message: str, hint_keywords: list[str] | None = None, top_n: int = 3) -> list[dict]:
    query_terms = _tokenize(user_message)
    if hint_keywords:
        query_terms |= _tokenize(" ".join(hint_keywords))

    alias_categories = _alias_categories(user_message)

    if not query_terms and not alias_categories:
        return []

    scored = []
    for item in _load_faq():
        haystack_terms = _tokenize(f"{item['question']} {item['category']} {item['answer']}")
        score = len(query_terms & haystack_terms)
        if item["category"] in alias_categories:
            score += 2
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:top_n]]


def format_faq_block(matches: list[dict]) -> str:
    if not matches:
        return ""

    lines = "\n".join(f"- Q: {item['question']}\n  A: {item['answer']}" for item in matches)
    return f"Relevant FAQ knowledge base entries (use ONLY this information, never invent policy details):\n{lines}"
