"""Administer complete, consented PHQ-9 or GAD-7 questionnaires separately from SPI."""

import streamlit as st

from src.database import get_scoped_cases, insert_alert, insert_scoped_validated_screening
from src.screening import (
    RESPONSE_OPTIONS,
    SKIPPED,
    ScreeningValidationError,
    get_instrument,
    score_validated_screening,
)
from src.translations import get_questionnaire_questions, t
from src.ui_access import get_active_actor


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p7_heading")}</h1>
        <p>{t("p7_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t("p7_warning"))

try:
    actor = get_active_actor()
    case_ids = [case["case_id"] for case in get_scoped_cases(actor, purpose="screening")]
except Exception as error:
    st.error(f"{t('p7_access_error')}: {error}")
    st.stop()
if not case_ids:
    st.info(t("p7_no_cases"))
    st.stop()

case_id = st.selectbox(t("p7_case_reference"), case_ids)

# Plain-language instrument labels — clinical names always kept in brackets
INSTRUMENT_LABELS = {
    "PHQ-9": t("p7_mood_checkin"),
    "GAD-7": t("p7_worry_checkin"),
}
LABEL_TO_INSTRUMENT = {v: k for k, v in INSTRUMENT_LABELS.items()}

instrument_label = st.radio(
    t("p7_which_checkin"),
    list(INSTRUMENT_LABELS.values()),
    horizontal=True,
    help=t("p7_instrument_help"),
)
instrument_name = LABEL_TO_INSTRUMENT[instrument_label]

# Reset question progress when the instrument changes
if st.session_state.get("checkin_instrument") != instrument_name:
    st.session_state["checkin_instrument"] = instrument_name
    st.session_state["checkin_index"] = 0
    st.session_state["checkin_answers"] = {}
    st.session_state["checkin_submitted"] = False

definition = get_instrument(instrument_name)
st.caption(definition["timeframe"])
st.caption(t("p7_skip_caption"))

consent = st.checkbox(t("p7_consent"), value=False)

if not consent:
    st.info(t("p7_no_consent_info"))
    st.stop()

# ── One-question-at-a-time flow ──────────────────────────────────────────────

lang_name = st.session_state.get("selected_language", "English")
lang_code, localized_questions = get_questionnaire_questions(instrument_name, lang_name)
questions = [{"id": q_def["id"], "text": loc_text} for q_def, loc_text in zip(definition["items"], localized_questions)]
total = len(questions)

if "checkin_index" not in st.session_state:
    st.session_state["checkin_index"] = 0
if "checkin_answers" not in st.session_state:
    st.session_state["checkin_answers"] = {}
if "checkin_submitted" not in st.session_state:
    st.session_state["checkin_submitted"] = False

response_labels = [t("p7_skip_option")] + [
    f"{value} — {label}" for value, label in RESPONSE_OPTIONS.items()
]


def _submit_screening(answers_so_far):
    """Build a full responses dict (skipping unanswered), score, and save."""
    responses = {}
    for item in questions:
        raw = answers_so_far.get(item["id"], t("p7_skip_option"))
        responses[item["id"]] = SKIPPED if raw == t("p7_skip_option") else int(raw.split(" — ", 1)[0])
    try:
        screening = score_validated_screening(
            instrument=instrument_name,
            questions_administered=definition["items"],
            responses=responses,
            consent_recorded=consent,
        )
        screening_id = insert_scoped_validated_screening(actor, case_id, screening, purpose="screening")
        if screening["status"] == "complete":
            st.success(
                f"Responses saved (record {screening_id}): total {screening['total_score']}/{screening['maximum_score']}. "
                "This is a total score, not a medical diagnosis or automatic decision."
            )
        else:
            st.info(
                f"Responses saved as incomplete (record {screening_id}); no total was calculated because "
                f"{len(screening['skipped_item_ids'])} question(s) were skipped."
            )
        if screening["requires_human_review"]:
            insert_alert(
                case_id, None, "URGENT",
                "A direct response to a check-in question needs trained staff review. It does not by itself prove what the person intends or make a diagnosis.",
                "Review the exact answer, the original notes, and how they prefer to be contacted before considering next steps.",
                alert_type="VALIDATED_SCREENING_RESPONSE",
            )
            st.warning(
                "A staff review task was created for the direct response. This system did not automatically contact anyone, make a referral, or change case records."
            )
        st.caption(screening["limitation_notice"])
        st.session_state["checkin_index"] = 0
        st.session_state["checkin_answers"] = {}
        st.session_state["checkin_submitted"] = True
    except (ScreeningValidationError, ValueError) as error:
        st.error(str(error))


if st.session_state.get("checkin_submitted"):
    if st.button(t("p7_new_checkin_button")):
        st.session_state["checkin_submitted"] = False
        st.session_state["checkin_index"] = 0
        st.session_state["checkin_answers"] = {}
        st.rerun()
    st.stop()

idx = st.session_state["checkin_index"]
current_q = questions[idx]

# Progress indicator
st.caption(t("p7_question_progress").format(current=idx + 1, total=total))
st.progress((idx + 1) / total)

# Pre-select any previously saved answer for this question
previous_answer = st.session_state["checkin_answers"].get(current_q["id"], t("p7_skip_option"))
default_index = response_labels.index(previous_answer) if previous_answer in response_labels else 0

answer = st.radio(
    current_q["text"],
    options=response_labels,
    index=default_index,
    key=f"q_{instrument_name}_{current_q['id']}_{idx}",
)
# Save answer immediately on every interaction
st.session_state["checkin_answers"][current_q["id"]] = answer

st.divider()
nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 2])

with nav_col1:
    if st.button(t("p7_back_button"), disabled=(idx == 0), use_container_width=True):
        st.session_state["checkin_index"] -= 1
        st.rerun()

with nav_col2:
    if idx < total - 1:
        if st.button(t("p7_next_button"), type="primary", use_container_width=True):
            st.session_state["checkin_index"] += 1
            st.rerun()
    else:
        if st.button(t("p7_finish_button"), type="primary", use_container_width=True):
            _submit_screening(st.session_state["checkin_answers"])

with nav_col3:
    if st.button(
        t("p7_save_stop_button"),
        use_container_width=True,
        help=t("p7_save_stop_help"),
    ):
        _submit_screening(st.session_state["checkin_answers"])

