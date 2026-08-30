"""
Translation module for the NHAA Support Triage app.

TWO SEPARATE SYSTEMS — do not merge them:

  UI_STRINGS          General UI labels, buttons, headings, captions, error
                      messages.  These were generated with LLM assistance and
                      cached statically — they are NOT called live on render.
                      A human translator must review them before production use.
                      See review-urgency flags in the comments below.

  VALIDATED_QUESTIONNAIRES
                      PHQ-9 and GAD-7 question wording ONLY.
                      English text is the canonical published wording.
                      Hindi (hi) text is sourced from peer-reviewed validation
                      studies (Cronbach's alpha ≥ 0.83; see inline citations).
                      Bengali and Tamil are NOT included yet — the app will
                      fall back to English with a visible warning when those
                      languages are selected, rather than silently showing
                      English or using an LLM translation.
                      DO NOT add a language here from an LLM translation —
                      source from phqscreeners.com or a peer-reviewed paper only.

REVIEW URGENCY FLAGS (used in UI_STRINGS):
  # [REVIEW: COSMETIC]          Navigation labels, chart titles, placeholder
                                text — low clinical risk, fix before public launch.
  # [REVIEW: CONSENT/SAFETY]    Consent checkboxes, crisis banners, data-deletion
                                warnings, not-a-diagnosis disclaimers — must be
                                reviewed by a qualified bilingual clinician/legal
                                reviewer BEFORE any user-facing deployment.
"""

import streamlit as st
from config import LANGUAGES


# ---------------------------------------------------------------------------
# t() — general UI translation helper
# ---------------------------------------------------------------------------

def t(key: str) -> str:
    """Return the UI string for the current session language, falling back to English."""
    lang_name = st.session_state.get("selected_language", "English")
    lang_code = LANGUAGES.get(lang_name, "en")
    en_strings = UI_STRINGS.get("en", {})
    lang_strings = UI_STRINGS.get(lang_code, en_strings)
    return lang_strings.get(key, en_strings.get(key, key))


# ---------------------------------------------------------------------------
# VALIDATED_QUESTIONNAIRES — official instrument translations only
# ---------------------------------------------------------------------------

def get_questionnaire_questions(instrument: str, lang_name: str):
    """
    Return (lang_used, questions_list) for the given instrument and language.

    If an approved translation exists for the requested language, it is
    returned as-is.  If not, returns ("en", english_questions) and emits a
    visible Streamlit warning — never silently falls back, never machine-
    translates.
    """
    lang_code = LANGUAGES.get(lang_name, "en")
    instrument_data = VALIDATED_QUESTIONNAIRES.get(instrument, {})
    if lang_code in instrument_data:
        return lang_code, instrument_data[lang_code]
    # Visible fallback — do not remove this warning
    lang_display = lang_name
    st.warning(
        f"An approved translation of this check-in is not yet available in "
        f"{lang_display}. Showing the English version.\n\n"
        "Only officially verified translations are used for these questions. "
        "Contact an admin to add a verified translation for this language."
    )
    return "en", instrument_data["en"]


VALIDATED_QUESTIONNAIRES = {
    # -----------------------------------------------------------------------
    # PHQ-9
    # English: canonical published wording (Kroenke, Spitzer & Williams 2001)
    # Hindi:   from peer-reviewed validation studies published in Indian
    #          academic journals (e.g. Kumar et al.; Cronbach α = 0.83–0.84).
    #          Corroborated across multiple independent validations.
    #          DO NOT modify without replacing with another peer-reviewed source.
    # Bengali: PENDING — add only from banglajol.info validation paper text.
    # Tamil:   PENDING — add only from a peer-reviewed Tamil validation study.
    # -----------------------------------------------------------------------
    "PHQ-9": {
        "en": [
            "Little interest or pleasure in doing things",
            "Feeling down, depressed, or hopeless",
            "Trouble falling or staying asleep, or sleeping too much",
            "Feeling tired or having little energy",
            "Poor appetite or overeating",
            "Feeling bad about yourself — or that you are a failure or have let yourself or your family down",
            "Trouble concentrating on things, such as reading the newspaper or watching television",
            "Moving or speaking so slowly that other people could have noticed? Or the opposite — being so fidgety or restless that you have been moving around a lot more than usual",
            "Thoughts that you would be better off dead or of hurting yourself in some way",
        ],
        "hi": [
            # Source: multiple peer-reviewed Hindi PHQ-9 validation studies;
            # wording verified against Kumar et al. and cross-checked with
            # APA-published Hindi reference text.
            "काम करने में कम रुचि या आनंद",
            "निराश, उदास या हताश महसूस करना",
            "नींद आने या सोते रहने में परेशानी, या बहुत अधिक सोना",
            "थकावट महसूस होना या कम ऊर्जा महसूस होना",
            "भूख कम लगना या अधिक खाना",
            "अपने बारे में बुरा महसूस करना — या यह सोचना कि आप असफल हैं या आपने खुद को या अपने परिवार को निराश किया है",
            "किसी चीज़ पर ध्यान केंद्रित करने में परेशानी, जैसे कि अखबार पढ़ना या टेलीविज़न देखना",
            "इतनी धीमी गति से चलना या बोलना कि दूसरे लोग नोटिस कर लें, या इसके विपरीत इतना बेचैन होना कि आप सामान्य से कहीं ज़्यादा इधर-उधर घूम रहे हों",
            # [REVIEW: CONSENT/SAFETY] — self-harm item; verify Hindi wording
            # with a bilingual clinician before deployment.
            "ऐसे विचार कि मर जाना या खुद को किसी तरह से चोट पहुँचाना बेहतर होगा",
        ],
    },
    # -----------------------------------------------------------------------
    # GAD-7
    # English: canonical published wording (Spitzer et al. 2006)
    # Hindi:   from Mendeley Data / Indian validation datasets (α ≥ 0.90).
    #          DO NOT modify without replacing with another peer-reviewed source.
    # Bengali/Tamil: PENDING
    # -----------------------------------------------------------------------
    "GAD-7": {
        "en": [
            "Feeling nervous, anxious, or on edge",
            "Not being able to stop or control worrying",
            "Worrying too much about different things",
            "Trouble relaxing",
            "Being so restless that it is hard to sit still",
            "Becoming easily annoyed or irritable",
            "Feeling afraid as if something awful might happen",
        ],
        "hi": [
            # Source: Mendeley Hindi GAD-7 validation dataset; verified against
            # ILAE-published Hindi reference.
            "घबराहट महसूस होना, बेचैन रहना या बहुत तनाव में रहना",
            "चिंता करना बंद न कर पाना या चिंता पर नियंत्रण न रख पाना",
            "अलग-अलग चीज़ों के बारे में बहुत अधिक चिंता करना",
            "आराम करने में परेशानी होना",
            "इतने बेचैन होना कि चुप बैठना मुश्किल हो",
            "आसानी से चिड़चिड़े हो जाना या गुस्सा आ जाना",
            "ऐसा महसूस होना कि कुछ बुरा होने वाला है",
        ],
    },
}


# ---------------------------------------------------------------------------
# UI_STRINGS — static label translations
# Generated with LLM assistance; see review-urgency flags.
# ---------------------------------------------------------------------------

UI_STRINGS = {
    # =======================================================================
    # ENGLISH (canonical source — all other languages must match this meaning)
    # =======================================================================
    "en": {
        # --- App-wide / sidebar -------------------------------------------
        # [REVIEW: COSMETIC]
        "app_title": "🧭 NHAA Support System",
        "app_subtitle": "Helping staff support the people we serve",
        "language_label": "🌐 Language",
        "language_help": "Choose the language being spoken or written",
        "privacy_expander": "🔒 Privacy and safety information",
        "logged_in_as": "Logged in as",

        # --- Page 1: Record a conversation --------------------------------
        # [REVIEW: COSMETIC]
        "p1_heading": "📝 Record a new conversation",
        "p1_subheading": "This helps staff understand what support someone may need — it is never a diagnosis or an automatic decision.",
        # [REVIEW: CONSENT/SAFETY]
        "p1_warning": (
            "Only record information the person has agreed to share. "
            "Do not type names, phone numbers, addresses, or other personal details here. "
            "The person can pause, skip, or say no at any time. "
            "A trained staff member must review everything before any action is taken."
        ),
        # [REVIEW: COSMETIC]
        "p1_case_selection": "Case selection",
        "p1_choose_existing": "Choose an existing case",
        "p1_start_new": "Start a new case",
        "p1_case_reference": "Case reference number",
        "p1_state": "State",
        "p1_district": "District",
        "p1_new_case_caption": "A new case reference number will be created automatically. Do not enter a name or phone number here.",
        "p1_channel_label": "How did this conversation happen?",
        "p1_channel_caption": "Record how the person prefers to be contacted in the secure case system, not in this text box.",
        "p1_missed_checkins": "Missed planned check-ins",
        "p1_missed_checkins_help": "Count only agreed check-ins that got no response. If the person chose to stop or pause, that is not a missed check-in.",
        # [REVIEW: CONSENT/SAFETY]
        "p1_consent_checkbox": (
            "I confirm that the person has given their permission for this conversation to be recorded and analysed, "
            "and that they can stop or say no at any time."
        ),
        # [REVIEW: COSMETIC]
        "p1_tab_text": "📄 Notes or written record",
        "p1_tab_audio": "🎙️ Audio recording",
        "p1_notes_placeholder": (
            "Record only what the person chose to share. Avoid incident detail unless necessary for immediate support. "
            "Example: 'I am worried about attending the hearing and need help understanding transport support.'"
        ),
        "p1_notes_label": "Brief, relevant interaction notes",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_info": (
            "Audio transcription is optional. Voice analysis is experimental and turned off by default — "
            "it does not diagnose anything and may be inaccurate. "
            "It cannot create a review task or change the follow-up priority score."
        ),
        "p1_audio_consent": "I confirm that the person has given specific permission for their audio to be transcribed.",
        # [REVIEW: COSMETIC]
        "p1_audio_method": "Recording method",
        "p1_record_now": "Record now",
        "p1_upload_file": "Upload a file",
        "p1_audio_input_label": "Record the conversation",
        "p1_upload_label": "Upload a consented recording",
        "p1_audio_discard_caption": "Raw audio is not stored by this prototype. It is discarded after transcription; any authorised retention must use a separate approved records system.",
        "p1_audio_quality": "Recording quality",
        "p1_audio_limitations": "Recording or device limitations",
        "p1_audio_limitations_help": "Select only known recording limitations. Do not enter identifying device details.",
        "p1_audio_analysis_opt_in": "Turn on optional experimental voice analysis for this recording",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_analysis_consent": "I confirm that separate, specific permission for this optional voice analysis has been recorded.",
        # [REVIEW: COSMETIC]
        "p1_audio_uncertainty": "How confident is the voice analysis model?",
        "p1_audio_uncertainty_help": "Choose a cautious value. This does not measure anyone's wellbeing or safety.",
        "p1_transcribe_button": "Transcribe recording",
        "p1_transcribe_spinner": "Transcribing the consented recording...",
        "p1_transcript_review_label": "Check the text before continuing",
        "p1_save_button": "Save and prepare for staff review",
        # [REVIEW: CONSENT/SAFETY]
        "p1_no_consent_info": "Please confirm permission before preparing a record for review.",
        # [REVIEW: COSMETIC]
        "p1_analysis_spinner": "Organising information for staff review...",

        # --- Page 2: Case history -----------------------------------------
        # [REVIEW: COSMETIC]
        "p2_heading": "📈 Case history",
        "p2_subheading": "See how follow-up priority has changed over time, with the evidence and limitations behind each estimate. This is not a medical chart.",
        "p2_caption": "A higher follow-up priority score means a staff member may need to check in sooner. It does not prove danger, make a diagnosis, judge truthfulness, or trigger any automatic action. Trend labels only appear when records can be fairly compared.",
        "p2_case_reference": "Case reference number",
        "p2_no_cases": "No cases found yet. Record a conversation first.",
        "p2_load_error": "Could not load case history",

        # --- Page 3: Staff review queue -----------------------------------
        # [REVIEW: COSMETIC]
        "p3_heading": "👥 Cases waiting for staff review",
        "p3_subheading": "These cases need to be looked at by trained staff before anyone is contacted, referred, or any records are changed.",
        # [REVIEW: CONSENT/SAFETY]
        "p3_warning": (
            "A review task is not a diagnosis, a judgement about truthfulness, or proof of danger. "
            "Do not act on it without looking at the evidence, original notes, limitations, the person's permission, and how they prefer to be contacted."
        ),
        # [REVIEW: COSMETIC]
        "p3_waiting": "Waiting for review",
        "p3_urgent": "Urgent",
        "p3_priority": "Priority",
        "p3_done": "Reviews done",
        "p3_load_error": "Could not load the review list",

        # --- Page 4: Overview ---------------------------------------------
        # [REVIEW: COSMETIC]
        "p4_heading": "🗺️ Overview",
        "p4_subheading": "Summary view of case volumes and urgency across areas. This does not show individual details or health outcomes.",
        "p4_caption": "Available only to State and national roles. Numbers are grouped to protect privacy; no individual cases, names, or notes are shown here.",
        "p4_cases_followed": "Cases being followed",
        "p4_scope": "Dashboard scope",
        "p4_privacy_threshold": "Minimum group size for privacy",
        "p4_by_state": "Cases by State",
        "p4_urgency": "How urgent are current cases?",
        "p4_urgency_by_state": "Urgency breakdown by state",
        "p4_download_button": "Download summary report",
        "p4_download_json_button": "Download summary report (JSON)",
        "p4_download_success": "Summary report downloaded. Individual case details and notes remain securely protected and are not included.",
        "p4_load_error": "Could not load the summary view",

        # --- Page 5: Urgent help process ----------------------------------
        # [REVIEW: COSMETIC]
        "p5_heading": "🚨 Urgent help process",
        "p5_subheading": "Separate staff review pathways for reported self-harm statements and external safety threats.",
        # [REVIEW: CONSENT/SAFETY]
        "p5_error_banner": (
            "This page does not send text messages, make calls, share information with outside services, or start a referral. "
            "Any contact must be made by a staff member using the person's agreed safe way to be reached."
        ),
        # [REVIEW: COSMETIC]
        "p5_show_closed": "Show resolved concerns",
        "p5_load_error": "Could not load urgent concerns",
        "p5_no_events": "No open urgent concerns.",

        # --- Page 6: Urgent help settings ---------------------------------
        # [REVIEW: COSMETIC]
        "p6_heading": "⚙️ Urgent help settings",
        "p6_subheading": "Configure responsible staff, response time targets, safe ways to reach people, and verified local services.",
        # [REVIEW: CONSENT/SAFETY]
        "p6_warning": (
            "For authorised staff only. This prototype has no SMS integration, no automated survivor outreach, "
            "and no emergency numbers hard-coded into the application. Verify all service entries before use."
        ),
        # [REVIEW: COSMETIC]
        "p6_tab_response": "Response times & assigned staff",
        "p6_tab_spi": "Follow-up priority settings",
        "p6_tab_contact": "Safe ways to reach people",
        "p6_tab_services": "Verified local services",
        "p6_access_error": "Only State or national administrators may access configuration. Casework roles cannot change shared workflow settings.",

        # --- Page 7: Wellbeing check-in -----------------------------------
        # [REVIEW: COSMETIC]
        "p7_heading": "📋 Standard wellbeing check-in (PHQ-9 / GAD-7)",
        "p7_subheading": "Optional standard check-in (PHQ-9 for mood, GAD-7 for anxiety) with recorded permission. The person can skip any question.",
        # [REVIEW: CONSENT/SAFETY]
        "p7_warning": (
            "Only use this exact check-in format when approved. "
            "A total score is not a medical diagnosis and is never used to make an automatic decision or change the follow-up priority score."
        ),
        # [REVIEW: COSMETIC]
        "p7_case_reference": "Case reference number",
        "p7_which_checkin": "Which check-in?",
        "p7_mood_checkin": "Mood check-in (PHQ-9)",
        "p7_worry_checkin": "Worry check-in (GAD-7)",
        "p7_instrument_help": "PHQ-9 is a standard mood questionnaire. GAD-7 is a standard worry/anxiety questionnaire. Both are recognised clinical instruments used worldwide.",
        "p7_skip_caption": "The person may skip any question. If they skip a question, no total score is calculated — we never guess their answers.",
        # [REVIEW: CONSENT/SAFETY]
        "p7_consent": "I confirm that the person has given specific permission for this check-in, and they know they can skip questions or stop at any time.",
        "p7_no_consent_info": "Please confirm permission above before starting the check-in questions.",
        # [REVIEW: COSMETIC]
        "p7_question_progress": "Question {current} of {total}",
        "p7_skip_option": "Skip this question",
        "p7_back_button": "⬅ Back",
        "p7_next_button": "Next ➡",
        "p7_finish_button": "✅ Finish check-in",
        "p7_save_stop_button": "💾 Save and stop here",
        "p7_save_stop_help": "Saves what has been answered so far and stops. No total score will be calculated if any question was skipped.",
        "p7_new_checkin_button": "Start a new check-in",
        "p7_access_error": "Questionnaire access is unavailable",
        "p7_no_cases": "Start a new case before recording an optional check-in.",

        # --- Page 8: Privacy & data rules ---------------------------------
        # [REVIEW: COSMETIC]
        "p8_heading": "🔐 Privacy & data rules",
        "p8_subheading": "How long data is kept, deleting records (needs two people), and activity logs that cannot be changed.",
        # [REVIEW: CONSENT/SAFETY]
        "p8_warning": (
            "Deleting a record removes personal details and notes, but keeps a basic log of what happened. "
            "Only use this if approved by the rules for managing records and respecting people's rights."
        ),
        # [REVIEW: COSMETIC]
        "p8_delete_heading": "Ask to delete a case",
        "p8_delete_caption": "A separate State or national administrator must approve this request. The request itself does not delete any content.",
        "p8_no_cases": "No in-scope active cases are available.",
        "p8_case_reference": "Case reference number",
        "p8_delete_reason": "Why this case needs to be deleted",
        "p8_request_deletion": "Request deletion",
        "p8_tab_retention": "How long we keep data",
        "p8_tab_deletions": "Record deletion requests",
        "p8_retention_version": "New retention-policy version",
        "p8_retention_days": "Retention period (days)",
        "p8_retention_rationale": "Approval rationale",
        "p8_create_retention": "Create retention-policy version",
        "p8_approve_deletion": "Approve deletion",
        "p8_execute_deletion": "Execute approved deletion",
        "p8_audit_heading": "Activity log check",
        "p8_audit_pass": "Hash-chain verification passed.",
        # [REVIEW: CONSENT/SAFETY]
        "p8_audit_fail": "Hash-chain verification failed. Escalate immediately through the security incident process.",
        # [REVIEW: COSMETIC]
        "p8_no_role": "This role has no privacy-governance operations.",
        "p8_access_error": "Privacy-governance access is unavailable",

        # --- Page 9: Follow-up schedule -----------------------------------
        # [REVIEW: COSMETIC]
        "p9_heading": "💬 Follow-up schedule",
        "p9_subheading": "Guided, step-by-step check-ins in the person's preferred language and channel.",
        "p9_safety_first_title": "🔒 Safety-first design",

        # --- Page 10: AI oversight (admin) --------------------------------
        # [REVIEW: COSMETIC]
        "p10_heading": "🛡️ AI oversight (admin)",
        "p10_subheading": "Approval checks, fairness tests, and version controls before using AI models.",
        "p10_tab_registry": "📦 AI versions & rollback",
        "p10_tab_eval": "📊 Performance & fairness checks",
        "p10_tab_signoffs": "✅ Expert sign-offs",
        "p10_tab_incidents": "🚨 Report an issue",
        "p5_what_shared": "**What was shared and how reliable it is**",
        "p5_no_evidence": "No evidence snapshot is available. Review the source notes before acting.",
        "p5_safe_ways": "**Safe ways to reach this person**",
        "p5_no_safe_way": "No safe way to contact this person has been recorded. Do not contact them.",
        "p5_case_history": "Case history for review",
        "p5_no_history": "No interaction history is available.",
        "p5_local_support": "Verified local support directory",
        "p5_no_local_services": "No verified local services are configured. Do not substitute unverified contact information.",
        "p5_internal_referral": "Internal referral history",
        "p5_no_outward_channel": "Only secure internal queue escalation is automated. No outward channel is available here.",
        "p5_accountable_role": "Accountable role",
        "p5_counsellor": "Counsellor",
        "p5_district_safety_officer": "District safety officer",
        "p5_staff_assigned": "Staff member assigned. No outreach was sent.",
        "p5_reviewer_attestation": "I am the assigned reviewer and have reviewed the evidence, limitations, consent, and safe-contact protocol.",
        "p5_confirm_attestation": "Confirm the acknowledgement attestation first.",
        "p5_ack_recorded": "Acknowledgement recorded. No automatic outreach was performed.",
        "p5_contact_log": "**Safe-contact attempt log**",
        "p5_no_contact_attempt": "No contact attempt has been logged.",
        "p5_record_attempt": "Record a human-performed safe-contact attempt",
        "p5_approved_channel": "Approved safe channel",
        "p5_outcome": "Outcome",
        "p5_reached": "REACHED",
        "p5_not_reached": "NOT_REACHED",
        "p5_attempt_logged": "Attempt logged. This system did not initiate the contact.",
        "p5_mark_resolved": "Mark as resolved",
        "p5_event_closed": "Crisis event closed with an auditable human outcome.",
        "p9_begin_new": "Begin a New Check-In",
        "p9_select_case_channel": "Select a case, channel, and language. Consent and safety preferences are collected first.",
        "p9_no_active_cases": "No active cases. Create a case through the Record Consented Interaction page first.",
        "p9_select_case": "Select case",
        "p9_preferred_language": "Preferred language",
        "p9_btn_begin_checkin": "✅ Begin Check-In",
        "p9_consent_required": "Consent is required to begin a check-in. The survivor may decline at any time.",
        "p9_continue_checkin": "Continue a Check-In",
        "p9_no_open_sessions": "No open check-in sessions. Start a new check-in in the first tab.",
        "p9_select_session": "Select session",
        "p9_how_to_deliver": "📡 How to deliver this check-in",
        "p9_ivrs_instructions": "🔊 Press **7** to repeat • **0** for a trained person • **8** to pause • **9** to stop",
        "p9_submit": "Submit",
        "p9_finish_checkin": "✅ Finish this check-in",
        "p9_checkin_complete": "Check-in marked as complete.",
        "p9_answers_recorded": "📜 Answers recorded so far",
        "p9_no_responses": "No responses recorded yet.",
        "p9_language_status": "Language support status",
        "p9_language_status_help": "Each language is evaluated independently. A language is never treated as validated merely because it shares a script or model with another.",
    },

    # =======================================================================
    # HINDI (हिन्दी)
    # LLM-generated; cached statically.
    # MUST be reviewed by a bilingual human translator before production use.
    # Items marked [REVIEW: CONSENT/SAFETY] require a clinician/legal reviewer.
    # =======================================================================
    "hi": {
        # --- App-wide / sidebar -------------------------------------------
        # [REVIEW: COSMETIC]
        "app_title": "🧭 NHAA सहायता प्रणाली",
        "app_subtitle": "हमारे लोगों की सहायता करने वाले कर्मचारियों की मदद करना",
        "language_label": "🌐 भाषा",
        "language_help": "जो भाषा बोली या लिखी जा रही है उसे चुनें",
        "privacy_expander": "🔒 गोपनीयता और सुरक्षा जानकारी",
        "logged_in_as": "लॉग इन किया है",

        # --- Page 1 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p1_heading": "📝 नई बातचीत दर्ज करें",
        "p1_subheading": "इससे कर्मचारियों को यह समझने में मदद मिलती है कि किसी को किस सहायता की ज़रूरत हो सकती है — यह कभी भी निदान या स्वचालित निर्णय नहीं है।",
        # [REVIEW: CONSENT/SAFETY]
        "p1_warning": (
            "केवल वही जानकारी दर्ज करें जिसे व्यक्ति ने साझा करने की सहमति दी हो। "
            "यहाँ नाम, फोन नंबर, पते या अन्य व्यक्तिगत विवरण न टाइप करें। "
            "व्यक्ति कभी भी रुक सकता है, छोड़ सकता है, या मना कर सकता है। "
            "कोई भी कार्रवाई करने से पहले एक प्रशिक्षित कर्मचारी को सभी चीज़ें समीक्षा करनी होगी।"
        ),
        # [REVIEW: COSMETIC]
        "p1_case_selection": "मामले का चयन",
        "p1_choose_existing": "मौजूदा मामला चुनें",
        "p1_start_new": "नया मामला शुरू करें",
        "p1_case_reference": "मामला संदर्भ संख्या",
        "p1_state": "राज्य",
        "p1_district": "जिला",
        "p1_new_case_caption": "एक नई मामला संदर्भ संख्या स्वचालित रूप से बनाई जाएगी। यहाँ नाम या फोन नंबर न डालें।",
        "p1_channel_label": "यह बातचीत कैसे हुई?",
        "p1_channel_caption": "व्यक्ति से संपर्क करने की पसंद सुरक्षित केस सिस्टम में दर्ज करें, इस टेक्स्ट बॉक्स में नहीं।",
        "p1_missed_checkins": "छूटे हुए नियोजित चेक-इन",
        "p1_missed_checkins_help": "केवल उन सहमत चेक-इन की गिनती करें जिनका कोई जवाब नहीं आया। अगर व्यक्ति ने रोकने या रुकने का चुनाव किया, तो वह छूटा हुआ चेक-इन नहीं है।",
        # [REVIEW: CONSENT/SAFETY]
        "p1_consent_checkbox": (
            "मैं पुष्टि करता/करती हूँ कि व्यक्ति ने इस बातचीत को रिकॉर्ड और विश्लेषण करने की अनुमति दी है, "
            "और वे किसी भी समय रुक सकते हैं या मना कर सकते हैं।"
        ),
        # [REVIEW: COSMETIC]
        "p1_tab_text": "📄 नोट्स या लिखित रिकॉर्ड",
        "p1_tab_audio": "🎙️ ऑडियो रिकॉर्डिंग",
        "p1_notes_placeholder": (
            "केवल वही दर्ज करें जो व्यक्ति ने साझा करना चुना। तत्काल सहायता के लिए ज़रूरी न हो तो घटना का विवरण न दें।"
        ),
        "p1_notes_label": "संक्षिप्त, प्रासंगिक बातचीत के नोट्स",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_info": (
            "ऑडियो ट्रांसक्रिप्शन वैकल्पिक है। आवाज़ विश्लेषण प्रायोगिक है और डिफ़ॉल्ट रूप से बंद है — "
            "यह कुछ भी निदान नहीं करता और गलत हो सकता है। "
            "यह कोई समीक्षा कार्य नहीं बना सकता या अनुवर्ती प्राथमिकता स्कोर नहीं बदल सकता।"
        ),
        "p1_audio_consent": "मैं पुष्टि करता/करती हूँ कि व्यक्ति ने अपनी ऑडियो ट्रांसक्रिप्ट करने की विशेष अनुमति दी है।",
        # [REVIEW: COSMETIC]
        "p1_audio_method": "रिकॉर्डिंग का तरीका",
        "p1_record_now": "अभी रिकॉर्ड करें",
        "p1_upload_file": "फ़ाइल अपलोड करें",
        "p1_audio_input_label": "बातचीत रिकॉर्ड करें",
        "p1_upload_label": "सहमत रिकॉर्डिंग अपलोड करें",
        "p1_audio_discard_caption": "इस प्रोटोटाइप में रॉ ऑडियो संग्रहीत नहीं होती। ट्रांसक्रिप्शन के बाद इसे हटा दिया जाता है।",
        "p1_audio_quality": "रिकॉर्डिंग गुणवत्ता",
        "p1_audio_limitations": "रिकॉर्डिंग या डिवाइस की सीमाएँ",
        "p1_audio_limitations_help": "केवल ज्ञात रिकॉर्डिंग सीमाएँ चुनें। पहचान योग्य डिवाइस विवरण न दर्ज करें।",
        "p1_audio_analysis_opt_in": "इस रिकॉर्डिंग के लिए वैकल्पिक प्रायोगिक आवाज़ विश्लेषण चालू करें",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_analysis_consent": "मैं पुष्टि करता/करती हूँ कि इस वैकल्पिक आवाज़ विश्लेषण के लिए अलग से विशेष अनुमति दर्ज की गई है।",
        # [REVIEW: COSMETIC]
        "p1_audio_uncertainty": "आवाज़ विश्लेषण मॉडल कितना आश्वस्त है?",
        "p1_audio_uncertainty_help": "सावधानी से मूल्य चुनें। यह किसी की भलाई या सुरक्षा नहीं मापता।",
        "p1_transcribe_button": "रिकॉर्डिंग ट्रांसक्रिप्ट करें",
        "p1_transcribe_spinner": "सहमत रिकॉर्डिंग ट्रांसक्रिप्ट हो रही है...",
        "p1_transcript_review_label": "जारी रखने से पहले पाठ जाँचें",
        "p1_save_button": "सहेजें और कर्मचारी समीक्षा के लिए तैयार करें",
        # [REVIEW: CONSENT/SAFETY]
        "p1_no_consent_info": "रिकॉर्ड तैयार करने से पहले अनुमति की पुष्टि करें।",
        # [REVIEW: COSMETIC]
        "p1_analysis_spinner": "कर्मचारी समीक्षा के लिए जानकारी व्यवस्थित की जा रही है...",

        # --- Page 2 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p2_heading": "📈 मामले का इतिहास",
        "p2_subheading": "देखें कि समय के साथ अनुवर्ती प्राथमिकता कैसे बदली है। यह कोई चिकित्सा चार्ट नहीं है।",
        "p2_caption": "अधिक अनुवर्ती प्राथमिकता स्कोर का मतलब है कि कर्मचारी को जल्द जाँच करनी पड़ सकती है। यह खतरा साबित नहीं करता, निदान नहीं करता, और कोई स्वचालित कार्रवाई नहीं करता।",
        "p2_case_reference": "मामला संदर्भ संख्या",
        "p2_no_cases": "अभी कोई मामला नहीं मिला। पहले एक बातचीत दर्ज करें।",
        "p2_load_error": "मामले का इतिहास लोड नहीं हो सका",

        # --- Page 3 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p3_heading": "👥 कर्मचारी समीक्षा के लिए प्रतीक्षारत मामले",
        "p3_subheading": "किसी से संपर्क करने, रेफर करने, या कोई रिकॉर्ड बदलने से पहले प्रशिक्षित कर्मचारी को इन मामलों को देखना होगा।",
        # [REVIEW: CONSENT/SAFETY]
        "p3_warning": (
            "समीक्षा कार्य निदान, सत्यता का निर्णय, या खतरे का प्रमाण नहीं है। "
            "साक्ष्य, मूल नोट्स, सीमाएँ, व्यक्ति की अनुमति और संपर्क वरीयता देखे बिना कार्रवाई न करें।"
        ),
        # [REVIEW: COSMETIC]
        "p3_waiting": "समीक्षा के लिए प्रतीक्षारत",
        "p3_urgent": "तत्काल",
        "p3_priority": "प्राथमिकता",
        "p3_done": "समीक्षाएँ पूर्ण",
        "p3_load_error": "समीक्षा सूची लोड नहीं हो सकी",

        # --- Page 4 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p4_heading": "🗺️ सिंहावलोकन",
        "p4_subheading": "क्षेत्रों में मामलों की संख्या और तात्कालिकता का सारांश। इसमें व्यक्तिगत विवरण नहीं दिखाए जाते।",
        "p4_caption": "केवल राज्य और राष्ट्रीय भूमिकाओं के लिए उपलब्ध। गोपनीयता की रक्षा के लिए संख्याएँ समूहीकृत हैं।",
        "p4_cases_followed": "फॉलो किए जा रहे मामले",
        "p4_scope": "डैशबोर्ड दायरा",
        "p4_privacy_threshold": "गोपनीयता के लिए न्यूनतम समूह आकार",
        "p4_by_state": "राज्य के अनुसार मामले",
        "p4_urgency": "वर्तमान मामले कितने तत्काल हैं?",
        "p4_urgency_by_state": "राज्य के अनुसार तात्कालिकता विवरण",
        "p4_download_button": "सारांश रिपोर्ट डाउनलोड करें",
        "p4_download_json_button": "सारांश रिपोर्ट डाउनलोड करें (JSON)",
        "p4_download_success": "सारांश रिपोर्ट डाउनलोड हुई। व्यक्तिगत मामले के विवरण और नोट्स सुरक्षित हैं।",
        "p4_load_error": "सारांश दृश्य लोड नहीं हो सका",

        # --- Page 5 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p5_heading": "🚨 तत्काल सहायता प्रक्रिया",
        "p5_subheading": "स्व-हानि और बाहरी खतरे की रिपोर्ट के लिए अलग-अलग कर्मचारी समीक्षा मार्ग।",
        # [REVIEW: CONSENT/SAFETY]
        "p5_error_banner": (
            "यह पृष्ठ टेक्स्ट संदेश नहीं भेजता, कॉल नहीं करता, बाहरी सेवाओं से जानकारी साझा नहीं करता, या रेफरल शुरू नहीं करता। "
            "किसी भी संपर्क के लिए कर्मचारी को व्यक्ति के सहमत सुरक्षित तरीके का उपयोग करना होगा।"
        ),
        # [REVIEW: COSMETIC]
        "p5_show_closed": "हल किए गए मामले दिखाएँ",
        "p5_load_error": "तत्काल चिंताएँ लोड नहीं हो सकीं",
        "p5_no_events": "कोई खुली तत्काल चिंता नहीं है।",

        # --- Page 6 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p6_heading": "⚙️ तत्काल सहायता सेटिंग्स",
        "p6_subheading": "जिम्मेदार कर्मचारी, प्रतिक्रिया समय लक्ष्य, लोगों से संपर्क के सुरक्षित तरीके और सत्यापित स्थानीय सेवाएँ कॉन्फ़िगर करें।",
        # [REVIEW: CONSENT/SAFETY]
        "p6_warning": (
            "केवल अधिकृत कर्मचारियों के लिए। इस प्रोटोटाइप में कोई SMS एकीकरण, स्वचालित आउटरीच, या आपातकालीन नंबर नहीं है। उपयोग से पहले सभी सेवा प्रविष्टियाँ सत्यापित करें।"
        ),
        # [REVIEW: COSMETIC]
        "p6_tab_response": "प्रतिक्रिया समय और असाइन कर्मचारी",
        "p6_tab_spi": "अनुवर्ती प्राथमिकता सेटिंग्स",
        "p6_tab_contact": "लोगों से संपर्क के सुरक्षित तरीके",
        "p6_tab_services": "सत्यापित स्थानीय सेवाएँ",
        "p6_access_error": "केवल राज्य या राष्ट्रीय प्रशासक ही कॉन्फ़िगरेशन तक पहुँच सकते हैं।",

        # --- Page 7 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p7_heading": "📋 मानक भलाई जाँच (PHQ-9 / GAD-7)",
        "p7_subheading": "दर्ज अनुमति के साथ वैकल्पिक मानक जाँच (PHQ-9 मनोदशा के लिए, GAD-7 चिंता के लिए)। व्यक्ति कोई भी प्रश्न छोड़ सकता है।",
        # [REVIEW: CONSENT/SAFETY]
        "p7_warning": (
            "इस सटीक जाँच प्रारूप का उपयोग केवल स्वीकृति के बाद करें। "
            "कुल स्कोर चिकित्सा निदान नहीं है और कभी भी स्वचालित निर्णय लेने या अनुवर्ती प्राथमिकता स्कोर बदलने के लिए उपयोग नहीं किया जाता।"
        ),
        # [REVIEW: COSMETIC]
        "p7_case_reference": "मामला संदर्भ संख्या",
        "p7_which_checkin": "कौन सी जाँच?",
        "p7_mood_checkin": "मनोदशा जाँच (PHQ-9)",
        "p7_worry_checkin": "चिंता जाँच (GAD-7)",
        "p7_instrument_help": "PHQ-9 मनोदशा के लिए मानक प्रश्नावली है। GAD-7 चिंता के लिए मानक प्रश्नावली है।",
        "p7_skip_caption": "व्यक्ति कोई भी प्रश्न छोड़ सकता है। यदि प्रश्न छोड़ा जाए, तो कुल स्कोर नहीं निकाला जाता।",
        # [REVIEW: CONSENT/SAFETY]
        "p7_consent": "मैं पुष्टि करता/करती हूँ कि व्यक्ति ने इस जाँच के लिए विशेष अनुमति दी है और वे जानते हैं कि प्रश्न छोड़ सकते हैं या किसी भी समय रुक सकते हैं।",
        "p7_no_consent_info": "जाँच प्रश्न शुरू करने से पहले ऊपर अनुमति की पुष्टि करें।",
        # [REVIEW: COSMETIC]
        "p7_question_progress": "प्रश्न {current} / {total}",
        "p7_skip_option": "यह प्रश्न छोड़ें",
        "p7_back_button": "⬅ वापस",
        "p7_next_button": "अगला ➡",
        "p7_finish_button": "✅ जाँच पूरी करें",
        "p7_save_stop_button": "💾 सहेजें और यहाँ रुकें",
        "p7_save_stop_help": "अब तक दिए गए उत्तर सहेजें और रुकें। यदि कोई प्रश्न छोड़ा गया तो कुल स्कोर नहीं निकाला जाएगा।",
        "p7_new_checkin_button": "नई जाँच शुरू करें",
        "p7_access_error": "प्रश्नावली तक पहुँच उपलब्ध नहीं है",
        "p7_no_cases": "वैकल्पिक जाँच दर्ज करने से पहले एक नया मामला शुरू करें।",

        # --- Page 8 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p8_heading": "🔐 गोपनीयता और डेटा नियम",
        "p8_subheading": "डेटा कितने समय तक रखा जाता है, रिकॉर्ड हटाना (दो लोगों की ज़रूरत), और बदले न जा सकने वाले गतिविधि लॉग।",
        # [REVIEW: CONSENT/SAFETY]
        "p8_warning": (
            "रिकॉर्ड हटाने से व्यक्तिगत विवरण और नोट्स हट जाते हैं, लेकिन एक बुनियादी लॉग रहता है। "
            "इसका उपयोग केवल तभी करें जब रिकॉर्ड प्रबंधन और अधिकारों के नियमों द्वारा अनुमोदित हो।"
        ),
        # [REVIEW: COSMETIC]
        "p8_delete_heading": "मामला हटाने का अनुरोध करें",
        "p8_delete_caption": "इस अनुरोध को एक अलग राज्य या राष्ट्रीय प्रशासक द्वारा अनुमोदित किया जाना चाहिए।",
        "p8_no_cases": "दायरे में कोई सक्रिय मामला उपलब्ध नहीं है।",
        "p8_case_reference": "मामला संदर्भ संख्या",
        "p8_delete_reason": "यह मामला क्यों हटाया जाना चाहिए",
        "p8_request_deletion": "हटाने का अनुरोध करें",
        "p8_tab_retention": "डेटा कितने समय तक रखा जाता है",
        "p8_tab_deletions": "रिकॉर्ड हटाने के अनुरोध",
        "p8_retention_version": "नई डेटा-रखरखाव नीति संस्करण",
        "p8_retention_days": "डेटा रखने की अवधि (दिनों में)",
        "p8_retention_rationale": "अनुमोदन का कारण",
        "p8_create_retention": "डेटा-रखरखाव नीति संस्करण बनाएँ",
        "p8_approve_deletion": "हटाने की मंजूरी दें",
        "p8_execute_deletion": "अनुमोदित विलोपन निष्पादित करें",
        "p8_audit_heading": "गतिविधि लॉग जाँच",
        "p8_audit_pass": "हैश-चेन सत्यापन पास हुआ।",
        # [REVIEW: CONSENT/SAFETY]
        "p8_audit_fail": "हैश-चेन सत्यापन विफल। सुरक्षा घटना प्रक्रिया के माध्यम से तुरंत एस्केलेट करें।",
        # [REVIEW: COSMETIC]
        "p8_no_role": "इस भूमिका में कोई गोपनीयता-प्रशासन संचालन नहीं है।",
        "p8_access_error": "गोपनीयता-प्रशासन तक पहुँच उपलब्ध नहीं है",

        # --- Page 9 -------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p9_heading": "💬 अनुवर्ती कार्यक्रम",
        "p9_subheading": "व्यक्ति की पसंदीदा भाषा और चैनल में निर्देशित, चरण-दर-चरण जाँच।",
        "p9_safety_first_title": "🔒 सुरक्षा-पहले डिज़ाइन",

        # --- Page 10 ------------------------------------------------------
        # [REVIEW: COSMETIC]
        "p10_heading": "🛡️ AI निगरानी (व्यवस्थापक)",
        "p10_subheading": "AI मॉडल उपयोग करने से पहले अनुमोदन जाँच, निष्पक्षता परीक्षण और संस्करण नियंत्रण।",
        "p10_tab_registry": "📦 AI संस्करण और रोलबैक",
        "p10_tab_eval": "📊 प्रदर्शन और निष्पक्षता जाँच",
        "p10_tab_signoffs": "✅ विशेषज्ञ हस्ताक्षर",
        "p10_tab_incidents": "🚨 समस्या रिपोर्ट करें",
        "p5_what_shared": "**क्या साझा किया गया था और यह कितना विश्वसनीय है**",
        "p5_no_evidence": "कोई साक्ष्य स्नैपशॉट उपलब्ध नहीं है। कार्य करने से पहले स्रोत नोट्स की समीक्षा करें।",
        "p5_safe_ways": "**इस व्यक्ति तक पहुंचने के सुरक्षित तरीके**",
        "p5_no_safe_way": "इस व्यक्ति से संपर्क करने का कोई सुरक्षित तरीका दर्ज नहीं किया गया है। उनसे संपर्क न करें।",
        "p5_case_history": "समीक्षा के लिए मामले का इतिहास",
        "p5_no_history": "कोई बातचीत इतिहास उपलब्ध नहीं है।",
        "p5_local_support": "सत्यापित स्थानीय सहायता निर्देशिका",
        "p5_no_local_services": "कोई सत्यापित स्थानीय सेवा कॉन्फ़िगर नहीं की गई है। असत्यापित संपर्क जानकारी को प्रतिस्थापित न करें।",
        "p5_internal_referral": "आंतरिक रेफरल इतिहास",
        "p5_no_outward_channel": "केवल सुरक्षित आंतरिक कतार वृद्धि स्वचालित है। यहाँ कोई बाहरी चैनल उपलब्ध नहीं है।",
        "p5_accountable_role": "जवाबदेह भूमिका",
        "p5_counsellor": "परामर्शदाता",
        "p5_district_safety_officer": "जिला सुरक्षा अधिकारी",
        "p5_staff_assigned": "कर्मचारी को सौंपा गया। कोई आउटरीच नहीं भेजा गया था।",
        "p5_reviewer_attestation": "मैं नियुक्त समीक्षक हूँ और मैंने साक्ष्य, सीमाओं, सहमति और सुरक्षित-संपर्क प्रोटोकॉल की समीक्षा की है।",
        "p5_confirm_attestation": "पहले पावती प्रमाणीकरण की पुष्टि करें।",
        "p5_ack_recorded": "पावती दर्ज की गई। कोई स्वचालित आउटरीच नहीं किया गया था।",
        "p5_contact_log": "**सुरक्षित-संपर्क प्रयास लॉग**",
        "p5_no_contact_attempt": "कोई संपर्क प्रयास लॉग नहीं किया गया है।",
        "p5_record_attempt": "मानव-प्रदर्शन सुरक्षित-संपर्क प्रयास रिकॉर्ड करें",
        "p5_approved_channel": "अनुमोदित सुरक्षित चैनल",
        "p5_outcome": "परिणाम",
        "p5_reached": "पहुंच गया",
        "p5_not_reached": "नहीं पहुंचा",
        "p5_attempt_logged": "प्रयास लॉग किया गया। इस प्रणाली ने संपर्क शुरू नहीं किया।",
        "p5_mark_resolved": "हल के रूप में चिह्नित करें",
        "p5_event_closed": "संकट की घटना एक श्रव्य मानव परिणाम के साथ बंद हो गई।",
        "p9_begin_new": "एक नया चेक-इन शुरू करें",
        "p9_select_case_channel": "एक मामला, चैनल और भाषा चुनें। सहमति और सुरक्षा प्राथमिकताएं पहले एकत्र की जाती हैं।",
        "p9_no_active_cases": "कोई सक्रिय मामला नहीं। पहले रिकॉर्ड सहमति प्राप्त बातचीत पृष्ठ के माध्यम से एक मामला बनाएँ।",
        "p9_select_case": "मामला चुनें",
        "p9_preferred_language": "पसंदीदा भाषा",
        "p9_btn_begin_checkin": "✅ चेक-इन शुरू करें",
        "p9_consent_required": "चेक-इन शुरू करने के लिए सहमति आवश्यक है। उत्तरजीवी किसी भी समय मना कर सकता है।",
        "p9_continue_checkin": "एक चेक-इन जारी रखें",
        "p9_no_open_sessions": "कोई खुला चेक-इन सत्र नहीं। पहले टैब में एक नया चेक-इन शुरू करें।",
        "p9_select_session": "सत्र चुनें",
        "p9_how_to_deliver": "📡 यह चेक-इन कैसे प्रदान करें",
        "p9_ivrs_instructions": "🔊 दोहराने के लिए **7** दबाएँ • एक प्रशिक्षित व्यक्ति के लिए **0** • रोकने के लिए **8** • बंद करने के लिए **9**",
        "p9_submit": "जमा करें",
        "p9_finish_checkin": "✅ यह चेक-इन पूरा करें",
        "p9_checkin_complete": "चेक-इन पूरा हो गया है।",
        "p9_answers_recorded": "📜 अब तक दर्ज किए गए उत्तर",
        "p9_no_responses": "अभी तक कोई प्रतिक्रिया दर्ज नहीं की गई है।",
        "p9_language_status": "भाषा समर्थन स्थिति",
        "p9_language_status_help": "प्रत्येक भाषा का स्वतंत्र रूप से मूल्यांकन किया जाता है। किसी भाषा को केवल इसलिए मान्य नहीं माना जाता है क्योंकि यह किसी अन्य के साथ एक स्क्रिप्ट या मॉडल साझा करती है।",
    },

    # =======================================================================
    # BENGALI (বাংলা)
    # LLM-generated; cached statically.
    # [REVIEW: CONSENT/SAFETY] items require bilingual clinician review.
    # =======================================================================
    "bn": {
        # [REVIEW: COSMETIC]
        "app_title": "🧭 NHAA সহায়তা সিস্টেম",
        "app_subtitle": "আমাদের মানুষদের সহায়তা করতে কর্মীদের সাহায্য করা",
        "language_label": "🌐 ভাষা",
        "language_help": "যে ভাষায় কথা বলা বা লেখা হচ্ছে সেটি নির্বাচন করুন",
        "privacy_expander": "🔒 গোপনীয়তা এবং নিরাপত্তা তথ্য",
        "logged_in_as": "লগ ইন করেছেন",
        "p1_heading": "📝 নতুন কথোপকথন রেকর্ড করুন",
        "p1_subheading": "এটি কর্মীদের বুঝতে সাহায্য করে কাউকে কী সহায়তা দরকার — এটি কখনো রোগ নির্ণয় বা স্বয়ংক্রিয় সিদ্ধান্ত নয়।",
        # [REVIEW: CONSENT/SAFETY]
        "p1_warning": (
            "শুধুমাত্র সেই তথ্যই রেকর্ড করুন যা ব্যক্তি শেয়ার করতে সম্মত হয়েছেন। "
            "এখানে নাম, ফোন নম্বর, ঠিকানা বা অন্যান্য ব্যক্তিগত তথ্য টাইপ করবেন না। "
            "ব্যক্তি যেকোনো সময় থামতে, এড়িয়ে যেতে বা না বলতে পারেন।"
        ),
        # [REVIEW: COSMETIC]
        "p1_case_selection": "মামলা নির্বাচন",
        "p1_choose_existing": "বিদ্যমান মামলা বেছে নিন",
        "p1_start_new": "নতুন মামলা শুরু করুন",
        "p1_case_reference": "মামলার রেফারেন্স নম্বর",
        "p1_state": "রাজ্য",
        "p1_district": "জেলা",
        "p1_new_case_caption": "একটি নতুন মামলার রেফারেন্স নম্বর স্বয়ংক্রিয়ভাবে তৈরি হবে।",
        "p1_channel_label": "এই কথোপকথন কীভাবে হয়েছিল?",
        "p1_channel_caption": "ব্যক্তি কীভাবে যোগাযোগ পছন্দ করেন তা নিরাপদ কেস সিস্টেমে রেকর্ড করুন।",
        "p1_missed_checkins": "মিসড পরিকল্পিত চেক-ইন",
        "p1_missed_checkins_help": "শুধুমাত্র সম্মত চেক-ইন গণনা করুন যার কোনো সাড়া আসেনি।",
        # [REVIEW: CONSENT/SAFETY]
        "p1_consent_checkbox": "আমি নিশ্চিত করছি যে ব্যক্তি এই কথোপকথন রেকর্ড ও বিশ্লেষণের অনুমতি দিয়েছেন এবং তিনি যেকোনো সময় থামতে পারেন।",
        # [REVIEW: COSMETIC]
        "p1_tab_text": "📄 নোট বা লিখিত রেকর্ড",
        "p1_tab_audio": "🎙️ অডিও রেকর্ডিং",
        "p1_notes_placeholder": "শুধুমাত্র ব্যক্তি যা শেয়ার করতে বেছে নিয়েছেন তা রেকর্ড করুন।",
        "p1_notes_label": "সংক্ষিপ্ত, প্রাসঙ্গিক কথোপকথনের নোট",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_info": "অডিও ট্রান্সক্রিপশন ঐচ্ছিক। ভয়েস বিশ্লেষণ পরীক্ষামূলক এবং ডিফল্টরূপে বন্ধ — এটি কিছু নির্ণয় করে না।",
        "p1_audio_consent": "আমি নিশ্চিত করছি যে ব্যক্তি তাদের অডিও ট্রান্সক্রাইব করার জন্য নির্দিষ্ট অনুমতি দিয়েছেন।",
        # [REVIEW: COSMETIC]
        "p1_audio_method": "রেকর্ডিং পদ্ধতি",
        "p1_record_now": "এখনই রেকর্ড করুন",
        "p1_upload_file": "ফাইল আপলোড করুন",
        "p1_audio_input_label": "কথোপকথন রেকর্ড করুন",
        "p1_upload_label": "সম্মত রেকর্ডিং আপলোড করুন",
        "p1_audio_discard_caption": "এই প্রোটোটাইপে রো অডিও সংরক্ষিত হয় না।",
        "p1_audio_quality": "রেকর্ডিং মান",
        "p1_audio_limitations": "রেকর্ডিং বা ডিভাইস সীমাবদ্ধতা",
        "p1_audio_limitations_help": "শুধুমাত্র পরিচিত রেকর্ডিং সীমাবদ্ধতা নির্বাচন করুন।",
        "p1_audio_analysis_opt_in": "এই রেকর্ডিংয়ের জন্য ঐচ্ছিক পরীক্ষামূলক ভয়েস বিশ্লেষণ চালু করুন",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_analysis_consent": "আমি নিশ্চিত করছি যে এই ঐচ্ছিক ভয়েস বিশ্লেষণের জন্য আলাদা অনুমতি রেকর্ড করা হয়েছে।",
        # [REVIEW: COSMETIC]
        "p1_audio_uncertainty": "ভয়েস বিশ্লেষণ মডেল কতটা আত্মবিশ্বাসী?",
        "p1_audio_uncertainty_help": "সতর্কতার সাথে মান বেছে নিন।",
        "p1_transcribe_button": "রেকর্ডিং ট্রান্সক্রাইব করুন",
        "p1_transcribe_spinner": "সম্মত রেকর্ডিং ট্রান্সক্রাইব হচ্ছে...",
        "p1_transcript_review_label": "চালিয়ে যাওয়ার আগে টেক্সট পরীক্ষা করুন",
        "p1_save_button": "সংরক্ষণ করুন এবং কর্মীর পর্যালোচনার জন্য প্রস্তুত করুন",
        # [REVIEW: CONSENT/SAFETY]
        "p1_no_consent_info": "রেকর্ড প্রস্তুত করার আগে অনুমতি নিশ্চিত করুন।",
        # [REVIEW: COSMETIC]
        "p1_analysis_spinner": "কর্মীর পর্যালোচনার জন্য তথ্য সাজানো হচ্ছে...",
        "p2_heading": "📈 মামলার ইতিহাস",
        "p2_subheading": "দেখুন সময়ের সাথে ফলো-আপ অগ্রাধিকার কীভাবে পরিবর্তিত হয়েছে।",
        "p2_caption": "উচ্চ ফলো-আপ অগ্রাধিকার স্কোর মানে কর্মীকে শীঘ্রই চেক করতে হতে পারে।",
        "p2_case_reference": "মামলার রেফারেন্স নম্বর",
        "p2_no_cases": "এখনো কোনো মামলা পাওয়া যায়নি। প্রথমে একটি কথোপকথন রেকর্ড করুন।",
        "p2_load_error": "মামলার ইতিহাস লোড করা যায়নি",
        "p3_heading": "👥 কর্মীর পর্যালোচনার জন্য অপেক্ষারত মামলা",
        "p3_subheading": "কাউকে যোগাযোগ করা, রেফার করা বা রেকর্ড পরিবর্তন করার আগে প্রশিক্ষিত কর্মীকে এই মামলাগুলি দেখতে হবে।",
        # [REVIEW: CONSENT/SAFETY]
        "p3_warning": "পর্যালোচনা কার্য রোগ নির্ণয়, সত্যতার বিচার বা বিপদের প্রমাণ নয়।",
        # [REVIEW: COSMETIC]
        "p3_waiting": "পর্যালোচনার জন্য অপেক্ষারত",
        "p3_urgent": "জরুরি",
        "p3_priority": "অগ্রাধিকার",
        "p3_done": "পর্যালোচনা সম্পন্ন",
        "p3_load_error": "পর্যালোচনার তালিকা লোড করা যায়নি",
        "p4_heading": "🗺️ সংক্ষিপ্ত বিবরণ",
        "p4_subheading": "এলাকাজুড়ে মামলার সংখ্যা এবং জরুরিতার সারসংক্ষেপ।",
        "p4_caption": "শুধুমাত্র রাজ্য এবং জাতীয় ভূমিকার জন্য উপলব্ধ।",
        "p4_cases_followed": "অনুসরণ করা মামলা",
        "p4_scope": "ড্যাশবোর্ড পরিধি",
        "p4_privacy_threshold": "গোপনীয়তার জন্য ন্যূনতম গ্রুপ আকার",
        "p4_by_state": "রাজ্য অনুযায়ী মামলা",
        "p4_urgency": "বর্তমান মামলা কতটা জরুরি?",
        "p4_urgency_by_state": "রাজ্য অনুযায়ী জরুরিতার বিবরণ",
        "p4_download_button": "সারসংক্ষেপ রিপোর্ট ডাউনলোড করুন",
        "p4_download_json_button": "সারসংক্ষেপ রিপোর্ট ডাউনলোড করুন (JSON)",
        "p4_download_success": "সারসংক্ষেপ রিপোর্ট ডাউনলোড হয়েছে। ব্যক্তিগত মামলার বিবরণ সুরক্ষিত।",
        "p4_load_error": "সারসংক্ষেপ দৃশ্য লোড করা যায়নি",
        "p5_heading": "🚨 জরুরি সাহায্যের প্রক্রিয়া",
        "p5_subheading": "স্ব-ক্ষতি এবং বাহ্যিক হুমকির রিপোর্টের জন্য আলাদা কর্মী পর্যালোচনা পথ।",
        # [REVIEW: CONSENT/SAFETY]
        "p5_error_banner": "এই পৃষ্ঠা টেক্সট পাঠায় না, কল করে না, বাইরের সেবার সাথে তথ্য ভাগ করে না বা রেফারেল শুরু করে না।",
        # [REVIEW: COSMETIC]
        "p5_show_closed": "সমাধান করা উদ্বেগ দেখান",
        "p5_load_error": "জরুরি উদ্বেগ লোড করা যায়নি",
        "p5_no_events": "কোনো খোলা জরুরি উদ্বেগ নেই।",
        "p6_heading": "⚙️ জরুরি সাহায্যের সেটিংস",
        "p6_subheading": "দায়িত্বশীল কর্মী, সাড়া দেওয়ার সময় লক্ষ্যমাত্রা এবং যোগাযোগের নিরাপদ উপায় কনফিগার করুন।",
        # [REVIEW: CONSENT/SAFETY]
        "p6_warning": "শুধুমাত্র অনুমোদিত কর্মীদের জন্য। ব্যবহারের আগে সমস্ত সেবা এন্ট্রি যাচাই করুন।",
        # [REVIEW: COSMETIC]
        "p6_tab_response": "সাড়া দেওয়ার সময় এবং নিযুক্ত কর্মী",
        "p6_tab_spi": "ফলো-আপ অগ্রাধিকার সেটিংস",
        "p6_tab_contact": "মানুষের সাথে যোগাযোগের নিরাপদ উপায়",
        "p6_tab_services": "যাচাই করা স্থানীয় সেবা",
        "p6_access_error": "শুধুমাত্র রাজ্য বা জাতীয় প্রশাসকরা কনফিগারেশন অ্যাক্সেস করতে পারেন।",
        "p7_heading": "📋 মানক সুস্থতা যাচাই (PHQ-9 / GAD-7)",
        "p7_subheading": "রেকর্ড করা অনুমতির সাথে ঐচ্ছিক মানক যাচাই।",
        # [REVIEW: CONSENT/SAFETY]
        "p7_warning": "মোট স্কোর চিকিৎসা নির্ণয় নয় এবং কখনো স্বয়ংক্রিয় সিদ্ধান্তের জন্য ব্যবহার করা হয় না।",
        # [REVIEW: COSMETIC]
        "p7_case_reference": "মামলার রেফারেন্স নম্বর",
        "p7_which_checkin": "কোন যাচাই?",
        "p7_mood_checkin": "মেজাজ যাচাই (PHQ-9)",
        "p7_worry_checkin": "উদ্বেগ যাচাই (GAD-7)",
        "p7_instrument_help": "PHQ-9 মেজাজের জন্য মানক প্রশ্নাবলী। GAD-7 উদ্বেগের জন্য।",
        "p7_skip_caption": "ব্যক্তি যেকোনো প্রশ্ন এড়িয়ে যেতে পারেন।",
        # [REVIEW: CONSENT/SAFETY]
        "p7_consent": "আমি নিশ্চিত করছি যে ব্যক্তি এই যাচাইয়ের জন্য নির্দিষ্ট অনুমতি দিয়েছেন।",
        "p7_no_consent_info": "প্রশ্ন শুরু করার আগে উপরে অনুমতি নিশ্চিত করুন।",
        # [REVIEW: COSMETIC]
        "p7_question_progress": "প্রশ্ন {current} / {total}",
        "p7_skip_option": "এই প্রশ্ন এড়িয়ে যান",
        "p7_back_button": "⬅ পেছনে",
        "p7_next_button": "পরবর্তী ➡",
        "p7_finish_button": "✅ যাচাই শেষ করুন",
        "p7_save_stop_button": "💾 সংরক্ষণ করুন এবং এখানে থামুন",
        "p7_save_stop_help": "এখন পর্যন্ত উত্তর দেওয়া সংরক্ষণ করুন।",
        "p7_new_checkin_button": "নতুন যাচাই শুরু করুন",
        "p7_access_error": "প্রশ্নাবলী অ্যাক্সেস উপলব্ধ নেই",
        "p7_no_cases": "ঐচ্ছিক যাচাই রেকর্ড করার আগে একটি নতুন মামলা শুরু করুন।",
        "p8_heading": "🔐 গোপনীয়তা ও ডেটা নিয়ম",
        "p8_subheading": "ডেটা কতক্ষণ রাখা হয়, রেকর্ড মুছে ফেলা এবং কার্যকলাপ লগ।",
        # [REVIEW: CONSENT/SAFETY]
        "p8_warning": "রেকর্ড মুছে ফেললে ব্যক্তিগত বিবরণ ও নোট সরানো হয়, কিন্তু একটি মৌলিক লগ থাকে।",
        # [REVIEW: COSMETIC]
        "p8_delete_heading": "মামলা মুছে ফেলার অনুরোধ করুন",
        "p8_delete_caption": "এই অনুরোধটি একটি পৃথক রাজ্য বা জাতীয় প্রশাসককে অনুমোদন করতে হবে।",
        "p8_no_cases": "কোনো সক্রিয় মামলা উপলব্ধ নেই।",
        "p8_case_reference": "মামলার রেফারেন্স নম্বর",
        "p8_delete_reason": "কেন এই মামলাটি মুছে ফেলতে হবে",
        "p8_request_deletion": "মুছে ফেলার অনুরোধ করুন",
        "p8_tab_retention": "ডেটা কতক্ষণ রাখা হয়",
        "p8_tab_deletions": "রেকর্ড মুছে ফেলার অনুরোধ",
        "p8_retention_version": "নতুন ডেটা-রক্ষণাবেক্ষণ নীতি সংস্করণ",
        "p8_retention_days": "ডেটা রাখার মেয়াদ (দিনে)",
        "p8_retention_rationale": "অনুমোদনের কারণ",
        "p8_create_retention": "ডেটা-রক্ষণাবেক্ষণ নীতি সংস্করণ তৈরি করুন",
        "p8_approve_deletion": "মুছে ফেলা অনুমোদন করুন",
        "p8_execute_deletion": "অনুমোদিত মুছে ফেলা কার্যকর করুন",
        "p8_audit_heading": "কার্যকলাপ লগ যাচাই",
        "p8_audit_pass": "হ্যাশ-চেইন যাচাই পাস হয়েছে।",
        # [REVIEW: CONSENT/SAFETY]
        "p8_audit_fail": "হ্যাশ-চেইন যাচাই ব্যর্থ হয়েছে। নিরাপত্তা ঘটনা প্রক্রিয়ার মাধ্যমে অবিলম্বে এস্কেলেট করুন।",
        # [REVIEW: COSMETIC]
        "p8_no_role": "এই ভূমিকায় কোনো গোপনীয়তা-প্রশাসন কার্যক্রম নেই।",
        "p8_access_error": "গোপনীয়তা-প্রশাসন অ্যাক্সেস উপলব্ধ নেই",
        "p9_heading": "💬 ফলো-আপ সময়সূচি",
        "p9_subheading": "ব্যক্তির পছন্দের ভাষায় নির্দেশিত, ধাপে ধাপে যাচাই।",
        "p9_safety_first_title": "🔒 নিরাপত্তা-প্রথম ডিজাইন",
        "p10_heading": "🛡️ AI তদারকি (অ্যাডমিন)",
        "p10_subheading": "AI মডেল ব্যবহার করার আগে অনুমোদন যাচাই, ন্যায্যতা পরীক্ষা এবং সংস্করণ নিয়ন্ত্রণ।",
        "p10_tab_registry": "📦 AI সংস্করণ ও রোলব্যাক",
        "p10_tab_eval": "📊 কর্মক্ষমতা ও ন্যায্যতা যাচাই",
        "p10_tab_signoffs": "✅ বিশেষজ্ঞ স্বাক্ষর",
        "p10_tab_incidents": "🚨 সমস্যা রিপোর্ট করুন",
        "p5_what_shared": "**কী শেয়ার করা হয়েছে এবং তা কতটা নির্ভরযোগ্য**",
        "p5_no_evidence": "কোনো প্রমাণ স্ন্যাপশট উপলব্ধ নেই। কাজ করার আগে উত্স নোট পর্যালোচনা করুন।",
        "p5_safe_ways": "**এই ব্যক্তির কাছে পৌঁছানোর নিরাপদ উপায়**",
        "p5_no_safe_way": "এই ব্যক্তির সাথে যোগাযোগ করার কোনো নিরাপদ উপায় রেকর্ড করা হয়নি। তাদের সাথে যোগাযোগ করবেন না।",
        "p5_case_history": "পর্যালোচনার জন্য মামলার ইতিহাস",
        "p5_no_history": "কোনো মিথস্ক্রিয়া ইতিহাস উপলব্ধ নেই।",
        "p5_local_support": "যাচাইকৃত স্থানীয় সহায়তা ডিরেক্টরি",
        "p5_no_local_services": "কোনো যাচাইকৃত স্থানীয় পরিষেবা কনফিগার করা হয়নি। অযাচাইকৃত যোগাযোগের তথ্য প্রতিস্থাপন করবেন না।",
        "p5_internal_referral": "অভ্যন্তরীণ রেফারেল ইতিহাস",
        "p5_no_outward_channel": "শুধুমাত্র নিরাপদ অভ্যন্তরীণ সারি বৃদ্ধি স্বয়ংক্রিয়। এখানে কোনো বাহ্যিক চ্যানেল উপলব্ধ নেই।",
        "p5_accountable_role": "জবাবদিহিতামূলক ভূমিকা",
        "p5_counsellor": "কাউন্সেলর",
        "p5_district_safety_officer": "জেলা নিরাপত্তা কর্মকর্তা",
        "p5_staff_assigned": "কর্মী নিযুক্ত করা হয়েছে। কোনো আউটরিচ পাঠানো হয়নি।",
        "p5_reviewer_attestation": "আমি নিযুক্ত পর্যালোচক এবং আমি প্রমাণ, সীমাবদ্ধতা, সম্মতি এবং নিরাপদ-যোগাযোগ প্রোটোকল পর্যালোচনা করেছি।",
        "p5_confirm_attestation": "প্রথমে স্বীকৃতি প্রত্যয়ন নিশ্চিত করুন।",
        "p5_ack_recorded": "স্বীকৃতি রেকর্ড করা হয়েছে। কোনো স্বয়ংক্রিয় আউটরিচ করা হয়নি।",
        "p5_contact_log": "**নিরাপদ-যোগাযোগ প্রচেষ্টা লগ**",
        "p5_no_contact_attempt": "কোনো যোগাযোগ প্রচেষ্টা লগ করা হয়নি।",
        "p5_record_attempt": "একটি মানব-সম্পাদিত নিরাপদ-যোগাযোগ প্রচেষ্টা রেকর্ড করুন",
        "p5_approved_channel": "অনুমোদিত নিরাপদ চ্যানেল",
        "p5_outcome": "ফলাফল",
        "p5_reached": "পৌঁছেছে",
        "p5_not_reached": "পৌঁছায়নি",
        "p5_attempt_logged": "প্রচেষ্টা লগ করা হয়েছে। এই সিস্টেমটি যোগাযোগ শুরু করেনি।",
        "p5_mark_resolved": "সমাধান করা হয়েছে হিসাবে চিহ্নিত করুন",
        "p5_event_closed": "একটি নিরীক্ষণযোগ্য মানব ফলাফলের সাথে সংকট ইভেন্টটি বন্ধ করা হয়েছে।",
        "p9_begin_new": "একটি নতুন চেক-ইন শুরু করুন",
        "p9_select_case_channel": "একটি মামলা, চ্যানেল এবং ভাষা নির্বাচন করুন। সম্মতি এবং নিরাপত্তা পছন্দ প্রথমে সংগ্রহ করা হয়।",
        "p9_no_active_cases": "কোনো সক্রিয় মামলা নেই। প্রথমে রেকর্ড সম্মতিযুক্ত মিথস্ক্রিয়া পৃষ্ঠার মাধ্যমে একটি মামলা তৈরি করুন।",
        "p9_select_case": "মামলা নির্বাচন করুন",
        "p9_preferred_language": "পছন্দের ভাষা",
        "p9_btn_begin_checkin": "✅ চেক-ইন শুরু করুন",
        "p9_consent_required": "চেক-ইন শুরু করার জন্য সম্মতি প্রয়োজন। সারভাইভার যেকোনো সময় প্রত্যাখ্যান করতে পারেন।",
        "p9_continue_checkin": "একটি চেক-ইন চালিয়ে যান",
        "p9_no_open_sessions": "কোনো খোলা চেক-ইন সেশন নেই। প্রথম ট্যাবে একটি নতুন চেক-ইন শুরু করুন।",
        "p9_select_session": "সেশন নির্বাচন করুন",
        "p9_how_to_deliver": "📡 কীভাবে এই চেক-ইন বিতরণ করবেন",
        "p9_ivrs_instructions": "🔊 পুনরাবৃত্তি করতে **7** টিপুন • একজন প্রশিক্ষিত ব্যক্তির জন্য **0** • বিরতি দিতে **8** • থামাতে **9**",
        "p9_submit": "জমা দিন",
        "p9_finish_checkin": "✅ এই চেক-ইন শেষ করুন",
        "p9_checkin_complete": "চেক-ইন সম্পূর্ণ হিসাবে চিহ্নিত করা হয়েছে।",
        "p9_answers_recorded": "📜 এ পর্যন্ত রেকর্ড করা উত্তর",
        "p9_no_responses": "এখনো কোনো প্রতিক্রিয়া রেকর্ড করা হয়নি।",
        "p9_language_status": "ভাষা সমর্থন স্থিতি",
        "p9_language_status_help": "প্রতিটি ভাষা স্বাধীনভাবে মূল্যায়ন করা হয়। কোনো ভাষাকে অন্যটির সাথে স্ক্রিপ্ট বা মডেল শেয়ার করার কারণে যাচাই করা হয়েছে বলে বিবেচনা করা হয় না।",
    },

    # =======================================================================
    # TAMIL (தமிழ்)
    # LLM-generated; cached statically.
    # [REVIEW: CONSENT/SAFETY] items require bilingual clinician review.
    # =======================================================================
    "ta": {
        # [REVIEW: COSMETIC]
        "app_title": "🧭 NHAA ஆதரவு அமைப்பு",
        "app_subtitle": "நாம் சேவை செய்யும் மக்களை ஆதரிக்க பணியாளர்களுக்கு உதவுகிறது",
        "language_label": "🌐 மொழி",
        "language_help": "பேசப்படும் அல்லது எழுதப்படும் மொழியைத் தேர்ந்தெடுக்கவும்",
        "privacy_expander": "🔒 தனியுரிமை மற்றும் பாதுகாப்பு தகவல்",
        "logged_in_as": "உள்நுழைந்துள்ளார்",
        "p1_heading": "📝 புதிய உரையாடலை பதிவு செய்யுங்கள்",
        "p1_subheading": "இது பணியாளர்களுக்கு ஒருவருக்கு என்ன ஆதரவு தேவை என்பதை புரிந்துகொள்ள உதவுகிறது — இது ஒருபோதும் நோயறிதல் அல்ல.",
        # [REVIEW: CONSENT/SAFETY]
        "p1_warning": (
            "நபர் பகிர்ந்துகொள்ள ஒப்புக்கொண்ட தகவலை மட்டுமே பதிவு செய்யுங்கள். "
            "பெயர்கள், தொலைபேசி எண்கள், முகவரிகள் அல்லது பிற தனிப்பட்ட விவரங்களை இங்கே தட்டச்சு செய்யாதீர்கள்."
        ),
        # [REVIEW: COSMETIC]
        "p1_case_selection": "வழக்கு தேர்வு",
        "p1_choose_existing": "தற்போதுள்ள வழக்கை தேர்ந்தெடுக்கவும்",
        "p1_start_new": "புதிய வழக்கை தொடங்கவும்",
        "p1_case_reference": "வழக்கு குறிப்பு எண்",
        "p1_state": "மாநிலம்",
        "p1_district": "மாவட்டம்",
        "p1_new_case_caption": "புதிய வழக்கு குறிப்பு எண் தானாகவே உருவாக்கப்படும்.",
        "p1_channel_label": "இந்த உரையாடல் எப்படி நடந்தது?",
        "p1_channel_caption": "நபர் எப்படி தொடர்பு கொள்ள விரும்புகிறார் என்பதை பாதுகாப்பான வழக்கு அமைப்பில் பதிவு செய்யுங்கள்.",
        "p1_missed_checkins": "தவறவிட்ட திட்டமிட்ட சரிபார்ப்புகள்",
        "p1_missed_checkins_help": "எந்த சரிபார்ப்புக்கும் பதில் இல்லை என்பதை மட்டுமே கணக்கிடுங்கள்.",
        # [REVIEW: CONSENT/SAFETY]
        "p1_consent_checkbox": "இந்த உரையாடலை பதிவு செய்து பகுப்பாய்வு செய்வதற்கு நபர் அனுமதி அளித்துள்ளார் என்பதை உறுதிப்படுத்துகிறேன்.",
        # [REVIEW: COSMETIC]
        "p1_tab_text": "📄 குறிப்புகள் அல்லது எழுத்துப் பதிவு",
        "p1_tab_audio": "🎙️ ஒலிப் பதிவு",
        "p1_notes_placeholder": "நபர் பகிர்ந்துகொள்ள தேர்ந்தெடுத்ததை மட்டுமே பதிவு செய்யுங்கள்.",
        "p1_notes_label": "சுருக்கமான, தொடர்புடைய உரையாடல் குறிப்புகள்",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_info": "ஒலி படியெடுத்தல் விருப்பமானது. குரல் பகுப்பாய்வு சோதனை நிலையில் உள்ளது மற்றும் இயல்பாக முடக்கப்பட்டுள்ளது.",
        "p1_audio_consent": "அவரது ஒலியை படியெடுக்க நபர் குறிப்பிட்ட அனுமதி அளித்துள்ளார் என்பதை உறுதிப்படுத்துகிறேன்.",
        # [REVIEW: COSMETIC]
        "p1_audio_method": "பதிவு முறை",
        "p1_record_now": "இப்போது பதிவு செய்யுங்கள்",
        "p1_upload_file": "கோப்பை பதிவேற்றுங்கள்",
        "p1_audio_input_label": "உரையாடலை பதிவு செய்யுங்கள்",
        "p1_upload_label": "ஒப்புதல் பதிவை பதிவேற்றுங்கள்",
        "p1_audio_discard_caption": "இந்த முன்மாதிரியில் மூல ஒலி சேமிக்கப்படவில்லை.",
        "p1_audio_quality": "பதிவு தரம்",
        "p1_audio_limitations": "பதிவு அல்லது சாதன வரம்புகள்",
        "p1_audio_limitations_help": "அறிந்த பதிவு வரம்புகளை மட்டுமே தேர்ந்தெடுங்கள்.",
        "p1_audio_analysis_opt_in": "இந்த பதிவிற்கு விருப்பமான சோதனை குரல் பகுப்பாய்வை இயக்குங்கள்",
        # [REVIEW: CONSENT/SAFETY]
        "p1_audio_analysis_consent": "இந்த விருப்ப குரல் பகுப்பாய்விற்காக தனியாக அனுமதி பதிவு செய்யப்பட்டுள்ளது என்பதை உறுதிப்படுத்துகிறேன்.",
        # [REVIEW: COSMETIC]
        "p1_audio_uncertainty": "குரல் பகுப்பாய்வு மாதிரி எவ்வளவு நம்பிக்கையாக உள்ளது?",
        "p1_audio_uncertainty_help": "எச்சரிக்கையான மதிப்பை தேர்ந்தெடுங்கள்.",
        "p1_transcribe_button": "பதிவை படியெடுக்கவும்",
        "p1_transcribe_spinner": "ஒப்புதல் பதிவை படியெடுக்கிறது...",
        "p1_transcript_review_label": "தொடர்வதற்கு முன் உரையை சரிபாருங்கள்",
        "p1_save_button": "சேமிக்கவும் மற்றும் பணியாளர் மதிப்பாய்விற்கு தயாரிக்கவும்",
        # [REVIEW: CONSENT/SAFETY]
        "p1_no_consent_info": "பதிவை தயாரிக்கும் முன் அனுமதியை உறுதிப்படுத்துங்கள்.",
        # [REVIEW: COSMETIC]
        "p1_analysis_spinner": "பணியாளர் மதிப்பாய்விற்கு தகவலை ஒழுங்கமைக்கிறது...",
        "p2_heading": "📈 வழக்கு வரலாறு",
        "p2_subheading": "காலப்போக்கில் தொடர்-முன்னுரிமை எவ்வாறு மாறியது என்பதைப் பாருங்கள்.",
        "p2_caption": "அதிக தொடர்-முன்னுரிமை மதிப்பெண் என்பது பணியாளர் விரைவில் சரிபார்க்க வேண்டும் என்று அர்த்தம்.",
        "p2_case_reference": "வழக்கு குறிப்பு எண்",
        "p2_no_cases": "இன்னும் வழக்குகள் எதுவும் இல்லை. முதலில் உரையாடலை பதிவு செய்யுங்கள்.",
        "p2_load_error": "வழக்கு வரலாற்றை ஏற்ற முடியவில்லை",
        "p3_heading": "👥 பணியாளர் மதிப்பாய்விற்காக காத்திருக்கும் வழக்குகள்",
        "p3_subheading": "யாரையாவது தொடர்பு கொள்வதற்கு அல்லது பரிந்துரைக்கும் முன் பயிற்சி பெற்ற பணியாளர் இந்த வழக்குகளை பார்க்க வேண்டும்.",
        # [REVIEW: CONSENT/SAFETY]
        "p3_warning": "மதிப்பாய்வு பணி நோயறிதல் அல்ல, உண்மை-பொய் தீர்ப்பு அல்ல, ஆபத்தின் சான்று அல்ல.",
        # [REVIEW: COSMETIC]
        "p3_waiting": "மதிப்பாய்விற்காக காத்திருக்கிறது",
        "p3_urgent": "அவசரம்",
        "p3_priority": "முன்னுரிமை",
        "p3_done": "மதிப்பாய்வுகள் முடிந்தன",
        "p3_load_error": "மதிப்பாய்வு பட்டியலை ஏற்ற முடியவில்லை",
        "p4_heading": "🗺️ கண்ணோட்டம்",
        "p4_subheading": "பகுதிகளில் வழக்குகளின் எண்ணிக்கை மற்றும் அவசரத்தன்மையின் சுருக்கம்.",
        "p4_caption": "மாநில மற்றும் தேசிய பாத்திரங்களுக்கு மட்டுமே கிடைக்கும்.",
        "p4_cases_followed": "கண்காணிக்கப்படும் வழக்குகள்",
        "p4_scope": "டாஷ்போர்டு நோக்கம்",
        "p4_privacy_threshold": "தனியுரிமைக்கான குறைந்தபட்ச குழு அளவு",
        "p4_by_state": "மாநிலம் வாரியாக வழக்குகள்",
        "p4_urgency": "தற்போதைய வழக்குகள் எவ்வளவு அவசரமானவை?",
        "p4_urgency_by_state": "மாநிலம் வாரியாக அவசரத்தன்மை விவரம்",
        "p4_download_button": "சுருக்க அறிக்கையை பதிவிறக்கவும்",
        "p4_download_json_button": "சுருக்க அறிக்கையை பதிவிறக்கவும் (JSON)",
        "p4_download_success": "சுருக்க அறிக்கை பதிவிறக்கப்பட்டது. தனிப்பட்ட வழக்கு விவரங்கள் பாதுகாக்கப்பட்டுள்ளன.",
        "p4_load_error": "சுருக்க பார்வையை ஏற்ற முடியவில்லை",
        "p5_heading": "🚨 அவசர உதவி செயல்முறை",
        "p5_subheading": "சுய-தீங்கு மற்றும் வெளிப்புற அச்சுறுத்தல் அறிக்கைகளுக்கு தனித்தனி பணியாளர் மதிப்பாய்வு பாதைகள்.",
        # [REVIEW: CONSENT/SAFETY]
        "p5_error_banner": "இந்த பக்கம் குறுஞ்செய்திகள் அனுப்பாது, அழைக்காது, வெளிப்புற சேவைகளுடன் தகவல் பகிரவில்லை.",
        # [REVIEW: COSMETIC]
        "p5_show_closed": "தீர்க்கப்பட்ட கவலைகளை காண்பி",
        "p5_load_error": "அவசர கவலைகளை ஏற்ற முடியவில்லை",
        "p5_no_events": "திறந்த அவசர கவலைகள் எதுவும் இல்லை.",
        "p6_heading": "⚙️ அவசர உதவி அமைப்புகள்",
        "p6_subheading": "பொறுப்பான பணியாளர், பதில் நேர இலக்குகள் மற்றும் தொடர்பு கொள்வதற்கான பாதுகாப்பான வழிகளை உள்ளமைக்கவும்.",
        # [REVIEW: CONSENT/SAFETY]
        "p6_warning": "அங்கீகரிக்கப்பட்ட பணியாளர்களுக்கு மட்டுமே. பயன்படுத்துவதற்கு முன் அனைத்து சேவை உள்ளீடுகளையும் சரிபாருங்கள்.",
        # [REVIEW: COSMETIC]
        "p6_tab_response": "பதில் நேரங்கள் மற்றும் நியமிக்கப்பட்ட பணியாளர்",
        "p6_tab_spi": "தொடர்-முன்னுரிமை அமைப்புகள்",
        "p6_tab_contact": "மக்களை தொடர்பு கொள்வதற்கான பாதுகாப்பான வழிகள்",
        "p6_tab_services": "சரிபார்க்கப்பட்ட உள்ளூர் சேவைகள்",
        "p6_access_error": "மாநில அல்லது தேசிய நிர்வாகிகள் மட்டுமே உள்ளமைவை அணுகலாம்.",
        "p7_heading": "📋 நிலையான நலன்-சரிபார்ப்பு (PHQ-9 / GAD-7)",
        "p7_subheading": "பதிவு செய்யப்பட்ட அனுமதியுடன் விருப்பமான நிலையான சரிபார்ப்பு.",
        # [REVIEW: CONSENT/SAFETY]
        "p7_warning": "மொத்த மதிப்பெண் மருத்துவ நோயறிதல் அல்ல மற்றும் தானியங்கி முடிவுக்கு பயன்படுத்தப்படவில்லை.",
        # [REVIEW: COSMETIC]
        "p7_case_reference": "வழக்கு குறிப்பு எண்",
        "p7_which_checkin": "எந்த சரிபார்ப்பு?",
        "p7_mood_checkin": "மனநிலை சரிபார்ப்பு (PHQ-9)",
        "p7_worry_checkin": "கவலை சரிபார்ப்பு (GAD-7)",
        "p7_instrument_help": "PHQ-9 மனநிலைக்கான நிலையான கேள்வித்தாள். GAD-7 கவலைக்கான.",
        "p7_skip_caption": "நபர் எந்த கேள்வியையும் தவிர்க்கலாம்.",
        # [REVIEW: CONSENT/SAFETY]
        "p7_consent": "இந்த சரிபார்ப்பிற்காக நபர் குறிப்பிட்ட அனுமதி அளித்துள்ளார் என்பதை உறுதிப்படுத்துகிறேன்.",
        "p7_no_consent_info": "கேள்விகளை தொடங்குவதற்கு முன் மேலே அனுமதியை உறுதிப்படுத்துங்கள்.",
        # [REVIEW: COSMETIC]
        "p7_question_progress": "கேள்வி {current} / {total}",
        "p7_skip_option": "இந்த கேள்வியை தவிர்க்கவும்",
        "p7_back_button": "⬅ திரும்பு",
        "p7_next_button": "அடுத்து ➡",
        "p7_finish_button": "✅ சரிபார்ப்பை முடிக்கவும்",
        "p7_save_stop_button": "💾 சேமித்து இங்கே நிறுத்துங்கள்",
        "p7_save_stop_help": "இதுவரை பதிலளித்ததை சேமிக்கவும்.",
        "p7_new_checkin_button": "புதிய சரிபார்ப்பை தொடங்கவும்",
        "p7_access_error": "கேள்வித்தாள் அணுகல் கிடைக்கவில்லை",
        "p7_no_cases": "விருப்பமான சரிபார்ப்பை பதிவு செய்வதற்கு முன் புதிய வழக்கை தொடங்குங்கள்.",
        "p8_heading": "🔐 தனியுரிமை மற்றும் தரவு விதிகள்",
        "p8_subheading": "தரவை எவ்வளவு காலம் வைத்திருப்பது, பதிவுகளை நீக்குவது மற்றும் செயல்பாட்டு பதிவுகள்.",
        # [REVIEW: CONSENT/SAFETY]
        "p8_warning": "பதிவை நீக்கினால் தனிப்பட்ட விவரங்கள் மற்றும் குறிப்புகள் அகற்றப்படும், ஆனால் அடிப்படை பதிவு இருக்கும்.",
        # [REVIEW: COSMETIC]
        "p8_delete_heading": "வழக்கை நீக்க கோருங்கள்",
        "p8_delete_caption": "இந்த கோரிக்கையை தனி மாநில அல்லது தேசிய நிர்வாகி அங்கீகரிக்க வேண்டும்.",
        "p8_no_cases": "நோக்கத்தில் உள்ள சுறுசுறுப்பான வழக்குகள் எதுவும் இல்லை.",
        "p8_case_reference": "வழக்கு குறிப்பு எண்",
        "p8_delete_reason": "இந்த வழக்கை ஏன் நீக்க வேண்டும்",
        "p8_request_deletion": "நீக்கும் கோரிக்கை செய்யுங்கள்",
        "p8_tab_retention": "தரவை எவ்வளவு காலம் வைத்திருக்கிறோம்",
        "p8_tab_deletions": "பதிவு நீக்கும் கோரிக்கைகள்",
        "p8_retention_version": "புதிய தரவு-பாதுகாப்பு கொள்கை பதிப்பு",
        "p8_retention_days": "தரவு வைத்திருக்கும் காலம் (நாட்களில்)",
        "p8_retention_rationale": "அங்கீகாரத்தின் காரணம்",
        "p8_create_retention": "தரவு-பாதுகாப்பு கொள்கை பதிப்பை உருவாக்குங்கள்",
        "p8_approve_deletion": "நீக்குதலை அங்கீகரிக்கவும்",
        "p8_execute_deletion": "அங்கீகரிக்கப்பட்ட நீக்குதலை செயல்படுத்துங்கள்",
        "p8_audit_heading": "செயல்பாட்டு பதிவு சரிபார்ப்பு",
        "p8_audit_pass": "ஹாஷ்-சங்கிலி சரிபார்ப்பு நிறைவேறியது.",
        # [REVIEW: CONSENT/SAFETY]
        "p8_audit_fail": "ஹாஷ்-சங்கிலி சரிபார்ப்பு தோல்வியடைந்தது. உடனே பாதுகாப்பு சம்பவ செயல்முறையில் அறிவிக்கவும்.",
        # [REVIEW: COSMETIC]
        "p8_no_role": "இந்த பாத்திரத்தில் தனியுரிமை-நிர்வாக செயல்பாடுகள் எதுவும் இல்லை.",
        "p8_access_error": "தனியுரிமை-நிர்வாக அணுகல் கிடைக்கவில்லை",
        "p9_heading": "💬 தொடர்-கால அட்டவணை",
        "p9_subheading": "நபரின் விரும்பிய மொழி மற்றும் சேனலில் வழிகாட்டப்பட்ட, படிப்படியான சரிபார்ப்புகள்.",
        "p9_safety_first_title": "🔒 பாதுகாப்பு-முதல் வடிவமைப்பு",
        "p10_heading": "🛡️ AI மேற்பார்வை (நிர்வாகி)",
        "p10_subheading": "AI மாதிரிகளை பயன்படுத்துவதற்கு முன் அங்கீகார சரிபார்ப்புகள், நேர்மை சோதனைகள் மற்றும் பதிப்பு கட்டுப்பாடுகள்.",
        "p10_tab_registry": "📦 AI பதிப்புகள் மற்றும் ரோல்பேக்",
        "p10_tab_eval": "📊 செயல்திறன் மற்றும் நேர்மை சரிபார்ப்புகள்",
        "p10_tab_signoffs": "✅ நிபுணர் கையொப்பங்கள்",
        "p10_tab_incidents": "🚨 சிக்கலை தெரிவியுங்கள்",
        "p5_what_shared": "**என்ன பகிரப்பட்டது மற்றும் அது எவ்வளவு நம்பகமானது**",
        "p5_no_evidence": "ஆதார ஸ்னாப்ஷாட் கிடைக்கவில்லை. செயல்படுவதற்கு முன் மூல குறிப்புகளை மதிப்பாய்வு செய்யவும்.",
        "p5_safe_ways": "**இந்த நபரை அடைய பாதுகாப்பான வழிகள்**",
        "p5_no_safe_way": "இந்த நபரை தொடர்புகொள்ள பாதுகாப்பான வழி எதுவும் பதிவு செய்யப்படவில்லை. அவர்களை தொடர்புகொள்ள வேண்டாம்.",
        "p5_case_history": "மதிப்பாய்வுக்கான வழக்கு வரலாறு",
        "p5_no_history": "எந்த உரையாடல் வரலாறும் கிடைக்கவில்லை.",
        "p5_local_support": "சரிபார்க்கப்பட்ட உள்ளூர் ஆதரவு கோப்பகம்",
        "p5_no_local_services": "எந்த சரிபார்க்கப்பட்ட உள்ளூர் சேவைகளும் கட்டமைக்கப்படவில்லை. சரிபார்க்கப்படாத தொடர்பு தகவலை மாற்ற வேண்டாம்.",
        "p5_internal_referral": "உள்ளக பரிந்துரை வரலாறு",
        "p5_no_outward_channel": "பாதுகாப்பான உள்ளக வரிசை விரிவாக்கம் மட்டுமே தானியங்கி செய்யப்பட்டுள்ளது. இங்கு எந்த வெளிப்படையான சேனலும் கிடைக்கவில்லை.",
        "p5_accountable_role": "பொறுப்பான பாத்திரம்",
        "p5_counsellor": "ஆலோசகர்",
        "p5_district_safety_officer": "மாவட்ட பாதுகாப்பு அதிகாரி",
        "p5_staff_assigned": "பணியாளர் நியமிக்கப்பட்டுள்ளார். எந்த அவுட்ரீச்சும் அனுப்பப்படவில்லை.",
        "p5_reviewer_attestation": "நான் நியமிக்கப்பட்ட மதிப்பாய்வாளர், ஆதாரம், வரம்புகள், ஒப்புதல் மற்றும் பாதுகாப்பான தொடர்பு நெறிமுறைகளை மதிப்பாய்வு செய்துள்ளேன்.",
        "p5_confirm_attestation": "முதலில் ஒப்புகை சான்றளிப்பை உறுதிப்படுத்தவும்.",
        "p5_ack_recorded": "ஒப்புகை பதிவு செய்யப்பட்டது. எந்த தானியங்கி அவுட்ரீச்சும் செய்யப்படவில்லை.",
        "p5_contact_log": "**பாதுகாப்பான தொடர்பு முயற்சி பதிவு**",
        "p5_no_contact_attempt": "எந்த தொடர்பு முயற்சியும் பதிவு செய்யப்படவில்லை.",
        "p5_record_attempt": "மனிதரால் செய்யப்பட்ட பாதுகாப்பான தொடர்பு முயற்சியை பதிவு செய்யவும்",
        "p5_approved_channel": "அங்கீகரிக்கப்பட்ட பாதுகாப்பான சேனல்",
        "p5_outcome": "முடிவு",
        "p5_reached": "அடையப்பட்டது",
        "p5_not_reached": "அடையவில்லை",
        "p5_attempt_logged": "முயற்சி பதிவு செய்யப்பட்டது. இந்த அமைப்பு தொடர்பை தொடங்கவில்லை.",
        "p5_mark_resolved": "தீர்க்கப்பட்டதாகக் குறிக்கவும்",
        "p5_event_closed": "தணிக்கை செய்யக்கூடிய மனித முடிவுடன் நெருக்கடி நிகழ்வு மூடப்பட்டது.",
        "p9_begin_new": "புதிய சரிபார்ப்பை தொடங்கவும்",
        "p9_select_case_channel": "வழக்கு, சேனல் மற்றும் மொழியைத் தேர்ந்தெடுக்கவும். ஒப்புதல் மற்றும் பாதுகாப்பு விருப்பத்தேர்வுகள் முதலில் சேகரிக்கப்படும்.",
        "p9_no_active_cases": "செயலில் உள்ள வழக்குகள் இல்லை. பதிவு ஒப்புதல் உரையாடல் பக்கம் மூலம் முதலில் வழக்கை உருவாக்கவும்.",
        "p9_select_case": "வழக்கை தேர்ந்தெடுக்கவும்",
        "p9_preferred_language": "விருப்பமான மொழி",
        "p9_btn_begin_checkin": "✅ சரிபார்ப்பை தொடங்கவும்",
        "p9_consent_required": "சரிபார்ப்பை தொடங்க ஒப்புதல் தேவை. தப்பியவர் எந்த நேரத்திலும் மறுக்கலாம்.",
        "p9_continue_checkin": "சரிபார்ப்பை தொடரவும்",
        "p9_no_open_sessions": "திறந்த சரிபார்ப்பு அமர்வுகள் இல்லை. முதல் தாவலில் புதிய சரிபார்ப்பை தொடங்கவும்.",
        "p9_select_session": "அமர்வை தேர்ந்தெடுக்கவும்",
        "p9_how_to_deliver": "📡 இந்த சரிபார்ப்பை எப்படி வழங்குவது",
        "p9_ivrs_instructions": "🔊 மீண்டும் கேட்க **7** ஐ அழுத்தவும் • பயிற்சி பெற்ற நபருக்கு **0** • இடைநிறுத்த **8** • நிறுத்த **9**",
        "p9_submit": "சமர்ப்பி",
        "p9_finish_checkin": "✅ இந்த சரிபார்ப்பை முடிக்கவும்",
        "p9_checkin_complete": "சரிபார்ப்பு முடிந்தது என குறிக்கப்பட்டது.",
        "p9_answers_recorded": "📜 இதுவரை பதிவு செய்யப்பட்ட பதில்கள்",
        "p9_no_responses": "இதுவரை எந்த பதிலும் பதிவு செய்யப்படவில்லை.",
        "p9_language_status": "மொழி ஆதரவு நிலை",
        "p9_language_status_help": "ஒவ்வொரு மொழியும் தனித்தனியாக மதிப்பிடப்படுகிறது. ஒரு மொழி மற்றொரு மொழியுடன் ஸ்கிரிப்ட் அல்லது மாதிரியைப் பகிர்வதால் மட்டும் சரிபார்க்கப்பட்டதாகக் கருதப்படாது.",
    },
}