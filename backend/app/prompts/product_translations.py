"""Static name/description translations for tea products, keyed by the
English name stored in the DB (products.name, lowercased). Product names are
stored in English only (see app.models.product.Product), so this is the
translation layer that lets a product card match whichever language the
CURRENT customer message is in - see product_context.

A static table (vs. an on-the-fly Gemini translation call) was chosen
because the catalog is small and fixed enough that pre-written,
human-quality translations are more reliable than a per-request LLM call,
and add zero extra latency/cost to every non-English product view. A
product with no entry here just falls back to its English name/description
untranslated - a rare gap for a newly admin-added product is an acceptable,
non-breaking degradation."""

PRODUCT_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "himalayan green tea": {
        "hi": {"name": "हिमालयन ग्रीन टी", "description": "ताज़ी, जीवंत पत्तियों से बना हल्का और नाज़ुक स्वाद"},
    },
    "silver tips white tea": {
        "hi": {"name": "सिल्वर टिप्स व्हाइट टी", "description": "कोमल कलियों से बनी शुद्ध और हल्की सफ़ेद चाय"},
    },
    "darjeeling first flush": {
        "hi": {"name": "दार्जिलिंग फर्स्ट फ्लश", "description": "सीज़न की पहली तुड़ाई से बनी मस्कटेल खुशबू वाली काली चाय"},
    },
    "artisan oolong": {
        "hi": {"name": "आर्टिज़न ऊलोंग", "description": "हाथ से बनाई गई, जटिल और परिष्कृत स्वाद वाली ऊलोंग चाय"},
    },
    "assam golden black": {
        "hi": {"name": "असम गोल्डन ब्लैक", "description": "गहरी, माल्टी खुशबू वाली भरपूर असम काली चाय"},
    },
    "kashmir white reserve": {
        "hi": {"name": "कश्मीर व्हाइट रिज़र्व", "description": "कश्मीर की दुर्लभ बागानों से चुनी गई प्रीमियम सफ़ेद चाय"},
    },
    "mountain pu-erh": {
        "hi": {"name": "माउंटेन पु-एर्ह", "description": "गहरी, मिट्टी जैसी खुशबू वाली परिपक्व पु-एर्ह चाय"},
    },
    "reserve oolong": {
        "hi": {"name": "रिज़र्व ऊलोंग", "description": "छोटे बैच में तैयार की गई खास रिज़र्व ऊलोंग चाय"},
    },
}


def translated_name_and_description(name: str, description: str | None, lang: str) -> tuple[str, str | None]:
    """Returns (name, description) translated into lang if we have an entry
    and lang is "hi" (Devanagari) - "en" and "hinglish" both use the
    catalog's own English names as-is. Falls back to the original English
    name/description untranslated when there's no entry."""
    if lang != "hi":
        return name, description

    entry = PRODUCT_TRANSLATIONS.get(name.strip().lower(), {}).get(lang)
    if entry is None:
        return name, description
    return entry.get("name", name), entry.get("description", description)
