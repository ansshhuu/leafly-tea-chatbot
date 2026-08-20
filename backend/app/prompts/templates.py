
TEMPLATES: dict[str, dict[str, str]] = {
    "escalation_response": {
        "en": "I'm really sorry to hear that. I've made a note of this for our team. If you'd like to speak to someone directly, please email us at {email}.",
        "hi": "यह सुनकर मुझे बहुत खेद है। मैंने इसे हमारी टीम के लिए नोट कर लिया है। अगर आप सीधे किसी से बात करना चाहें, तो कृपया हमें {email} पर ईमेल करें।",
        "hinglish": "Yeh sunkar mujhe bahut afsos hua. Maine iski note hamari team ke liye kar li hai. Agar aap directly kisi se baat karna chahein, toh please humein {email} par email karein.",
    },
    "faq_about_intro": {
        "en": (
            "Leafly is about pure tea, done right — {tagline}. We use whole, unbroken leaves, source "
            "single-origin teas with a clear story, follow ethical and sustainable sourcing practices, "
            "and blend everything in small batches for freshness.\n\n"
            "You can always reach us at {email}."
        ),
    },
}


def t(key: str, lang: str = "en", **kwargs) -> str:
    entry = TEMPLATES.get(key, {})
    template = entry.get(lang) or entry.get("en", "")
    return template.format(**kwargs)
