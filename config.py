"""Shared configuration for the survivor-support triage prototype.

This prototype provides decision support only. It does not diagnose a mental
health condition, determine credibility, or authorise an intervention.
"""

import os

GROQ_CHAT_MODEL = "openai/gpt-oss-20b"
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"

# These bands express review timeliness, not a clinical condition or finding
# that a person is unsafe.
SUPPORT_PRIORITY_BANDS = [
    {"min": 0, "max": 29, "label": "Routine review", "color": "#4CAF50", "emoji": "🟢"},
    {"min": 30, "max": 59, "label": "Timely review", "color": "#FFC107", "emoji": "🟡"},
    {"min": 60, "max": 84, "label": "Prompt review", "color": "#FF9800", "emoji": "🟠"},
    {"min": 85, "max": 100, "label": "Urgent human review", "color": "#B71C1C", "emoji": "🚨"},
]

URGENT_REVIEW_THRESHOLD = 85
PROMPT_REVIEW_THRESHOLD = 60
SERVICE_COORDINATION_THRESHOLD = 70
RISING_SPI_DELTA = 15

# The SPI configuration is deliberately separate from validated questionnaire
# scoring.  Values below are the first immutable configuration version; later
# versions are stored in SQLite with their author and rationale.  An SPI is a
# human-review ordering aid only, and no score authorises coercive, irreversible,
# legal, compensation, protection, or service action.
DEFAULT_SPI_THRESHOLD_CONFIG = {
    "version": "spi-thresholds.v1",
    "physical_safety_weight": 35.0,
    "wellbeing_weight": 20.0,
    "service_access_weight": 15.0,
    "explicit_statement_weight": 15.0,
    "recent_change_weight": 10.0,
    "unanswered_followups_weight": 5.0,
    "unanswered_followups_reference": 2,
    "reported_threat_floor": 70.0,
    "explicit_self_harm_floor": 85.0,
    "timely_review_threshold": 30.0,
    "prompt_review_threshold": 60.0,
    "urgent_review_threshold": 85.0,
    "material_change_points": 15.0,
}

SPI_FEATURE_SET_VERSION = "spi-feature-set.v2"
SPI_FEATURE_SET = (
    "explicit_supported_signals; reported_threat_or_immediate_danger; "
    "unmet_service_needs; comparable_recent_change; unanswered_followups"
)

# Audio analysis is optional experimental research metadata. It is disabled by
# default, never a support-priority feature, and this prototype never persists
# raw recordings. Any retention request belongs in an authorised external
# records system with its own approval, access control, and retention policy.
AUDIO_ANALYSIS_DEFAULT_ENABLED = False
RAW_AUDIO_RETENTION_POLICY = "discard_after_transcription"
EXPERIMENTAL_AUDIO_LIMITATION = (
    "Optional voice analysis is experimental and may be inaccurate due to recording quality, language, "
    "device, or other limitations. It does not diagnose anything and is never used on its own to raise a concern or change a follow-up priority score."
)

MAX_AUDIO_DURATION_SECONDS = 300
MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024

# Crisis workflow safeguards. Automatic escalation is limited to an internal,
# access-controlled queue. The application never sends an SMS or contacts a
# survivor, relative, police officer, or service provider directly.
CRISIS_PATHWAYS = {
    "SELF_HARM_CONCERN": {
        "label": "Someone may be thinking about hurting themselves",
        "default_role": "Counsellor",
        "suggested_next_action": (
            "A trained counsellor should promptly look at what was said, check that permission "
            "was given, follow the safe way to reach this person, and discuss available support."
        ),
    },
    "EXTERNAL_SAFETY_THREAT": {
        "label": "Someone may be in danger from another person",
        "default_role": "District safety officer",
        "suggested_next_action": (
            "An authorised safety officer should look at the reported concern and evidence, "
            "follow the safe way to reach this person, and discuss protection options with them where appropriate."
        ),
    },
}

APPROVED_AUTOMATIC_ESCALATION_CHANNELS = ("secure_internal_case_queue",)
SAFE_OUTREACH_CHANNELS = ("approved_secure_call", "approved_secure_portal")
SERVICE_DIRECTORY_TYPES = ("emergency", "counselling", "protection", "medical", "legal_aid")

# These are suggested discussion steps. They never trigger a referral,
# notification, case change, or other action without a trained human reviewer.
INTERVENTIONS = {
    "physical_safety": (
        "A trained staff member should look at the safety concern using the person's "
        "preferred safe way of being contacted before discussing any protection options "
        "(such as witness protection or relocation support)."
    ),
    "wellbeing": (
        "A trained counsellor should check in with the person through an agreed safe "
        "channel and talk about support options they may want (such as counselling "
        "or medical treatment)."
    ),
    "service_access": (
        "A trained coordinator should talk with the person about any barriers to getting "
        "help and what support they would prefer (such as financial assistance, legal aid, "
        "or rehabilitation measures), before making any referral or changing records."
    ),
    "trend": (
        "A trained staff member should look at the change alongside the data's limitations "
        "before deciding whether a follow-up is needed."
    ),
}

DIMENSION_LABELS = {
    "physical_safety": "Safety concern",
    "wellbeing": "Emotional wellbeing concern",
    "service_access": "Difficulty getting services or help",
    "contact_preferences": "How this person prefers to be contacted",
}

APP_TITLE = "🧭 NHAA Support System"
APP_SUBTITLE = "Helping staff support the people we serve"
APP_VERSION = "2.0.0-prototype"

# Privacy architecture. Case/wellbeing data, identity/contact data, and the
# immutable security audit trail use distinct stores. Local SQLite is permitted
# only for development/test; deployment must configure a managed, encrypted
# database connection and a KMS-provided field-encryption key.
DEPLOYMENT_ENVIRONMENT = os.environ.get("NHAA_DEPLOYMENT_ENV", "development").lower()
STORAGE_BACKEND = os.environ.get("NHAA_STORAGE_BACKEND", "isolated_sqlite_development")
PRODUCTION_STORAGE_BACKEND = "managed_encrypted_postgres"
CASE_DB_PATH = os.environ.get("NHAA_CASE_DB_PATH", os.environ.get("NHAA_DB_PATH", "nhaa_case_wellbeing.db"))
IDENTITY_DB_PATH = os.environ.get("NHAA_IDENTITY_DB_PATH", "nhaa_identity_contact.db")
AUDIT_DB_PATH = os.environ.get("NHAA_AUDIT_DB_PATH", "nhaa_security_audit.db")
# Compatibility alias for the case/wellbeing store only. No identity/contact
# data belongs in this database.
DB_PATH = CASE_DB_PATH
FIELD_ENCRYPTION_KEY_ENV = "NHAA_FIELD_ENCRYPTION_KEY"
FIELD_ENCRYPTION_KEY_VERSION = os.environ.get("NHAA_FIELD_ENCRYPTION_KEY_VERSION", "local-dev-v1")
LOCAL_DEVELOPMENT_KEY_PATH = os.environ.get("NHAA_LOCAL_FIELD_KEY_PATH", ".nhaa-local-field-encryption.key")
DATABASE_URL = os.environ.get("NHAA_DATABASE_URL")
MINIMUM_AGGREGATE_CELL_SIZE = int(os.environ.get("NHAA_MINIMUM_AGGREGATE_CELL_SIZE", "5"))
DEFAULT_RETENTION_DAYS = int(os.environ.get("NHAA_DEFAULT_RETENTION_DAYS", "2555"))
PROJECTION_DAYS = int(os.environ.get("NHAA_PROJECTION_DAYS", "14"))

ROLE_NAMES = (
    "counsellor", "district_officer", "state_administrator", "national_administrator", "auditor",
    "clinical_reviewer", "survivor_advocate", "legal_officer", "child_protection_officer",
    "security_officer", "privacy_officer"
)

# Pre-deployment governance
DEPLOYMENT_MODE = os.environ.get("NHAA_DEPLOYMENT_MODE", "PILOT").upper()
GOVERNANCE_DOMAINS = (
    "clinical", "survivor_advocate", "legal", "child_protection", 
    "security", "privacy", "district_operations"
)
GO_NO_GO_THRESHOLDS = {
    "min_sensitivity": 0.90,
    "min_precision": 0.85,
    "max_false_negative_urgent": 0.01,
    "max_false_alert_burden": 0.15,
}

LANGUAGES = {
    "English": "en",
    "हिन्दी (Hindi)": "hi",
    "বাংলা (Bengali)": "bn",
    "தமிழ் (Tamil)": "ta",
}

# Guided check-ins are deliberately separate from clinical tools and free-text
# assessment. A channel is a delivery format, not permission to contact a
# person: each use must first honour their current consent and safe-contact
# choice. New Indian-language packs can be added through the language-pack
# registry only after their complete journey copy has been reviewed.
CHECKIN_JOURNEY_VERSION = "checkin-journey.v1"
CHECKIN_CHANNELS = (
    "chatbot", "ivrs", "sms", "mobile_app", "web_portal", "counsellor_follow_up",
)
CHECKIN_CHANNEL_LABELS = {
    "chatbot": "Chatbot",
    "ivrs": "Automated phone call (IVRS)",
    "sms": "Text message (SMS)",
    "mobile_app": "Mobile app",
    "web_portal": "Website",
    "counsellor_follow_up": "Counsellor follow-up call",
}
SAFE_FOLLOW_UP_CHANNELS = CHECKIN_CHANNELS + ("no_follow_up",)
CHECKIN_SUPPORT_CHOICES = (
    "counselling", "medical_care", "witness_protection", "relocation",
    "financial_relief", "legal_aid", "rehabilitation", "transport", "callback",
)
CHECKIN_ACCESSIBILITY_NEEDS = (
    "low_literacy", "low_connectivity", "hearing_access", "speech_access",
    "vision_access", "cognitive_or_memory_support", "prefer_human_support", "other_or_not_stated",
)

# All listed packs must be evaluated independently before production use. The
# registry records that evaluation by language and component; a language is not
# treated as validated merely because it shares a script or model with another.
CHECKIN_BASE_LANGUAGE_PACKS = {
    "en": {"name": "English", "autonym": "English"},
    "hi": {"name": "Hindi", "autonym": "हिन्दी"},
    "bn": {"name": "Bengali", "autonym": "বাংলা"},
    "ta": {"name": "Tamil", "autonym": "தமிழ்"},
}

PRIVACY_AND_SAFETY_NOTE = """
**Safety and privacy — please read**

This system helps staff make decisions — it does not make decisions by itself.
It is not a medical tool, an emergency response system, or an automatic
case-management system.

• Only record information the person has agreed to share.
• **Never type names, phone numbers, addresses, or other personal details**
  into notes or text boxes. Personal details go only in the separate secure
  system, not in case notes or dashboards.
• Who can see what is controlled by each person's role, location, and purpose,
  and every access is logged.
• Before making any referral, protection step, service change, or legal update,
  a trained and authorised staff member must review it — and the person's own
  choice matters.

This version uses local test data. A live version requires approved secure
databases, verified staff login, and completed privacy, security, clinical,
and legal reviews.
"""
