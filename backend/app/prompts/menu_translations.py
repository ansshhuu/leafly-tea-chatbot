"""Static name/description translations for menu items, keyed by the
English name stored in the DB (menu_items.name, lowercased). Item names are
stored in English only (see app.models.menu_item.MenuItem), so this is the
translation layer that lets the menu card match whichever language the
CURRENT customer message is in - see menu_translation_service.

A static table (vs. an on-the-fly Gemini translation call) was chosen
because the menu is small and fixed enough that pre-written, human-quality
translations are more reliable than a per-request LLM call, and add zero
extra latency/cost to every non-English menu view. An item with no entry
here just falls back to its English name/description untranslated (see
menu_translation_service.translate_item) - a rare gap for a newly
admin-added item is a acceptable, non-breaking degradation."""

MENU_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "masala chai": {
        "hi": {"name": "मसाला चाय", "description": "साबुत मसालों और ताज़े दूध के साथ बनी सुगंधित काली चाय"},
        "mr": {"name": "मसाला चहा", "description": "संपूर्ण मसाले आणि ताज्या दुधासह बनवलेला सुगंधी काळा चहा"},
    },
    "filter coffee": {
        "hi": {"name": "फिल्टर कॉफी", "description": "झागदार दूध के साथ पारंपरिक दक्षिण भारतीय डिकॉक्शन कॉफी"},
        "mr": {"name": "फिल्टर कॉफी", "description": "फेसाळ दुधासह पारंपरिक दक्षिण भारतीय डिकॉक्शन कॉफी"},
    },
    "cutting chai": {
        "hi": {"name": "कटिंग चाय", "description": "तेज़, अदरक-इलायची वाली टपरी स्टाइल हाफ चाय"},
        "mr": {"name": "कटिंग चहा", "description": "तीव्र, आले-वेलची घातलेला टपरी स्टाईल हाफ चहा"},
    },
    "ginger chai": {
        "hi": {"name": "अदरक चाय", "description": "ताज़ी कुटी अदरक से बनी तेज़ मसालेदार दूध वाली चाय"},
        "mr": {"name": "आले चहा", "description": "ताज्या ठेचलेल्या आल्यापासून बनवलेला तीव्र मसालेदार दुधाचा चहा"},
    },
    "kesar chai": {
        "hi": {"name": "केसर चाय", "description": "केसर से सुगंधित शाही इलायची चाय"},
        "mr": {"name": "केशर चहा", "description": "केशराने सुगंधित शाही वेलची चहा"},
    },
    "samosa": {
        "hi": {"name": "समोसा", "description": "मसालेदार आलू और मटर से भरी कुरकुरी सुनहरी पेस्ट्री"},
        "mr": {"name": "समोसा", "description": "मसालेदार बटाटा आणि वाटाण्यांनी भरलेली कुरकुरीत सोनेरी पेस्ट्री"},
    },
    "vada pav": {
        "hi": {"name": "वड़ा पाव", "description": "मुंबई का मशहूर मसालेदार आलू वड़ा, नरम पाव और चटनी के साथ"},
        "mr": {"name": "वडा पाव", "description": "मुंबईचा प्रसिद्ध मसालेदार बटाटा वडा, मऊ पाव आणि चटणीसह"},
    },
    "kachori": {
        "hi": {"name": "कचौरी", "description": "मसालेदार दाल भरी कुरकुरी तली हुई पेस्ट्री"},
        "mr": {"name": "कचोरी", "description": "मसालेदार डाळ भरलेली कुरकुरीत तळलेली पेस्ट्री"},
    },
    "bread pakora": {
        "hi": {"name": "ब्रेड पकोड़ा", "description": "बेसन के घोल में तला मसालेदार आलू भरा ब्रेड"},
        "mr": {"name": "ब्रेड पकोडा", "description": "बेसनाच्या पिठात तळलेला मसालेदार बटाटा भरलेला ब्रेड"},
    },
    "aloo tikki": {
        "hi": {"name": "आलू टिक्की", "description": "मीठी और पुदीना चटनी के साथ परोसी सुनहरी आलू पैटीज़"},
        "mr": {"name": "बटाटा टिक्की", "description": "गोड आणि पुदिना चटणीसह दिलेली सोनेरी बटाटा पॅटीस"},
    },
    "dabeli": {
        "hi": {"name": "डबेली", "description": "अनार के साथ कच्छी मीठी और तीखी आलू बर्गर"},
        "mr": {"name": "डबेली", "description": "डाळिंबासह कच्छी गोड आणि तिखट बटाटा बर्गर"},
    },
    "banana bread": {
        "hi": {"name": "बनाना ब्रेड", "description": "अखरोट और दालचीनी के साथ ताज़ा बेक्ड नम केक"},
        "mr": {"name": "बनाना ब्रेड", "description": "अक्रोड आणि दालचिनीसह ताजा भाजलेला ओलसर केक"},
    },
    "butter croissant": {
        "hi": {"name": "बटर क्रोइसां", "description": "हर सुबह ताज़ा बेक्ड कुरकुरा सुनहरा बटर क्रोइसां"},
        "mr": {"name": "बटर क्रोसां", "description": "दररोज सकाळी ताजा भाजलेला खुसखुशीत सोनेरी बटर क्रोसां"},
    },
    "chocolate muffin": {
        "hi": {"name": "चॉकलेट मफिन", "description": "नरम और गर्म बेक्ड गहरे चॉकलेट चिप मफिन"},
        "mr": {"name": "चॉकलेट मफिन", "description": "मऊ आणि उबदार भाजलेला गडद चॉकलेट चिप मफिन"},
    },
    "cinnamon roll": {
        "hi": {"name": "दालचीनी रोल", "description": "ब्राउन शुगर और दालचीनी के साथ गर्म ग्लेज़्ड रोल"},
        "mr": {"name": "दालचिनी रोल", "description": "ब्राऊन शुगर आणि दालचिनीसह उबदार ग्लेझ्ड रोल"},
    },
    "whole wheat bread": {
        "hi": {"name": "होल व्हीट ब्रेड", "description": "पत्थर से पिसे आटे से बनी आर्टिज़न साबुत गेहूं की ब्रेड"},
        "mr": {"name": "होल व्हीट ब्रेड", "description": "दगडावर दळलेल्या पिठापासून बनवलेला संपूर्ण गव्हाचा ब्रेड"},
    },
    "nankhatai cookies": {
        "hi": {"name": "नानखटाई कुकीज़", "description": "इलायची के स्वाद वाली पारंपरिक भारतीय शॉर्टब्रेड कुकीज़"},
        "mr": {"name": "नानखटाई कुकीज", "description": "वेलचीच्या चवीच्या पारंपरिक भारतीय शॉर्टब्रेड कुकीज"},
    },
    "cold coffee": {
        "hi": {"name": "कोल्ड कॉफी", "description": "ठंडे दूध और आइसक्रीम के साथ क्लासिक ब्लेंडेड एस्प्रेसो"},
        "mr": {"name": "कोल्ड कॉफी", "description": "थंड दूध आणि आइस्क्रीमसह क्लासिक ब्लेंडेड एस्प्रेसो"},
    },
    "cold brew": {
        "hi": {"name": "कोल्ड ब्रू", "description": "बर्फ पर परोसी 16 घंटे धीमी आंच पर बनी आर्टिज़न कॉफी"},
        "mr": {"name": "कोल्ड ब्र्यू", "description": "बर्फावर दिलेली १६ तास हळू तयार केलेली आर्टिझन कॉफी"},
    },
    "iced latte": {
        "hi": {"name": "आइस्ड लाटे", "description": "ठंडे दूध और बर्फ पर डाला गया मुलायम एस्प्रेसो"},
        "mr": {"name": "आइस्ड लाटे", "description": "थंड दूध आणि बर्फावर ओतलेला मऊ एस्प्रेसो"},
    },
    "lemon iced tea": {
        "hi": {"name": "लेमन आइस्ड टी", "description": "ताज़े नींबू और पुदीने के साथ ताज़गी भरी काली चाय"},
        "mr": {"name": "लेमन आइस्ड टी", "description": "ताज्या लिंबू आणि पुदिन्यासह ताजेतवाने काळा चहा"},
    },
    "mango cooler": {
        "hi": {"name": "मैंगो कूलर", "description": "कुचली बर्फ के साथ मिश्रित उष्णकटिबंधीय अल्फांसो आम का गूदा"},
        "mr": {"name": "मँगो कूलर", "description": "बर्फासह मिसळलेला उष्णकटिबंधीय हापूस आंब्याचा गर"},
    },
    "virgin mojito": {
        "hi": {"name": "वर्जिन मोजिटो", "description": "कुटा हुआ पुदीना, नींबू का रस और स्पार्कलिंग सोडा"},
        "mr": {"name": "व्हर्जिन मोहितो", "description": "ठेचलेला पुदिना, लिंबाचा रस आणि स्पार्कलिंग सोडा"},
    },
    "watermelon cooler": {
        "hi": {"name": "वॉटरमेलन कूलर", "description": "काले नमक और पुदीने के साथ ताज़ा निचोड़ा तरबूज़ जूस"},
        "mr": {"name": "वॉटरमेलन कूलर", "description": "काळ्या मिठासह आणि पुदिन्यासह ताजा पिळलेला टरबूज रस"},
    },
}


def translated_name_and_description(name: str, description: str | None, lang: str) -> tuple[str, str | None]:
    """Returns (name, description) translated into lang if we have an entry
    and lang is "hi"/"mr" (Devanagari) - "en" and "hinglish" both use the
    menu's own English/Romanized names as-is (Hinglish is Hindi meaning in
    Roman script, and these names already read naturally that way, e.g.
    "Masala Chai", "Vada Pav" - no separate Hinglish variant needed). Falls
    back to the original English name/description untranslated when there's
    no entry (e.g. a newly admin-added item)."""
    if lang not in ("hi", "mr"):
        return name, description

    entry = MENU_TRANSLATIONS.get(name.strip().lower(), {}).get(lang)
    if entry is None:
        return name, description
    return entry.get("name", name), entry.get("description", description)
