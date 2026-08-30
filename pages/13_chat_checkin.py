"""Real-time conversational check-in interface with safety routing.

This is an alternative, friendlier front-end to the same structured backend used
in the form-based flow. It uses the exact same extraction, scoring, and storage
pipeline, ensuring no divergent validation paths.
"""

import streamlit as st
from config import DIMENSION_LABELS, GROQ_CHAT_MODEL
from src.alerts import check_and_create_review_tasks, create_crisis_workflow_events
from src.database import (
    create_scoped_case,
    get_active_spi_threshold_config,
    get_scoped_case,
    get_scoped_cases,
    get_scoped_interactions,
    insert_scoped_interaction,
    record_consent,
)
from src.groq_client import _get_client, extract_support_signals, translate_to_english
from src.scoring import assess_spi_trend, compute_support_priority_indicator, project_spi_trajectory
from src.translations import t
from src.ui_access import get_active_actor

try:
    actor = get_active_actor()
except Exception as error:
    st.error(f"We could not verify your login: {error}")
    st.stop()

st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p13_heading")}</h1>
        <p>{t("p13_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t("p13_warning"))

# Left column for case selection, right column for settings
left, right = st.columns([2, 1])

with left:
    try:
        scoped_cases = get_scoped_cases(actor, purpose="case_review")
    except Exception as error:
        st.error(f"Could not load cases: {error}")
        st.stop()
    existing_cases = [case["case_id"] for case in scoped_cases]
    case_option = st.radio(
        t("p1_case_selection"), [t("p1_choose_existing"), t("p1_start_new")], horizontal=True, key="chat_case_option"
    )
    
    if case_option == t("p1_choose_existing"):
        case_id = st.selectbox(t("p1_case_reference"), options=existing_cases, key="chat_case_id")
        state = district = None
        case_type = "other"
    else:
        new_case_cols = st.columns(2)
        with new_case_cols[0]:
            state = st.text_input(t("p1_state"), value=actor.state or "", placeholder="e.g., Maharashtra", key="chat_state")
        with new_case_cols[1]:
            district = st.text_input(t("p1_district"), value=actor.district or "", placeholder="e.g., Pune", key="chat_district")
        
        case_type_options = {
            "Rape or gang rape": "rape_or_gang_rape",
            "Murder, grievous hurt, or arson": "murder_grievous_hurt_or_arson",
            "Witness intimidation or threats": "witness_intimidation_or_threats",
            "Caste based violence/family": "caste_based_violence_family",
            "Compensation/rehabilitation beneficiary": "compensation_rehabilitation_beneficiary",
            "Other": "other"
        }
        selected_type_label = st.selectbox(
            "Administrative case category", 
            list(case_type_options.keys()),
            index=5,
            help="Select the category based on the FIR/case record. Do not ask the victim this directly.",
            key="chat_case_type_label"
        )
        case_type = case_type_options[selected_type_label]
        case_id = "NEW-OPAQUE-CASE"
        st.caption(t("p1_new_case_caption"))

with right:
    # Use "chatbot" as channel to distinguish it.
    channel = "chatbot"
    unanswered_follow_ups = st.number_input(
        t("p1_missed_checkins"), min_value=0, max_value=20, value=0, step=1,
        help=t("p1_missed_checkins_help"),
        key="chat_missed_checkins"
    )

consent_recorded = st.checkbox(
    t("p13_consent_checkbox"),
    value=False,
    key="chat_consent"
)

st.divider()

if not consent_recorded:
    st.info(t("p13_no_consent_info"))
    st.stop()

# Initialize session state for chat
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = [
        {"role": "assistant", "content": t("p13_welcome_message")}
    ]
if "chat_crisis_triggered" not in st.session_state:
    st.session_state["chat_crisis_triggered"] = False
if "chat_saved" not in st.session_state:
    st.session_state["chat_saved"] = False

# Display chat messages
for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

selected_language = st.session_state.get("selected_language", "English")

def build_chatbot_prompt(messages, language):
    """Constructs the prompt for the conversational LLM."""
    system_prompt = f"""You are a warm, supportive check-in assistant for a government survivor-support programme.
Your role is to hold an open-ended check-in conversation.
Crucial instructions:
1. Respond exclusively in {language}.
2. Never diagnose a condition, give medical advice, or give legal advice.
3. Never ask leading questions about self-harm or danger in a way that could feel interrogative.
4. Never promise confidentiality that you cannot guarantee (you are part of a monitored system).
5. Invite the person to share how they are doing and follow up naturally on what they share.
6. Keep your responses concise (1-3 sentences) and conversational.
7. Wrap up the conversation naturally after a few turns or when the person indicates they are done."""
    
    formatted_msgs = [{"role": "system", "content": system_prompt}]
    formatted_msgs.extend(messages)
    return formatted_msgs

# Only show chat input if we haven't triggered a crisis hand-off or saved
if not st.session_state["chat_crisis_triggered"] and not st.session_state["chat_saved"]:
    if prompt := st.chat_input("Type your message here..."):
        # Append user message
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Compile full transcript to check for crisis
        transcript_so_far = "\\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in st.session_state["chat_messages"]])
        
        with st.spinner("Checking safety..."):
            check_text = transcript_so_far
            if selected_language != "English":
                check_text = translate_to_english(transcript_so_far, selected_language)
            
            # Use the EXACT same extraction function as the form flow
            signals = extract_support_signals(check_text)
            
            is_crisis = False
            # Check for physical safety threat
            phys_safety = signals.get("physical_safety", {})
            if phys_safety.get("status") == "detected" and phys_safety.get("explicit_threat_or_immediate_danger") is True:
                is_crisis = True
            
            # Check for self harm threat
            self_harm = signals.get("immediate_self_harm_or_suicide", {})
            if self_harm.get("status") == "detected" and self_harm.get("explicit_statement") is True:
                is_crisis = True
                
        if is_crisis:
            st.session_state["chat_crisis_triggered"] = True
            handoff_msg = t("p13_crisis_handoff")
            st.session_state["chat_messages"].append({"role": "assistant", "content": handoff_msg})
            with st.chat_message("assistant"):
                st.markdown(handoff_msg)
            st.rerun()
            
        else:
            # Generate conversational reply
            with st.chat_message("assistant"):
                with st.spinner("Typing..."):
                    client = _get_client()
                    response = client.chat.completions.create(
                        messages=build_chatbot_prompt(st.session_state["chat_messages"], selected_language),
                        model=GROQ_CHAT_MODEL,
                        temperature=0.4,
                        max_tokens=150
                    )
                    reply = response.choices[0].message.content.strip()
                    st.markdown(reply)
                    st.session_state["chat_messages"].append({"role": "assistant", "content": reply})

# The save logic
st.divider()

if st.button(t("p13_end_button"), type="primary", disabled=st.session_state["chat_saved"]):
    # 1. Prepare case
    if case_option == t("p1_start_new"):
        if not all([state, district]):
            st.error("Please fill in the State and district to start a new case.")
            st.stop()
        try:
            case_id = create_scoped_case(actor, state.strip(), district.strip(), purpose="case_review", case_type=case_type)
        except (ValueError, PermissionError) as error:
            st.error(str(error))
            st.stop()
            
    if not get_scoped_case(actor, case_id.strip(), purpose="case_review"):
        st.error("This case was not found. Start a new case or choose an existing one.")
        st.stop()

    # 2. Extract final transcript
    final_transcript = "\\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in st.session_state["chat_messages"]])
    
    # 3. Exactly the same backend pipeline as submit_interaction
    analysis_text = final_transcript.strip()
    translation_used = selected_language != "English"
    if translation_used:
        with st.spinner(f"Translating {selected_language} transcript for analysis..."):
            analysis_text = translate_to_english(analysis_text, selected_language)

    active_spi_config = get_active_spi_threshold_config()
    prior_interactions = list(reversed(get_scoped_interactions(actor, case_id.strip(), purpose="case_review")))[:10]
    
    with st.spinner("Extracting support signals..."):
        support_signals = extract_support_signals(analysis_text)
        
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

    scores = {item["key"]: item["score"] for item in assessment["dimensions"]}
    review_required = "PENDING" if (
        assessment["spi"] >= assessment["review_thresholds"]["prompt"]
        or assessment["explicit_danger"]
        or assessment["explicit_self_harm_statement"]
    ) else "NOT_REQUIRED"

    # Save to database
    interaction_id = insert_scoped_interaction(
        actor,
        case_id=case_id.strip(),
        purpose="case_review",
        transcript=final_transcript.strip(),
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
    )
    
    try:
        record_consent(
            actor,
            case_id.strip(),
            purpose="interaction_analysis",
            channel=channel,
            language=selected_language,
            consent_version="interaction-analysis.v1",
            contact_preferences={"source": "interaction"},
        )
    except (ValueError, PermissionError) as error:
        st.warning(f"Interaction saved, but the consent ledger could not be updated: {error}")
        
    tasks = check_and_create_review_tasks(case_id.strip(), interaction_id, assessment, support_signals)
    crisis_events = create_crisis_workflow_events(case_id.strip(), interaction_id, assessment, support_signals)
    
    st.session_state["chat_saved"] = True
    st.session_state["last_assessment"] = assessment
    st.session_state["last_tasks"] = tasks
    st.session_state["last_crisis_events"] = crisis_events
    st.session_state["last_support_signals"] = support_signals
    st.session_state["last_limitations"] = limitations
    st.session_state["last_interaction_id"] = interaction_id
    st.session_state["last_case_id"] = case_id
    st.rerun()

# -------------------------------------------------------------
# Results Display (only shown after chat is saved)
# -------------------------------------------------------------
if st.session_state.get("chat_saved"):
    st.success(t("p13_save_success"))
    assessment = st.session_state["last_assessment"]
    tasks = st.session_state["last_tasks"]
    crisis_events = st.session_state["last_crisis_events"]
    support_signals = st.session_state["last_support_signals"]
    limitations = st.session_state["last_limitations"]
    interaction_id = st.session_state["last_interaction_id"]
    saved_case_id = st.session_state["last_case_id"]

    summary_col, evidence_col = st.columns([1, 2])
    with summary_col:
        st.markdown(
            f'''
            <div class="score-display" style="background: {assessment['color']}18; border: 2px solid {assessment['color']};">
                <div class="score-number" style="color: {assessment['color']};">{assessment['spi']:.0f}</div>
                <div class="score-band" style="color: {assessment['color']};">{assessment['emoji']} {assessment['priority_band']}</div>
                <div class="score-scale">Follow-up priority score • 0–100</div>
            </div>
            ''',
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
                f'''
                <div class="explanation-card">
                    <div class="explanation-feature">{item['label']}: {item['score']:.0f}/100</div>
                    <div class="explanation-detail">{' • '.join(reported_items[:2])}</div>
                </div>
                ''',
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
    st.caption(f"Record {interaction_id} saved for case {saved_case_id.strip()}.")
