"""Record a consented interaction for non-diagnostic human review."""

import streamlit as st

from config import AUDIO_ANALYSIS_DEFAULT_ENABLED, DIMENSION_LABELS, EXPERIMENTAL_AUDIO_LIMITATION, MAX_AUDIO_DURATION_SECONDS, MAX_AUDIO_SIZE_BYTES
from src.alerts import check_and_create_review_tasks, create_crisis_workflow_events
from src.database import (
    get_active_spi_threshold_config,
    create_scoped_case,
    get_scoped_case,
    get_scoped_cases,
    get_scoped_interactions,
    insert_scoped_interaction,
    record_consent,
)
from src.translations import t
from src.groq_client import extract_support_signals, transcribe_audio, translate_to_english
from src.acoustic import build_audio_analysis_metadata, extract_acoustic_features_from_bytes, get_acoustic_feature_summary
from src.scoring import assess_spi_trend, compute_support_priority_indicator
from src.ui_access import get_active_actor


try:
    actor = get_active_actor()
except Exception as error:
    st.error(f"We could not verify your login: {error}")
    st.stop()


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p1_heading")}</h1>
        <p>{t("p1_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t("p1_warning"))

left, right = st.columns([2, 1])
with left:
    try:
        scoped_cases = get_scoped_cases(actor, purpose="case_review")
    except Exception as error:
        st.error(f"Could not load cases: {error}")
        st.stop()
    existing_cases = [case["case_id"] for case in scoped_cases]
    case_option = st.radio(
        t("p1_case_selection"), [t("p1_choose_existing"), t("p1_start_new")], horizontal=True
    )
    if case_option == t("p1_choose_existing"):
        case_id = st.selectbox(t("p1_case_reference"), options=existing_cases)
        state = district = None
    else:
        new_case_cols = st.columns(2)
        with new_case_cols[0]:
            state = st.text_input(t("p1_state"), value=actor.state or "", placeholder="e.g., Maharashtra")
        with new_case_cols[1]:
            district = st.text_input(t("p1_district"), value=actor.district or "", placeholder="e.g., Pune")
        case_id = "NEW-OPAQUE-CASE"
        st.caption(t("p1_new_case_caption"))

with right:
    channel = st.selectbox(
        t("p1_channel_label"),
        ["helpline_call", "follow_up_call", "counselling_session", "scheduled_call", "text_message"],
    )
    st.caption(t("p1_channel_caption"))
    unanswered_follow_ups = st.number_input(
        t("p1_missed_checkins"), min_value=0, max_value=20, value=0, step=1,
        help=t("p1_missed_checkins_help"),
    )

consent_recorded = st.checkbox(
    t("p1_consent_checkbox"),
    value=False,
)

st.divider()
tab_text, tab_audio = st.tabs([t("p1_tab_text"), t("p1_tab_audio")])
transcript = ""
source_is_audio = False
audio_transcription_consent = False
audio_analysis_opt_in = AUDIO_ANALYSIS_DEFAULT_ENABLED
audio_analysis_consent = False
audio_quality = "not_assessed"
audio_device_limitations = []
audio_model_uncertainty = "high"
audio_analysis_metadata = None

with tab_text:
    transcript = st.text_area(
        t("p1_notes_label"),
        height=190,
        placeholder=t("p1_notes_placeholder"),
    )

with tab_audio:
    st.info(t("p1_audio_info"))
    audio_transcription_consent = st.checkbox(
        t("p1_audio_consent"),
        value=False,
        key="audio_transcription_consent",
    )
    
    audio_input_method = st.radio(t("p1_audio_method"), [t("p1_record_now"), t("p1_upload_file")], horizontal=True)

    audio_bytes = None
    audio_filename = None
    is_live_recording = False
    
    if audio_input_method == t("p1_record_now"):
        recorded_audio = st.audio_input(t("p1_audio_input_label"), sample_rate=16000)
        if recorded_audio:
            audio_bytes = recorded_audio.getvalue()
            audio_filename = "live_recording.wav"
            is_live_recording = True
    else:
        uploaded_file = st.file_uploader(
            t("p1_upload_label"), type=["wav", "mp3", "m4a", "ogg", "flac", "webm"]
        )
        if uploaded_file:
            audio_bytes = uploaded_file.getvalue()
            audio_filename = uploaded_file.name

    if audio_bytes is not None:
        st.caption(t("p1_audio_discard_caption"))
        audio_quality = st.selectbox(
            t("p1_audio_quality"), ["not_assessed", "clear_or_usable", "limited_or_noisy", "very_limited"],
            help="A factual recording-quality label, not a statement about the person.",
        )
        audio_device_limitations = st.multiselect(
            t("p1_audio_limitations"), [
                "background_noise", "intermittent_signal", "microphone_distortion", "unknown_or_shared_device", "other_or_unknown",
            ],
            help=t("p1_audio_limitations_help"),
        )
        audio_analysis_opt_in = st.checkbox(
            t("p1_audio_analysis_opt_in"),
            value=AUDIO_ANALYSIS_DEFAULT_ENABLED,
            key="audio_analysis_opt_in",
        )
        if audio_analysis_opt_in:
            st.warning(EXPERIMENTAL_AUDIO_LIMITATION)
            audio_analysis_consent = st.checkbox(
                t("p1_audio_analysis_consent"),
                value=False,
                key="audio_analysis_consent",
            )
            audio_model_uncertainty = st.selectbox(
                t("p1_audio_uncertainty"), ["high", "medium", "low", "not_assessed"],
                help=t("p1_audio_uncertainty_help"),
            )
        if st.button(t("p1_transcribe_button"), key="transcribe_audio", disabled=not audio_transcription_consent):
            audio_size = len(audio_bytes)
            
            # Size validation
            if audio_size > MAX_AUDIO_SIZE_BYTES:
                st.error(f"Recording exceeds the maximum allowed file size of {MAX_AUDIO_SIZE_BYTES / (1024 * 1024):.0f}MB. Please provide a shorter recording.")
                st.stop()
                
            # Duration validation (live recordings are guaranteed to be WAV)
            if is_live_recording:
                duration_seconds = 0
                try:
                    import wave
                    import io
                    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
                        frames = w.getnframes()
                        rate = w.getframerate()
                        duration_seconds = frames / float(rate)
                except Exception:
                    pass
                
                if duration_seconds > MAX_AUDIO_DURATION_SECONDS:
                    st.error(f"Recording exceeds maximum duration of {MAX_AUDIO_DURATION_SECONDS} seconds (was {duration_seconds:.1f}s). Please record a shorter segment.")
                    st.stop()
                    
            with st.spinner(t("p1_transcribe_spinner")):
                transcribed = transcribe_audio(audio_bytes, audio_filename)
            if transcribed.startswith("[Transcription error"):
                st.error(transcribed)
            else:
                st.session_state["triage_transcript"] = transcribed
                st.session_state["triage_audio_source"] = True
                if audio_analysis_opt_in:
                    with st.spinner("Preparing optional experimental audio metadata..."):
                        st.session_state["triage_audio_analysis_metadata"] = extract_acoustic_features_from_bytes(
                            audio_bytes,
                            audio_filename,
                            opt_in=True,
                            transcription_consent_recorded=audio_transcription_consent,
                            consent_recorded=audio_analysis_consent,
                            audio_quality=audio_quality,
                            language=st.session_state.get("selected_language", "English"),
                            device_limitations=audio_device_limitations,
                            model_uncertainty=audio_model_uncertainty,
                        )
                    st.caption(get_acoustic_feature_summary(st.session_state["triage_audio_analysis_metadata"]))
                else:
                    st.session_state.pop("triage_audio_analysis_metadata", None)
                # Do not retain a raw in-memory copy after transcription/optional analysis.
                del audio_bytes
        if st.session_state.get("triage_transcript"):
            st.text_area(
                t("p1_transcript_review_label"),
                value=st.session_state["triage_transcript"],
                height=190,
                key="triage_transcript_review",
            )
            transcript = st.session_state["triage_transcript_review"]
            source_is_audio = st.session_state.get("triage_audio_source", False)
            audio_analysis_metadata = st.session_state.get("triage_audio_analysis_metadata")

st.divider()
if st.button(
    t("p1_save_button"),
    type="primary",
    use_container_width=True,
    disabled=not transcript.strip() or not case_id or not consent_recorded,
):
    if case_option == t("p1_start_new"):
        if not all([state, district]):
            st.error("Please fill in the State and district to start a new case.")
            st.stop()
        try:
            case_id = create_scoped_case(actor, state.strip(), district.strip(), purpose="case_review")
            st.session_state["new_case_created"] = case_id
        except (ValueError, PermissionError) as error:
            st.error(str(error))
            st.stop()
    if not get_scoped_case(actor, case_id.strip(), purpose="case_review"):
        st.error("This case was not found. Start a new case or choose an existing one.")
        st.stop()
    if source_is_audio and not audio_transcription_consent:
        st.error("The person must give specific permission for audio transcription before an audio-based record can be saved.")
        st.stop()
    if source_is_audio and audio_analysis_opt_in and not audio_analysis_consent:
        st.error("Separate permission is needed before recording optional voice analysis.")
        st.stop()

    selected_language = st.session_state.get("selected_language", "English")
    analysis_text = transcript.strip()
    translation_used = selected_language != "English"
    if translation_used:
        with st.spinner(f"Translating {selected_language} notes for analysis..."):
            analysis_text = translate_to_english(analysis_text, selected_language)

    active_spi_config = get_active_spi_threshold_config()
    prior_interactions = list(reversed(get_scoped_interactions(actor, case_id.strip(), purpose="case_review")))[:10]
    with st.spinner(t("p1_analysis_spinner")):
        support_signals = extract_support_signals(analysis_text)
    # First calculate current evidence features, then add only a quality-checked
    # trend. A raw score difference never becomes a worsening label by itself.
    baseline_assessment = compute_support_priority_indicator(
        support_signals,
        threshold_config=active_spi_config,
        unanswered_follow_up_count=unanswered_follow_ups,
    )
    current_context = {
        "support_priority_indicator": baseline_assessment["spi"],
        "confidence": baseline_assessment["confidence"],
        "channel": channel,
        "analysis_language": selected_language,
        "score_version": baseline_assessment["score_version"],
    }
    trend = assess_spi_trend(current_context, prior_interactions, active_spi_config)
    assessment = compute_support_priority_indicator(
        support_signals,
        threshold_config=active_spi_config,
        trend=trend,
        unanswered_follow_up_count=unanswered_follow_ups,
    )
    limitations = list(assessment["limitations"])
    if translation_used:
        limitations.append("Machine translation may not preserve all nuance from the original interaction.")
    if source_is_audio:
        limitations.append("This record is based on transcription; audio characteristics were not used for prioritisation or alerts.")
        if audio_analysis_metadata is None:
            audio_analysis_metadata = build_audio_analysis_metadata(
                opt_in=audio_analysis_opt_in,
                transcription_consent_recorded=audio_transcription_consent,
                consent_recorded=audio_analysis_consent,
                audio_quality=audio_quality,
                language=selected_language,
                device_limitations=audio_device_limitations,
                model_uncertainty=audio_model_uncertainty,
            )

    scores = {item["key"]: item["score"] for item in assessment["dimensions"]}
    review_required = "PENDING" if (
        assessment["spi"] >= assessment["review_thresholds"]["prompt"]
        or assessment["explicit_danger"]
        or assessment["explicit_self_harm_statement"]
    ) else "NOT_REQUIRED"
    interaction_id = insert_scoped_interaction(
        actor,
        case_id=case_id.strip(),
        purpose="case_review",
        transcript=transcript.strip(),
        channel=channel,
        support_signals=support_signals,
        support_priority_indicator=assessment["spi"],
        priority_band=assessment["priority_band"],
        confidence=assessment["confidence"],
        data_quality_limitations=limitations,
        evidence=assessment["evidence"],
        physical_safety_score=scores["physical_safety"],
        wellbeing_concern_score=scores["wellbeing"],
        service_access_score=scores["service_access"],
        consent_recorded=True,
        analysis_language=selected_language,
        human_review_status=review_required,
        unanswered_follow_up_count=assessment["unanswered_follow_up_count"],
        score_version=assessment["score_version"],
        threshold_version=assessment["threshold_version"],
        model_version=assessment["model_version"],
        feature_set=assessment["feature_set"],
        evidence_references=assessment["evidence_references"],
        trend_status=assessment["trend"]["status"],
        trend_delta=assessment["trend"]["delta"],
        trend_quality_issues=assessment["trend"].get("quality_issues", []),
        acoustic_features=(audio_analysis_metadata or {}).get("features") if source_is_audio else None,
        audio_analysis_metadata=audio_analysis_metadata,
        audio_analysis_opt_in=bool(audio_analysis_metadata and audio_analysis_metadata.get("experimental_opt_in")),
        audio_transcription_consent_recorded=bool(audio_analysis_metadata and audio_analysis_metadata.get("transcription_consent_recorded")),
        audio_analysis_consent_recorded=bool(audio_analysis_metadata and audio_analysis_metadata.get("consent_recorded")),
        audio_quality=(audio_analysis_metadata or {}).get("audio_quality"),
        audio_language=(audio_analysis_metadata or {}).get("language"),
        audio_device_limitations=(audio_analysis_metadata or {}).get("device_limitations", []),
        audio_model_uncertainty=(audio_analysis_metadata or {}).get("model_uncertainty"),
        raw_audio_retention_status=(audio_analysis_metadata or {}).get("raw_audio_retention_status", "not_retained"),
    )
    try:
        record_consent(
            actor,
            case_id.strip(),
            purpose="interaction_analysis",
            channel=channel,
            language=selected_language,
            consent_version="interaction-analysis.v1",
            contact_preferences={"source": "interaction", "audio_transcription": bool(source_is_audio)},
        )
    except (ValueError, PermissionError) as error:
        st.warning(f"Interaction saved, but the consent ledger could not be updated: {error}")
    tasks = check_and_create_review_tasks(case_id.strip(), interaction_id, assessment, support_signals)
    crisis_events = create_crisis_workflow_events(case_id.strip(), interaction_id, assessment, support_signals)

    st.divider()
    summary_col, evidence_col = st.columns([1, 2])
    with summary_col:
        st.markdown(
            f"""
            <div class="score-display" style="background: {assessment['color']}18; border: 2px solid {assessment['color']};">
                <div class="score-number" style="color: {assessment['color']};">{assessment['spi']:.0f}</div>
                <div class="score-band" style="color: {assessment['color']};">{assessment['emoji']} {assessment['priority_band']}</div>
                <div class="score-scale">Follow-up priority score • 0–100</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("This is only an estimate to help staff decide what to look at next — it is not a diagnosis, a judgement about truthfulness, or an automatic decision.")
        st.write(f"**How sure the system is:** {assessment['confidence'].title()}")
        st.caption(f"Scoring version: {assessment['score_version']} • AI version: {assessment['model_version']}")

    with evidence_col:
        st.markdown("#### Areas of concern")
        for item in assessment["dimensions"]:
            reported_items = item.get("reported_items") or ["No specific item extracted"]
            st.markdown(
                f"""
                <div class="explanation-card">
                    <div class="explanation-feature">{item['label']}: {item['score']:.0f}/100</div>
                    <div class="explanation-detail">{' • '.join(reported_items[:2])}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        contact_preferences = support_signals.get("contact_preferences", {})
        if contact_preferences.get("status") == "detected":
            language = contact_preferences.get("preferred_language") or "No language preference stated"
            constraints = contact_preferences.get("safe_contact_constraints") or []
            st.info(
                "**How the person prefers to be contacted (for staff review):** "
                f"language: {language}; preferences: {', '.join(constraints) if constraints else 'none stated'}"
            )

    st.markdown("#### Evidence and things to keep in mind")
    if assessment["evidence"]:
        for item in assessment["evidence"]:
            label = DIMENSION_LABELS.get(item["dimension"], "Information shared")
            st.write(f"- **{label}:** “{item['quote']}” ({item['confidence']} confidence)")
    else:
        st.info("No specific quote was found in the notes. Please review the original notes before relying on this estimate.")
    for limitation in limitations:
        st.caption(f"Keep in mind: {limitation}")

    st.markdown("#### Change and provenance")
    trend_label = assessment["trend"]["status"].replace("_", " ").title()
    st.write(f"**Trend assessment:** {trend_label} — {assessment['trend']['summary']}")
    if assessment["trend"].get("delta") is not None:
        st.caption(f"Comparable SPI change: {assessment['trend']['delta']:+.1f} points.")
    st.caption(
        "Based on: what the person shared about safety, threats, unmet needs, "
        "changes over time, and missed planned check-ins. "
        "Wellbeing check-in scores (PHQ-9 / GAD-7) are kept separate and never used here."
    )

    if tasks:
        st.warning("Staff review task(s) created. This system has not contacted anyone, made a referral, or changed any case records.")
        for task in tasks:
            st.write(f"- **{task['alert_level']} {task['alert_type'].replace('_', ' ').title()} review:** {task['reason']}")
    else:
        st.success("Record saved. No review task was needed from this record — but that does not mean the person is safe or has all the help they need.")
    if crisis_events:
        st.error(
            "An urgent concern was recorded and placed in the internal review queue. "
            "No text message, phone call, referral, or case change was made automatically by this system."
        )
        for event in crisis_events:
            st.write(
                f"- **{event['pathway'].replace('_', ' ').title()}** — "
                f"{event['status'].replace('_', ' ').title()}; acknowledgement due {event['acknowledgement_due_at']}"
            )
    st.caption(f"Record {interaction_id} saved for case {case_id.strip()}.")

elif not consent_recorded:
    st.info(t("p1_no_consent_info"))
