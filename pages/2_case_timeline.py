"""Show an evidence-linked support timeline for trained human review."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

from config import DIMENSION_LABELS, SUPPORT_PRIORITY_BANDS
from src.database import (
    get_active_spi_threshold_config,
    get_restricted_transcript,
    get_scoped_case,
    get_scoped_cases,
    get_scoped_interactions,
    get_scoped_validated_screenings,
    insert_scoped_interaction,
    save_scoped_interaction_reviewer_override,
)
from src.scoring import assess_spi_trend, project_spi_trajectory
from src.translations import t
from src.ui_access import get_active_actor


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p2_heading")}</h1>
        <p>{t("p2_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(t("p2_caption"))

try:
    actor = get_active_actor()
    scoped_cases = get_scoped_cases(actor, purpose="case_review")
except Exception as error:
    st.error(f"{t('p2_load_error')}: {error}")
    st.stop()
case_ids = [case["case_id"] for case in scoped_cases]
if not case_ids:
    st.warning(t("p2_no_cases"))
    st.stop()

selected_case = st.selectbox(t("p2_case_reference"), options=case_ids)
case_info = get_scoped_case(actor, selected_case, purpose="case_review")
if case_info:
    info_cols = st.columns(4)
    info_cols[0].metric("Case ID", selected_case)
    info_cols[1].metric("State", case_info.get("state", "N/A"))
    info_cols[2].metric("District", case_info.get("district", "N/A"))
    registered = case_info.get("registered_at", "")
    try:
        registered = datetime.fromisoformat(registered).strftime("%d %b %Y")
    except (ValueError, TypeError):
        pass
    info_cols[3].metric("Registered", registered or "N/A")

interactions = get_scoped_interactions(actor, selected_case, purpose="case_review")
if not interactions:
    st.info("No conversation records for this case yet.")
    st.stop()

df = pd.DataFrame(interactions)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df["spi"] = pd.to_numeric(df["support_priority_indicator"], errors="coerce")
df = df.sort_values("timestamp")
scored_df = df[df["spi"].notna()].copy()
scored_interactions = [record for record in interactions if record.get("support_priority_indicator") is not None]
active_spi_config = get_active_spi_threshold_config()
chart_bands = [
    {**SUPPORT_PRIORITY_BANDS[0], "min": 0, "max": active_spi_config["timely_review_threshold"]},
    {**SUPPORT_PRIORITY_BANDS[1], "min": active_spi_config["timely_review_threshold"], "max": active_spi_config["prompt_review_threshold"]},
    {**SUPPORT_PRIORITY_BANDS[2], "min": active_spi_config["prompt_review_threshold"], "max": active_spi_config["urgent_review_threshold"]},
    {**SUPPORT_PRIORITY_BANDS[3], "min": active_spi_config["urgent_review_threshold"], "max": 100},
]

if len(scored_df) >= 2:
    trend = assess_spi_trend(scored_interactions[-1], list(reversed(scored_interactions[:-1])), active_spi_config)
    last_spi = scored_df.iloc[-1]["spi"]
    summary_cols = st.columns(3)
    summary_cols[0].metric(
        "Latest priority", f"{last_spi:.0f}/100",
        delta=f"{trend['delta']:+.0f}" if trend["comparable"] else "Not comparable",
        delta_color="inverse" if trend["comparable"] else "off",
    )
    summary_cols[1].metric("Review timeliness", df.iloc[-1].get("priority_band") or "Not available")
    if not trend["comparable"]:
        summary_cols[2].metric("Trend", "Not comparable", delta="Check collection context")
        st.info("Trend not interpreted: " + ", ".join(issue.replace("_", " ") for issue in trend["quality_issues"]) + ".")
    elif trend["status"] == "worsening":
        summary_cols[2].metric("Change", "Higher estimate", delta="Review context and limitations", delta_color="inverse")
    elif trend["status"] == "improving":
        summary_cols[2].metric("Change", "Lower estimate", delta="Still review source notes", delta_color="normal")
    else:
        summary_cols[2].metric("Change", "Similar estimate", delta="No automatic conclusion")

if len(scored_interactions) >= 3:
    projection = project_spi_trajectory(scored_interactions, active_spi_config)
    if projection["status"] == "projected_urgent":
        st.warning(
            f"📈 **Trajectory projection:** {projection['message']}\n\n"
            f"*{projection['caveat']}*"
        )
    elif projection["status"] in ("no_crossing", "already_urgent"):
        st.info(f"📉 **Trajectory projection:** {projection['message']}")

if scored_df.empty:
    st.info("This case has no compatible follow-up priority records yet. Older records from a previous version are not shown here.")
else:
    fig = go.Figure()
    for band in chart_bands:
        fig.add_hrect(
            y0=band["min"], y1=band["max"], fillcolor=f"{band['color']}18", line_width=0,
            annotation_text=band["label"], annotation_position="right", annotation_font_size=10,
            annotation_font_color="rgba(230,230,230,0.55)",
        )
    marker_colors = [
        next((band["color"] for band in chart_bands if band["min"] <= value <= band["max"]), "#999999")
        for value in scored_df["spi"]
    ]
    fig.add_trace(go.Scatter(
        x=scored_df["timestamp"], y=scored_df["spi"], mode="lines+markers", name="Follow-up priority",
        line=dict(color="#6C63FF", width=3), marker=dict(size=11, color=marker_colors, line=dict(width=2, color="#FFFFFF")),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Priority: %{y:.0f}/100<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=f"Follow-up priority over time — {selected_case}", font=dict(size=16, color="#FAFAFA")),
        xaxis=dict(title="Date", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(title="Follow-up priority (0–100)", range=[0, 100], dtick=20, showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=450,
        margin=dict(l=60, r=150, t=60, b=60), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.markdown("### Engagement over time")

# Participation Rate
recent_interactions = interactions[-5:]
completed = len(recent_interactions)
missed = sum(r.get("unanswered_follow_up_count", 0) for r in recent_interactions)
scheduled = completed + missed
participation_rate = (completed / scheduled) * 100 if scheduled > 0 else 100.0

# Transcript Shift
lengths = [len(r.get("transcript_ciphertext", "")) for r in recent_interactions]
if len(lengths) >= 3:
    baseline_avg = sum(lengths[:-1]) / (len(lengths) - 1)
    current = lengths[-1]
    if baseline_avg > 0:
        if current < baseline_avg * 0.5:
            transcript_shift = "Shorter transcripts than historical baseline"
        elif current > baseline_avg * 1.5:
            transcript_shift = "Longer transcripts than historical baseline"
        else:
            transcript_shift = "Transcript length stable"
    else:
        transcript_shift = "Transcript length stable"
else:
    transcript_shift = "Insufficient history to establish response length baseline"

# Screening Shift
screenings = get_scoped_validated_screenings(actor, selected_case, purpose="case_review")
skip_shift = ""
if len(screenings) >= 2:
    recent_screening = screenings[0]
    older_screenings = screenings[1:5]
    q_admin = len(recent_screening.get("questions_administered", []))
    recent_skip_rate = len(recent_screening.get("skipped_item_ids", [])) / q_admin if q_admin else 0
    
    older_skip_rates = [
        len(s.get("skipped_item_ids", [])) / len(s.get("questions_administered", []))
        for s in older_screenings if s.get("questions_administered")
    ]
    avg_older_skip = sum(older_skip_rates) / len(older_skip_rates) if older_skip_rates else 0
    
    if recent_skip_rate > avg_older_skip + 0.2:
        skip_shift = "Increased skip rate on validated questionnaires"
    elif recent_skip_rate < avg_older_skip - 0.2:
        skip_shift = "Decreased skip rate on validated questionnaires"
    else:
        skip_shift = "Questionnaire completion stable"

shift_message = transcript_shift
if skip_shift:
    shift_message += f" • {skip_shift}"

st.info(
    f"**Participation rate:** {participation_rate:.0f}% of scheduled check-ins completed across the last {completed} interactions.\n\n"
    f"**Response pattern shift:** {shift_message}"
)

st.markdown("#### Conversation records")
for index, (_, row) in enumerate(df.iterrows()):
    timestamp = row["timestamp"].strftime("%d %b %Y, %I:%M %p")
    with st.expander(
        f"{timestamp} — " + (
            f"Priority {row['spi']:.0f}/100 ({row.get('priority_band') or 'not available'})"
            if not pd.isna(row["spi"]) else "No compatible priority score (older record)"
        ) + f" via {row.get('channel', 'N/A')}",
        expanded=index == len(df) - 1,
    ):
        detail_cols = st.columns(2)
        with detail_cols[0]:
            st.markdown("**Areas of concern**")
            dimensions = [
                ("physical_safety", row.get("physical_safety_score")),
                ("wellbeing", row.get("wellbeing_concern_score")),
                ("service_access", row.get("service_access_score")),
            ]
            for key, score in dimensions:
                if score is not None and not pd.isna(score):
                    st.write(f"- {DIMENSION_LABELS[key]}: {float(score):.0f}/100")
            st.write(f"**How sure the system is:** {(row.get('confidence') or 'low').title()}")
            st.caption(
                f"Scoring version: {row.get('score_version') or 'older/unknown'} • "
                f"AI version: {row.get('model_version') or 'older/unknown'}"
            )

        with detail_cols[1]:
            st.markdown("**What was shared**")
            evidence = row.get("evidence") or []
            if isinstance(evidence, list) and evidence:
                for item in evidence:
                    if isinstance(item, dict):
                        st.write(f"- {DIMENSION_LABELS.get(item.get('dimension'), 'Reported information')}: “{item.get('quote', '')}”")
            else:
                st.caption("No specific quote is available for this older or limited-information record.")

        st.markdown("**Things to keep in mind**")
        limitations = row.get("data_quality_limitations") or []
        if isinstance(limitations, list):
            for limitation in limitations:
                st.caption(f"• {limitation}")
        else:
            st.caption(str(limitations))

        trend_issues = row.get("trend_quality_issues") or []
        if trend_issues:
            st.caption("Stored trend-quality flags: " + ", ".join(str(item).replace("_", " ") for item in trend_issues))
        override = row.get("reviewer_override")
        if isinstance(override, dict):
            st.info(
                f"Staff reviewer note: {override.get('review_priority') or 'no priority change'} — "
                f"{override.get('rationale') or 'no reason recorded'}"
            )

        audio_metadata = row.get("audio_analysis_metadata")
        if isinstance(audio_metadata, dict):
            st.markdown("**Experimental voice analysis details**")
            st.caption(
                f"Status: {audio_metadata.get('analysis_status', 'not available')} • "
                f"Quality: {audio_metadata.get('audio_quality', 'not assessed')} • "
                f"Language: {audio_metadata.get('language', 'not stated')} • "
                f"Model uncertainty: {audio_metadata.get('model_uncertainty', 'not assessed')}"
            )
            st.caption(
                f"Audio transcription permission: {'recorded' if audio_metadata.get('transcription_consent_recorded') else 'not recorded'} • "
                f"Voice analysis permission: {'recorded' if audio_metadata.get('consent_recorded') else 'not recorded'}"
            )
            st.caption(audio_metadata.get("limitation_notice", "Experimental voice analysis does not diagnose anything and is not used for review tasks or priority scores."))
            st.caption(f"Raw-audio status: {audio_metadata.get('raw_audio_retention_status', 'not retained')}")

        with st.expander("View original notes (sensitive)", expanded=False):
            if not row.get("has_restricted_transcript"):
                st.caption("No original notes are stored for this record.")
            else:
                if st.button("Access original notes for case review", key=f"view_raw_{row['id']}"):
                    try:
                        st.text(get_restricted_transcript(actor, int(row["id"]), purpose="case_review") or "No source notes available.")
                    except PermissionError as error:
                        st.error(str(error))
                else:
                    st.caption("Access to original notes is controlled by your role, location, and purpose, and is logged.")

        with st.expander("Add your own assessment", expanded=False):
            st.caption("This records your own judgement about how urgently to follow up and why. It does not change the calculated score or trigger any action.")
            with st.form(f"override_{row['id']}"):
                st.caption(f"Reviewer identity: {actor.user_id}")
                labels = [band["label"] for band in SUPPORT_PRIORITY_BANDS]
                selected = st.selectbox(
                    "Your assessment of urgency (optional)", ["No priority override"] + labels,
                    key=f"override_priority_{row['id']}",
                )
                rationale = st.text_area("Rationale", key=f"override_rationale_{row['id']}")
                if st.form_submit_button("Record override"):
                    try:
                        save_scoped_interaction_reviewer_override(
                            actor, int(row["id"]), rationale,
                            None if selected == "No priority override" else selected,
                        )
                        st.success("Your assessment has been recorded and logged. The priority score itself was not changed.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
