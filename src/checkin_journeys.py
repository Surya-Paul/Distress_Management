"""Survivor-controlled, non-diagnostic multilingual check-in journeys.

This module contains channel-neutral journey rules and reviewed copy. It does
not infer a condition, score a person, or send a message/call. Delivery
adapters must use the returned safe script only after checking the current
consent and contact-preference record.
"""

from __future__ import annotations

from copy import deepcopy

from config import (
    CHECKIN_ACCESSIBILITY_NEEDS,
    CHECKIN_BASE_LANGUAGE_PACKS,
    CHECKIN_CHANNELS,
    CHECKIN_CHANNEL_LABELS,
    CHECKIN_JOURNEY_VERSION,
    CHECKIN_SUPPORT_CHOICES,
    SAFE_FOLLOW_UP_CHANNELS,
)


class CheckinJourneyValidationError(ValueError):
    """Raised when a journey tries to store ambiguous or unsupported data."""


# Every pack supplies the same short, survivor-facing content keys. New packs
# must supply every key; falling back to English would not be language support.
_ENGLISH_COPY = {
    "control": "You are in control. This is a short, optional check-in. You never need to describe what happened.",
    "consent": "Would you like to continue with this optional check-in?",
    "safe_time": "Is now a safe time to talk or receive a message?",
    "safe_channel": "Which channel would feel safest for a later check-in?",
    "programme_mention": "May a future message or call mention the programme?",
    "accessibility": "Would any of these make this check-in easier for you?",
    "safety": "Before anything else, do you feel safe right now?",
    "wellbeing": "Would you like to share how things are feeling today? You may skip this.",
    "support": "Which practical support, if any, would you like to discuss with a trained person?",
    "skip": "Skip",
    "pause": "Pause",
    "stop": "Stop",
    "human_help": "Request a trained person",
    "not_safe": "I need help from a trained person now",
    "no_programme": "Do not mention the programme",
}

_COPY = {
    "en": _ENGLISH_COPY,
    "hi": {
        "control": "नियंत्रण आपके पास है। यह छोटा, वैकल्पिक हालचाल पूछने का संवाद है। आपको घटना फिर से बताने की ज़रूरत नहीं है।",
        "consent": "क्या आप इस वैकल्पिक संवाद को जारी रखना चाहेंगे?",
        "safe_time": "क्या अभी बात करने या संदेश पाने का सुरक्षित समय है?",
        "safe_channel": "बाद में हालचाल पूछने के लिए कौन-सा माध्यम सबसे सुरक्षित लगेगा?",
        "programme_mention": "क्या भविष्य के संदेश या कॉल में कार्यक्रम का नाम लिया जा सकता है?",
        "accessibility": "क्या इनमें से कोई विकल्प इस संवाद को आपके लिए आसान बनाएगा?",
        "safety": "सबसे पहले, क्या आप अभी सुरक्षित महसूस कर रहे हैं?",
        "wellbeing": "क्या आप बताना चाहेंगे कि आज कैसा महसूस हो रहा है? आप इसे छोड़ सकते हैं।",
        "support": "आप किसी प्रशिक्षित व्यक्ति से किस व्यावहारिक सहायता पर बात करना चाहेंगे?",
        "skip": "छोड़ें", "pause": "रोकें", "stop": "बंद करें", "human_help": "प्रशिक्षित व्यक्ति से बात करने का अनुरोध करें",
        "not_safe": "मुझे अभी प्रशिक्षित व्यक्ति की मदद चाहिए", "no_programme": "कार्यक्रम का उल्लेख न करें",
    },
    "bn": {
        "control": "নিয়ন্ত্রণ আপনার হাতে। এটি একটি ছোট, ঐচ্ছিক খোঁজ-খবর। কী ঘটেছিল তা আবার বলতে হবে না।",
        "consent": "আপনি কি এই ঐচ্ছিক খোঁজ-খবরটি চালিয়ে যেতে চান?",
        "safe_time": "এখন কথা বলা বা বার্তা পাওয়ার জন্য নিরাপদ সময় কি?",
        "safe_channel": "পরে খোঁজ নেওয়ার জন্য কোন মাধ্যমটি সবচেয়ে নিরাপদ মনে হবে?",
        "programme_mention": "ভবিষ্যতের বার্তা বা কলে কি কর্মসূচির নাম উল্লেখ করা যাবে?",
        "accessibility": "এর মধ্যে কোনটি এই খোঁজ-খবরটি আপনার জন্য সহজ করবে?",
        "safety": "সবার আগে, আপনি কি এখন নিরাপদ বোধ করছেন?",
        "wellbeing": "আজ কেমন লাগছে তা কি বলতে চান? আপনি এই প্রশ্নটি এড়িয়ে যেতে পারেন।",
        "support": "একজন প্রশিক্ষিত ব্যক্তির সঙ্গে কোন ব্যবহারিক সহায়তা নিয়ে কথা বলতে চান?",
        "skip": "এড়িয়ে যান", "pause": "বিরতি", "stop": "বন্ধ করুন", "human_help": "প্রশিক্ষিত ব্যক্তির সাহায্য চান",
        "not_safe": "এখনই একজন প্রশিক্ষিত ব্যক্তির সাহায্য চাই", "no_programme": "কর্মসূচির নাম উল্লেখ করবেন না",
    },
    "ta": {
        "control": "கட்டுப்பாடு உங்களிடமே உள்ளது. இது ஒரு சுருக்கமான, விருப்பமான நலவிசாரிப்பு. நடந்ததை மீண்டும் சொல்ல வேண்டியதில்லை.",
        "consent": "இந்த விருப்பமான நலவிசாரிப்பைத் தொடர விரும்புகிறீர்களா?",
        "safe_time": "இப்போது பேசவோ அல்லது செய்தி பெறவோ பாதுகாப்பான நேரமா?",
        "safe_channel": "பின்னர் நலவிசாரிக்க எந்த வழி உங்களுக்கு மிகவும் பாதுகாப்பாக இருக்கும்?",
        "programme_mention": "எதிர்கால செய்தி அல்லது அழைப்பில் திட்டத்தின் பெயரைக் குறிப்பிடலாமா?",
        "accessibility": "இவற்றில் ஏதேனும் இந்த நலவிசாரிப்பை உங்களுக்கு எளிதாக்குமா?",
        "safety": "முதலில், நீங்கள் இப்போது பாதுகாப்பாக உணருகிறீர்களா?",
        "wellbeing": "இன்று எப்படி உணர்கிறீர்கள் என்பதைப் பகிர விரும்புகிறீர்களா? இதைத் தவிர்க்கலாம்.",
        "support": "பயிற்சி பெற்ற ஒருவருடன் எந்த நடைமுறை ஆதரவைப் பற்றி பேச விரும்புகிறீர்கள்?",
        "skip": "தவிர்க்கவும்", "pause": "இடைநிறுத்தவும்", "stop": "நிறுத்தவும்", "human_help": "பயிற்சி பெற்ற ஒருவரின் உதவியைக் கோரவும்",
        "not_safe": "இப்போது பயிற்சி பெற்ற ஒருவரின் உதவி வேண்டும்", "no_programme": "திட்டத்தைப் பற்றிக் குறிப்பிட வேண்டாம்",
    },
}

_OPTION_COPY = {
    "en": {
        "yes": "Yes", "no": "No", "not_stated": "Prefer not to say", "safe_now": "I feel safe right now",
        "not_sure": "I am not sure", "want_to_talk": "I would like to talk to someone",
        "doing_ok": "I do not want to discuss this now", "callback": "A callback", "no_follow_up": "No follow-up",
        "chatbot": "Chatbot", "ivrs": "IVRS call", "sms": "SMS", "mobile_app": "Mobile app",
        "web_portal": "Web portal", "counsellor_follow_up": "Counsellor follow-up",
        "counselling": "Counselling", "medical_care": "Medical care", "witness_protection": "Witness protection",
        "relocation": "Relocation support", "financial_relief": "Financial relief", "legal_aid": "Legal aid",
        "rehabilitation": "Rehabilitation", "transport": "Transport", "low_literacy": "Short spoken options",
        "low_connectivity": "Low-connectivity option", "hearing_access": "Hearing-access support", "speech_access": "Speech-access support",
        "vision_access": "Vision-access support", "cognitive_or_memory_support": "Extra time or reminders",
        "prefer_human_support": "Prefer a person", "other_or_not_stated": "Other or prefer not to say",
    },
    "hi": {
        "yes": "हाँ", "no": "नहीं", "not_stated": "न बताना पसंद है", "safe_now": "मैं अभी सुरक्षित महसूस कर रहा/रही हूँ",
        "not_sure": "मुझे पक्का नहीं है", "want_to_talk": "मैं किसी से बात करना चाहता/चाहती हूँ",
        "doing_ok": "मैं अभी इस पर बात नहीं करना चाहता/चाहती", "callback": "वापस कॉल", "no_follow_up": "फॉलो-अप नहीं",
        "chatbot": "चैटबॉट", "ivrs": "आईवीआरएस कॉल", "sms": "एसएमएस", "mobile_app": "मोबाइल ऐप",
        "web_portal": "वेब पोर्टल", "counsellor_follow_up": "परामर्शदाता का फॉलो-अप",
        "counselling": "परामर्श", "medical_care": "चिकित्सकीय देखभाल", "witness_protection": "गवाह सुरक्षा",
        "relocation": "स्थानांतरण सहायता", "financial_relief": "वित्तीय सहायता", "legal_aid": "कानूनी सहायता",
        "rehabilitation": "पुनर्वास", "transport": "परिवहन", "low_literacy": "छोटे बोले गए विकल्प",
        "low_connectivity": "कम कनेक्टिविटी विकल्प", "hearing_access": "सुनने संबंधी सहायता", "speech_access": "बोलने संबंधी सहायता",
        "vision_access": "देखने संबंधी सहायता", "cognitive_or_memory_support": "अतिरिक्त समय या याद दिलाना",
        "prefer_human_support": "किसी व्यक्ति से बात करना", "other_or_not_stated": "अन्य या न बताना पसंद है",
    },
    "bn": {
        "yes": "হ্যাঁ", "no": "না", "not_stated": "বলতে চাই না", "safe_now": "আমি এখন নিরাপদ বোধ করছি",
        "not_sure": "আমি নিশ্চিত নই", "want_to_talk": "আমি কারও সঙ্গে কথা বলতে চাই",
        "doing_ok": "আমি এখন এ বিষয়ে কথা বলতে চাই না", "callback": "ফিরতি কল", "no_follow_up": "ফলো-আপ নয়",
        "chatbot": "চ্যাটবট", "ivrs": "আইভিআরএস কল", "sms": "এসএমএস", "mobile_app": "মোবাইল অ্যাপ",
        "web_portal": "ওয়েব পোর্টাল", "counsellor_follow_up": "পরামর্শদাতার ফলো-আপ",
        "counselling": "পরামর্শ", "medical_care": "চিকিৎসা", "witness_protection": "সাক্ষী সুরক্ষা",
        "relocation": "স্থানান্তর সহায়তা", "financial_relief": "আর্থিক সহায়তা", "legal_aid": "আইনি সহায়তা",
        "rehabilitation": "পুনর্বাসন", "transport": "যাতায়াত", "low_literacy": "ছোট বলা বিকল্প",
        "low_connectivity": "কম সংযোগের বিকল্প", "hearing_access": "শ্রবণ সহায়তা", "speech_access": "বাক্ সহায়তা",
        "vision_access": "দেখার সহায়তা", "cognitive_or_memory_support": "অতিরিক্ত সময় বা স্মরণ করানো",
        "prefer_human_support": "একজন মানুষের সঙ্গে কথা", "other_or_not_stated": "অন্যান্য বা বলতে চাই না",
    },
    "ta": {
        "yes": "ஆம்", "no": "இல்லை", "not_stated": "சொல்ல விரும்பவில்லை", "safe_now": "நான் இப்போது பாதுகாப்பாக உணர்கிறேன்",
        "not_sure": "எனக்குத் தெரியவில்லை", "want_to_talk": "யாரிடமாவது பேச விரும்புகிறேன்",
        "doing_ok": "இப்போது இதைப் பற்றி பேச விரும்பவில்லை", "callback": "மீண்டும் அழைப்பு", "no_follow_up": "தொடர்பு வேண்டாம்",
        "chatbot": "உரையாடல் உதவியாளர்", "ivrs": "IVRS அழைப்பு", "sms": "SMS", "mobile_app": "மொபைல் செயலி",
        "web_portal": "இணைய தளம்", "counsellor_follow_up": "ஆலோசகரின் தொடர்நடவடிக்கை",
        "counselling": "ஆலோசனை", "medical_care": "மருத்துவ உதவி", "witness_protection": "சாட்சி பாதுகாப்பு",
        "relocation": "இடமாற்ற உதவி", "financial_relief": "நிதி உதவி", "legal_aid": "சட்ட உதவி",
        "rehabilitation": "மறுவாழ்வு", "transport": "போக்குவரத்து", "low_literacy": "குறுகிய பேசும் விருப்பங்கள்",
        "low_connectivity": "குறைந்த இணைப்பு விருப்பம்", "hearing_access": "கேட்கும் உதவி", "speech_access": "பேசும் உதவி",
        "vision_access": "பார்வை உதவி", "cognitive_or_memory_support": "கூடுதல் நேரம் அல்லது நினைவூட்டல்",
        "prefer_human_support": "ஒரு நபருடன் பேச விருப்பம்", "other_or_not_stated": "மற்றவை அல்லது சொல்ல விரும்பவில்லை",
    },
}

for _code in CHECKIN_BASE_LANGUAGE_PACKS:
    if set(_COPY[_code]) != set(_ENGLISH_COPY) or set(_OPTION_COPY[_code]) != set(_OPTION_COPY["en"]):
        raise RuntimeError(f"Check-in language pack {_code} is incomplete.")


def language_catalog():
    """Return the base Indian-language framework without making quality claims."""
    return [
        {"code": code, **metadata, "journey_version": CHECKIN_JOURNEY_VERSION}
        for code, metadata in CHECKIN_BASE_LANGUAGE_PACKS.items()
    ]


def get_language_pack(language_code: str):
    if language_code not in _COPY:
        raise CheckinJourneyValidationError("A complete, reviewed language pack is required for this check-in.")
    return {"copy": deepcopy(_COPY[language_code]), "options": deepcopy(_OPTION_COPY[language_code])}


def option_label(language_code: str, value: str) -> str:
    return get_language_pack(language_code)["options"].get(value, value.replace("_", " ").title())


def _require_bool(value, field):
    if type(value) is not bool:
        raise CheckinJourneyValidationError(f"{field} must be a JSON boolean.")
    return value


def _require_choice(value, allowed, field, *, allow_blank=False):
    if allow_blank and value in (None, ""):
        return None
    if not isinstance(value, str) or value not in allowed:
        raise CheckinJourneyValidationError(f"{field} must use a supported option.")
    return value


def _require_choices(value, allowed, field):
    if not isinstance(value, list) or len(value) != len(set(value)) or any(item not in allowed for item in value):
        raise CheckinJourneyValidationError(f"{field} must be a unique list of supported options.")
    return value


def validate_checkin_start(payload: dict) -> dict:
    """Validate the consent-and-contact stage before any wellbeing question."""
    if not isinstance(payload, dict):
        raise CheckinJourneyValidationError("Check-in settings must be structured data.")
    required = {
        "channel", "language_code", "consent_recorded", "safe_time", "safe_channel",
        "programme_mention_allowed", "accessibility_needs",
    }
    if set(payload) != required:
        raise CheckinJourneyValidationError("Check-in settings contain missing or unsupported fields.")
    language_code = _require_choice(payload["language_code"], _COPY, "language_code")
    safe_time = _require_choice(payload["safe_time"], {"safe_now", "another_time", "not_stated"}, "safe_time")
    return {
        "channel": _require_choice(payload["channel"], CHECKIN_CHANNELS, "channel"),
        "language_code": language_code,
        "consent_recorded": _require_bool(payload["consent_recorded"], "consent_recorded"),
        "safe_time": safe_time,
        "safe_channel": _require_choice(payload["safe_channel"], SAFE_FOLLOW_UP_CHANNELS, "safe_channel"),
        # Silence is never treated as permission to disclose the programme.
        "programme_mention_allowed": _require_bool(
            payload["programme_mention_allowed"], "programme_mention_allowed"
        ),
        "accessibility_needs": _require_choices(
            payload["accessibility_needs"], CHECKIN_ACCESSIBILITY_NEEDS, "accessibility_needs"
        ),
    }


def validate_checkin_update(payload: dict) -> dict:
    """Accept only short, non-incident check-in responses and control actions."""
    if not isinstance(payload, dict) or not payload:
        raise CheckinJourneyValidationError("A structured journey update is required.")
    allowed = {"immediate_safety", "wellbeing", "support_choices", "control", "request_human_help", "next_step"}
    if set(payload) - allowed:
        raise CheckinJourneyValidationError("The journey update contains unsupported fields.")
    result = {}
    if "immediate_safety" in payload:
        result["immediate_safety"] = _require_choice(
            payload["immediate_safety"], {"safe_now", "not_sure", "need_human_help_now", "skip"}, "immediate_safety"
        )
    if "wellbeing" in payload:
        result["wellbeing"] = _require_choice(
            payload["wellbeing"], {"want_to_talk", "doing_ok", "skip"}, "wellbeing"
        )
    if "support_choices" in payload:
        result["support_choices"] = _require_choices(payload["support_choices"], CHECKIN_SUPPORT_CHOICES, "support_choices")
    if "control" in payload:
        result["control"] = _require_choice(payload["control"], {"pause", "stop", "complete"}, "control")
    if "request_human_help" in payload:
        result["request_human_help"] = _require_bool(payload["request_human_help"], "request_human_help")
    if "next_step" in payload:
        result["next_step"] = _require_choice(payload["next_step"], {"safety", "wellbeing", "support", "complete"}, "next_step")
    return result


def channel_delivery_guidance(language_code: str, channel: str, *, programme_mention_allowed: bool) -> dict:
    """Return a non-disclosing first-touch script and accessibility safeguards.

    The caller must still validate the stored safe channel/time before delivery.
    In particular, SMS copy never includes case, wellbeing, caste, legal, or
    incident information; programme identity appears only after explicit yes.
    """
    pack = get_language_pack(language_code)["copy"]
    if channel not in CHECKIN_CHANNELS:
        raise CheckinJourneyValidationError("A supported delivery channel is required.")
    identity = "This is a private check-in from the programme. " if programme_mention_allowed else ""
    if channel == "sms":
        return {
            "channel": channel,
            "first_touch": identity + "Is this a safe time for a private check-in? Reply 1 for yes, 2 for not now, 0 for a trained person, or 9 to stop.",
            "rules": ["One short question per message.", "Never include case, health, caste, legal, or incident information.", "Do not send if SMS is not the recorded safe channel."],
        }
    if channel == "ivrs":
        return {
            "channel": channel,
            "first_touch": identity + pack["control"] + " " + pack["consent"],
            "rules": ["Use one short spoken question at a time.", "Repeat: press 7; trained person: press 0; pause: press 8; stop: press 9.", "Offer a non-IVRS safe alternative for hearing-access needs; never treat silence as consent."],
        }
    lead = identity + pack["control"]
    return {
        "channel": channel,
        "first_touch": lead + " " + pack["consent"],
        "rules": ["Show skip, pause, stop, and trained-person help on every screen or turn.", "Do not ask for incident details.", "Check immediate safety before wellbeing or service questions."],
    }


def journey_blueprint(language_code: str, channel: str, *, programme_mention_allowed=False) -> list[dict]:
    """Describe the required order for chatbot, IVRS, SMS, app, portal and staff follow-up."""
    pack = get_language_pack(language_code)["copy"]
    guidance = channel_delivery_guidance(language_code, channel, programme_mention_allowed=programme_mention_allowed)
    return [
        {"step": "consent_and_contact", "prompt": pack["consent"], "required_before_next": True,
         "includes": ["preferred language", "safe time", "safe channel", "programme mention permission", "accessibility needs"]},
        {"step": "immediate_safety", "prompt": pack["safety"], "required_before_next": True,
         "includes": ["safe now", "not sure", "trained-person help", "skip"]},
        {"step": "wellbeing_optional", "prompt": pack["wellbeing"], "required_before_next": False,
         "includes": ["talk to someone", "not now", "skip"]},
        {"step": "practical_support", "prompt": pack["support"], "required_before_next": False,
         "includes": list(CHECKIN_SUPPORT_CHOICES)},
        {"step": "channel_safeguards", "prompt": guidance["first_touch"], "required_before_next": True,
         "includes": guidance["rules"]},
    ]


def ivrs_accessibility_fallback(language_code: str) -> dict:
    """Provide a usable, non-text-dependent IVRS alternative plan."""
    get_language_pack(language_code)
    return {
        "design": [
            "Speak slowly; offer one short option per turn and a repeat key.",
            "Use keypad choices as well as speech; never require reading a text message.",
            "For low connectivity, allow a pause and a survivor-selected later attempt rather than repeated calling.",
            "For hearing or speech-access needs, offer the recorded safe app, portal, chatbot, or trained-person route.",
            "Keep 0 for a trained person, 8 for pause, and 9 for stop on every IVRS turn.",
        ],
        "not_supported": ["Automated external escalation", "Third-party disclosure", "Repeated calling after no response"],
    }


# ---------------------------------------------------------------------------
# Extensible Indian-language framework
# ---------------------------------------------------------------------------

EXTENSIBILITY_GUIDE = """
To add a new Indian language (e.g., Marathi, Telugu, Kannada):

1. Create a complete copy dict with EVERY key present in _ENGLISH_COPY.
   All values must be human-reviewed, plain-language translations —
   never machine-translated without expert validation.

2. Create a complete option dict with EVERY key present in _OPTION_COPY["en"].

3. Register the pack by calling:
       register_language_pack(
           code="mr",
           name="Marathi",
           autonym="मराठी",
           copy_dict={...},
           option_dict={...},
       )

4. The pack is validated at registration time — missing keys cause a
   CheckinJourneyValidationError. Once registered, it is available to
   all journey functions.

5. Use language_evaluation_report(code) to generate a per-language
   completeness and quality checklist before any deployment.

6. Each language pack must be evaluated independently. A language is
   never treated as validated merely because it shares a script or
   model with another language.
"""


def register_language_pack(
    code: str, name: str, autonym: str, copy_dict: dict, option_dict: dict,
) -> None:
    """Add a new language pack at runtime after validation.

    Raises CheckinJourneyValidationError if any required key is missing.
    This is the single entry point for extending language support.
    """
    missing_copy = set(_ENGLISH_COPY) - set(copy_dict)
    if missing_copy:
        raise CheckinJourneyValidationError(
            f"Language pack '{code}' is missing copy keys: {sorted(missing_copy)}"
        )
    missing_opts = set(_OPTION_COPY["en"]) - set(option_dict)
    if missing_opts:
        raise CheckinJourneyValidationError(
            f"Language pack '{code}' is missing option keys: {sorted(missing_opts)}"
        )
    _COPY[code] = deepcopy(copy_dict)
    _OPTION_COPY[code] = deepcopy(option_dict)
    # Also register in the config-level pack registry so language_catalog()
    # picks it up.
    CHECKIN_BASE_LANGUAGE_PACKS[code] = {"name": name, "autonym": autonym}


def language_evaluation_report(language_code: str) -> dict:
    """Return a per-language quality report for deployment readiness review.

    Each language is evaluated independently — a language is never treated as
    validated because it shares a script or model with another.
    """
    report = {
        "language_code": language_code,
        "registered": language_code in _COPY,
        "copy_keys_complete": False,
        "option_keys_complete": False,
        "copy_key_count": 0,
        "option_key_count": 0,
        "expected_copy_keys": len(_ENGLISH_COPY),
        "expected_option_keys": len(_OPTION_COPY["en"]),
        "missing_copy_keys": [],
        "missing_option_keys": [],
        "empty_values": [],
        "reviewed": False,
        "notes": [],
    }
    if not report["registered"]:
        report["notes"].append("Language pack not registered. Use register_language_pack() first.")
        return report

    pack_copy = _COPY[language_code]
    pack_opts = _OPTION_COPY[language_code]
    report["copy_key_count"] = len(pack_copy)
    report["option_key_count"] = len(pack_opts)
    report["missing_copy_keys"] = sorted(set(_ENGLISH_COPY) - set(pack_copy))
    report["missing_option_keys"] = sorted(set(_OPTION_COPY["en"]) - set(pack_opts))
    report["copy_keys_complete"] = len(report["missing_copy_keys"]) == 0
    report["option_keys_complete"] = len(report["missing_option_keys"]) == 0

    # Check for empty values
    for key, value in pack_copy.items():
        if not value or not str(value).strip():
            report["empty_values"].append(f"copy.{key}")
    for key, value in pack_opts.items():
        if not value or not str(value).strip():
            report["empty_values"].append(f"option.{key}")

    report["reviewed"] = (
        report["copy_keys_complete"]
        and report["option_keys_complete"]
        and len(report["empty_values"]) == 0
    )
    if report["reviewed"]:
        report["notes"].append("All keys present and non-empty. Ready for human review of translation quality.")
    else:
        report["notes"].append("Pack is incomplete or contains empty values. Not ready for deployment.")
    return report

