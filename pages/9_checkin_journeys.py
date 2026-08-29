"""Survivor-controlled multilingual check-in journey page.

This page provides a simulation of all six delivery channels (chatbot, IVRS,
SMS, mobile app, web portal, counsellor follow-up) for guided, non-diagnostic
check-ins across four Indian languages.

Design constraints:
 - Safety is always asked before wellbeing.
 - Skip, pause, stop, and request-human-help are available on every step.
 - No stigmatizing labels appear on any survivor-facing screen.
 - The survivor is never asked to retell the incident.
"""

import json

import streamlit as st

from config import (
    CHECKIN_ACCESSIBILITY_NEEDS,
    CHECKIN_BASE_LANGUAGE_PACKS,
    CHECKIN_CHANNELS,
    CHECKIN_CHANNEL_LABELS,
    CHECKIN_SUPPORT_CHOICES,
    SAFE_FOLLOW_UP_CHANNELS,
)
from src.checkin_journeys import (
    EXTENSIBILITY_GUIDE,
    CheckinJourneyValidationError,
    channel_delivery_guidance,
    get_language_pack,
    ivrs_accessibility_fallback,
    journey_blueprint,
    language_catalog,
    language_evaluation_report,
    option_label,
    validate_checkin_start,
    validate_checkin_update,
)
from src.database import (
    create_checkin_session,
    get_checkin_session,
    get_checkin_sessions_for_case,
    get_connection,
    update_checkin_session,
)
from src.translations import t

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="main-header">
    <h1>{t("p9_heading")}</h1>
    <p>{t("p9_subheading")}</p>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="background: rgba(108, 99, 255, 0.08); border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: 1.5rem; border-left: 3px solid #6C63FF;">
    <div style="font-weight: 600; margin-bottom: 0.3rem;">{t("p9_safety_first_title")}</div>
    <div style="font-size: 0.85rem; color: rgba(255,255,255,0.7);">
        Every check-in begins with consent and contact safety. Immediate safety is assessed
        before wellbeing. The survivor can skip, pause, stop, or request a trained person at any time.
        No incident details are ever requested.
    </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper: render channel-specific step UI
# ---------------------------------------------------------------------------
def _render_step_controls(lang_code, channel, step_key, prefix_key):
    """Render skip/pause/stop/human-help controls for each journey step."""
    pack = get_language_pack(lang_code)
    cols = st.columns(4)
    with cols[0]:
        skip = st.button(f"⏭ {pack['copy']['skip']}", key=f"{prefix_key}_skip")
    with cols[1]:
        pause = st.button(f"⏸ {pack['copy']['pause']}", key=f"{prefix_key}_pause")
    with cols[2]:
        stop = st.button(f"⏹ {pack['copy']['stop']}", key=f"{prefix_key}_stop")
    with cols[3]:
        human = st.button(f"🧑‍⚕️ {pack['copy']['human_help']}", key=f"{prefix_key}_human")
    return {"skip": skip, "pause": pause, "stop": stop, "human_help": human}


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_start, tab_continue, tab_languages = st.tabs([
    "🆕 Start a new check-in",
    "📋 Continue a check-in",
    "🌐 Languages & accessibility",
])

# ========================= TAB 1: START NEW CHECK-IN =========================
with tab_start:
    st.subheader("Begin a New Check-In")
    st.caption("Select a case, channel, and language. Consent and safety preferences are collected first.")

    # Case selection
    conn = get_connection()
    try:
        cases = conn.execute("SELECT case_id, state, district FROM cases WHERE data_status = 'ACTIVE' ORDER BY case_id").fetchall()
    finally:
        conn.close()

    if not cases:
        st.info("No active cases. Create a case through the Record Consented Interaction page first.")
    else:
        case_options = {f"{c['case_id']}  ({c['state']} / {c['district']})": c["case_id"] for c in cases}
        selected_case_label = st.selectbox("Select case", list(case_options.keys()), key="checkin_case")
        selected_case_id = case_options[selected_case_label]

        col_channel, col_lang = st.columns(2)
        with col_channel:
            channel = st.selectbox(
                "Delivery channel",
                CHECKIN_CHANNELS,
                format_func=lambda c: CHECKIN_CHANNEL_LABELS.get(c, c),
                key="checkin_channel",
            )
        with col_lang:
            lang_options = {v["autonym"] + f" ({v['name']})": code for code, v in CHECKIN_BASE_LANGUAGE_PACKS.items()}
            lang_label = st.selectbox("Preferred language", list(lang_options.keys()), key="checkin_lang")
            lang_code = lang_options[lang_label]

        # Show the control statement in the chosen language
        pack = get_language_pack(lang_code)
        st.markdown(f"""
        <div style="background: rgba(76, 175, 80, 0.1); border-left: 3px solid #4CAF50; border-radius: 0 8px 8px 0; padding: 1rem 1.2rem; margin: 1rem 0;">
            <div style="font-weight: 600; font-size: 1.05rem;">🛡️ {pack['copy']['control']}</div>
        </div>
        """, unsafe_allow_html=True)

        # Consent
        st.markdown(f"**{pack['copy']['consent']}**")
        consent = st.radio(
            "Consent",
            [True, False],
            format_func=lambda v: pack["options"]["yes"] if v else pack["options"]["no"],
            key="checkin_consent",
            horizontal=True,
            label_visibility="collapsed",
        )

        if consent:
            # Safe time
            st.markdown(f"**{pack['copy']['safe_time']}**")
            safe_time = st.radio(
                "Safe time",
                ["safe_now", "another_time", "not_stated"],
                format_func=lambda v: option_label(lang_code, v),
                key="checkin_safe_time",
                horizontal=True,
                label_visibility="collapsed",
            )

            # Safe channel
            st.markdown(f"**{pack['copy']['safe_channel']}**")
            safe_channel = st.selectbox(
                "Safe channel",
                SAFE_FOLLOW_UP_CHANNELS,
                format_func=lambda c: option_label(lang_code, c),
                key="checkin_safe_channel",
                label_visibility="collapsed",
            )

            # Programme mention
            st.markdown(f"**{pack['copy']['programme_mention']}**")
            prog_mention = st.radio(
                "Programme mention",
                [True, False],
                format_func=lambda v: pack["options"]["yes"] if v else pack["copy"]["no_programme"],
                key="checkin_prog_mention",
                horizontal=True,
                label_visibility="collapsed",
            )

            # Accessibility needs
            st.markdown(f"**{pack['copy']['accessibility']}**")
            access_needs = st.multiselect(
                "Accessibility needs",
                CHECKIN_ACCESSIBILITY_NEEDS,
                format_func=lambda a: option_label(lang_code, a),
                key="checkin_access_needs",
                label_visibility="collapsed",
            )

            # Submit
            if st.button("✅ Begin Check-In", type="primary", key="checkin_start_btn"):
                try:
                    payload = {
                        "channel": channel,
                        "language_code": lang_code,
                        "consent_recorded": consent,
                        "safe_time": safe_time,
                        "safe_channel": safe_channel,
                        "programme_mention_allowed": prog_mention,
                        "accessibility_needs": access_needs,
                    }
                    validated = validate_checkin_start(payload)
                    session_id = create_checkin_session(selected_case_id, validated)
                    st.success(f"Check-in session started (ID: {session_id}). Switch to the **Continue** tab to proceed.")
                    st.session_state["active_checkin_session"] = session_id
                except CheckinJourneyValidationError as e:
                    st.error(f"Validation error: {e}")
        else:
            st.info("Consent is required to begin a check-in. The survivor may decline at any time.")


# ========================= TAB 2: CONTINUE / COMPLETE =========================
with tab_continue:
    st.subheader("Continue a Check-In")

    # Find open sessions
    conn = get_connection()
    try:
        open_sessions = conn.execute(
            "SELECT s.*, c.state, c.district FROM checkin_sessions s JOIN cases c ON c.case_id = s.case_id WHERE s.status IN ('OPEN', 'PAUSED') ORDER BY s.updated_at DESC"
        ).fetchall()
    finally:
        conn.close()

    if not open_sessions:
        st.info("No open check-in sessions. Start a new check-in in the first tab.")
    else:
        session_options = {
            f"#{s['id']}  {s['case_id']} • {CHECKIN_CHANNEL_LABELS.get(s['channel'], s['channel'])} • {CHECKIN_BASE_LANGUAGE_PACKS.get(s['language_code'], {}).get('autonym', s['language_code'])} • {s['status']}": s["id"]
            for s in open_sessions
        }
        selected_session_label = st.selectbox("Select session", list(session_options.keys()), key="continue_session")
        session_id = session_options[selected_session_label]
        session = get_checkin_session(session_id)
        lang_code = session["language_code"]
        channel = session["channel"]
        pack = get_language_pack(lang_code)

        # Show channel delivery guidance
        guidance = channel_delivery_guidance(
            lang_code, channel, programme_mention_allowed=bool(session["programme_mention_allowed"]),
        )
        with st.expander("📡 How to deliver this check-in", expanded=False):
            st.markdown(f"**First touch:** {guidance['first_touch']}")
            for rule in guidance["rules"]:
                st.markdown(f"- {rule}")

        # Build the journey blueprint
        blueprint = journey_blueprint(
            lang_code, channel, programme_mention_allowed=bool(session["programme_mention_allowed"]),
        )

        # Determine which steps have been completed
        completed_steps = {r["step"] for r in session.get("responses", [])}

        # Render each journey step
        for i, step in enumerate(blueprint):
            step_name = step["step"]
            is_done = step_name in completed_steps

            # Channel-specific rendering
            if channel == "sms":
                icon = "📱"
                style_hint = "SMS: one question per message, keypad-style options"
            elif channel == "ivrs":
                icon = "📞"
                style_hint = "IVRS: spoken option with keypad — repeat(7) help(0) pause(8) stop(9)"
            elif channel == "counsellor_follow_up":
                icon = "👤"
                style_hint = "Guided script for a trained person"
            else:
                icon = "💬"
                style_hint = f"{CHECKIN_CHANNEL_LABELS.get(channel, channel)}: interactive UI"

            status_badge = "✅" if is_done else ("🔒" if step.get("required_before_next") and i > 0 and blueprint[i - 1]["step"] not in completed_steps else "⬜")

            with st.expander(f"{status_badge} {icon} Step {i + 1}: {step_name.replace('_', ' ').title()}", expanded=not is_done and status_badge != "🔒"):
                st.caption(style_hint)
                st.markdown(f"**{step['prompt']}**")

                if step.get("includes"):
                    if channel == "sms":
                        # SMS-style keypad rendering
                        for j, opt in enumerate(step["includes"]):
                            st.markdown(f"`{j + 1}` — {opt}")
                    elif channel == "ivrs":
                        # IVRS-style spoken options
                        for j, opt in enumerate(step["includes"]):
                            st.markdown(f"🔊 Press **{j + 1}** for: *{opt}*")
                        st.markdown("🔊 Press **7** to repeat • **0** for a trained person • **8** to pause • **9** to stop")
                    else:
                        # Interactive UI
                        for opt in step["includes"]:
                            st.markdown(f"- {opt}")

                if not is_done:
                    # Step-specific input
                    prefix = f"step_{session_id}_{step_name}"
                    if step_name == "immediate_safety":
                        safety_choice = st.radio(
                            "Your response",
                            ["safe_now", "not_sure", "need_human_help_now", "skip"],
                            format_func=lambda v: option_label(lang_code, v),
                            key=f"{prefix}_safety",
                            horizontal=True,
                            label_visibility="collapsed",
                        )
                        controls = _render_step_controls(lang_code, channel, step_name, prefix)
                        if st.button("Submit", key=f"{prefix}_submit", type="primary"):
                            if controls["pause"]:
                                update_checkin_session(session_id, validate_checkin_update({"control": "pause"}))
                                st.rerun()
                            elif controls["stop"]:
                                update_checkin_session(session_id, validate_checkin_update({"control": "stop"}))
                                st.rerun()
                            elif controls["human"]:
                                update_checkin_session(session_id, validate_checkin_update({"request_human_help": True}))
                                st.rerun()
                            else:
                                update_checkin_session(session_id, validate_checkin_update({"immediate_safety": safety_choice}))
                                st.rerun()

                    elif step_name == "wellbeing_optional":
                        well_choice = st.radio(
                            "Your response",
                            ["want_to_talk", "doing_ok", "skip"],
                            format_func=lambda v: option_label(lang_code, v),
                            key=f"{prefix}_well",
                            horizontal=True,
                            label_visibility="collapsed",
                        )
                        controls = _render_step_controls(lang_code, channel, step_name, prefix)
                        if st.button("Submit", key=f"{prefix}_submit", type="primary"):
                            if controls["pause"]:
                                update_checkin_session(session_id, validate_checkin_update({"control": "pause"}))
                                st.rerun()
                            elif controls["stop"]:
                                update_checkin_session(session_id, validate_checkin_update({"control": "stop"}))
                                st.rerun()
                            else:
                                update_checkin_session(session_id, validate_checkin_update({"wellbeing": well_choice}))
                                st.rerun()

                    elif step_name == "practical_support":
                        support = st.multiselect(
                            "Support preferences",
                            list(CHECKIN_SUPPORT_CHOICES),
                            format_func=lambda s: option_label(lang_code, s),
                            key=f"{prefix}_support",
                            label_visibility="collapsed",
                        )
                        controls = _render_step_controls(lang_code, channel, step_name, prefix)
                        if st.button("Submit", key=f"{prefix}_submit", type="primary"):
                            if controls["pause"]:
                                update_checkin_session(session_id, validate_checkin_update({"control": "pause"}))
                                st.rerun()
                            elif controls["stop"]:
                                update_checkin_session(session_id, validate_checkin_update({"control": "stop"}))
                                st.rerun()
                            else:
                                update_checkin_session(session_id, validate_checkin_update({"support_choices": support}))
                                st.rerun()

                    else:
                        _render_step_controls(lang_code, channel, step_name, prefix)

        # Complete the check-in
        st.divider()
        if st.button("✅ Finish this check-in", type="primary", key="complete_checkin"):
            update_checkin_session(session_id, validate_checkin_update({"control": "complete"}))
            st.success("Check-in marked as complete.")
            st.rerun()

        # Session history
        with st.expander("📜 Answers recorded so far", expanded=False):
            if session.get("responses"):
                for r in session["responses"]:
                    st.markdown(f"- **{r['response_key']}**: `{r['response_value']}` _(at {r['recorded_at']})_")
            else:
                st.info("No responses recorded yet.")


# ========================= TAB 3: LANGUAGE & ACCESSIBILITY REVIEW =========================
with tab_languages:
    st.subheader("Language support status")
    st.caption("Each language is evaluated independently. A language is never treated as validated merely because it shares a script or model with another.")

    # Side-by-side language comparison
    catalog = language_catalog()

    # Per-language evaluation reports
    st.markdown("### 📊 Per-Language Evaluation Reports")
    eval_cols = st.columns(len(catalog))
    for i, lang in enumerate(catalog):
        code = lang["code"]
        report = language_evaluation_report(code)
        with eval_cols[i]:
            status_icon = "✅" if report["reviewed"] else "⚠️"
            st.markdown(f"""
            <div style="background: rgba(108, 99, 255, 0.06); border-radius: 10px; padding: 1rem; text-align: center; border: 1px solid rgba(108, 99, 255, 0.15);">
                <div style="font-size: 1.5rem;">{status_icon}</div>
                <div style="font-weight: 700; font-size: 1.1rem;">{lang.get('autonym', code)}</div>
                <div style="font-size: 0.8rem; color: rgba(255,255,255,0.5);">{lang.get('name', code)}</div>
                <div style="margin-top: 0.5rem; font-size: 0.85rem;">
                    Copy: {report['copy_key_count']}/{report['expected_copy_keys']}<br/>
                    Options: {report['option_key_count']}/{report['expected_option_keys']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            if report["missing_copy_keys"]:
                st.error(f"Missing copy: {', '.join(report['missing_copy_keys'])}")
            if report["missing_option_keys"]:
                st.error(f"Missing opts: {', '.join(report['missing_option_keys'])}")

    # Side-by-side journey copy
    st.markdown("### 📝 Journey Copy Comparison")
    pack_en = get_language_pack("en")
    for key in pack_en["copy"]:
        with st.expander(f"🔑 `{key}`", expanded=False):
            for lang in catalog:
                code = lang["code"]
                try:
                    lp = get_language_pack(code)
                    val = lp["copy"].get(key, "❌ MISSING")
                except Exception:
                    val = "❌ NOT REGISTERED"
                st.markdown(f"**{lang.get('autonym', code)}** ({code}): {val}")

    # Option labels comparison
    st.markdown("### 🏷️ Option Labels Comparison")
    for key in pack_en["options"]:
        with st.expander(f"🔑 `{key}`", expanded=False):
            for lang in catalog:
                code = lang["code"]
                try:
                    lp = get_language_pack(code)
                    val = lp["options"].get(key, "❌ MISSING")
                except Exception:
                    val = "❌ NOT REGISTERED"
                st.markdown(f"**{lang.get('autonym', code)}** ({code}): {val}")

    # IVRS accessibility fallback
    st.markdown("### ♿ IVRS Accessibility Fallback")
    for lang in catalog:
        code = lang["code"]
        with st.expander(f"📞 {lang.get('autonym', code)} IVRS Fallback", expanded=False):
            fallback = ivrs_accessibility_fallback(code)
            st.markdown("**Design rules:**")
            for rule in fallback["design"]:
                st.markdown(f"- {rule}")
            st.markdown("**Not supported:**")
            for ns in fallback["not_supported"]:
                st.markdown(f"- ❌ {ns}")

    # Extensibility guide
    st.markdown("### 🔧 How to Add a New Language")
    with st.expander("Extensibility guide", expanded=False):
        st.code(EXTENSIBILITY_GUIDE, language="text")
