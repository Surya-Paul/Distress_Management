"""Human-review queue for non-diagnostic support-priority tasks."""

from datetime import datetime

import streamlit as st

from src.database import complete_scoped_review, get_scoped_alerts
from src.translations import t
from src.ui_access import get_active_actor


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p3_heading")}</h1>
        <p>{t("p3_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t("p3_warning"))

try:
    actor = get_active_actor()
    active_tasks = get_scoped_alerts(actor, purpose="case_review")
    all_tasks = get_scoped_alerts(actor, purpose="case_review", include_completed=True)
except Exception as error:
    st.error(f"{t('p3_load_error')}: {error}")
    st.stop()
urgent_count = sum(task["alert_level"] == "URGENT" for task in active_tasks)
priority_count = sum(task["alert_level"] == "PRIORITY" for task in active_tasks)
completed_count = sum(task.get("review_status") == "COMPLETED" for task in all_tasks)

stat_cols = st.columns(4)
for col, label, value, color in zip(
    stat_cols,
    [t("p3_waiting"), t("p3_urgent"), t("p3_priority"), t("p3_done")],
    [len(active_tasks), urgent_count, priority_count, completed_count],
    ["#FF5722", "#B71C1C", "#FF9800", "#4CAF50"],
):
    with col:
        st.markdown(
            f"""<div class="metric-card"><div class="metric-label">{label}</div>
            <div class="metric-value" style="color:{color};">{value}</div></div>""",
            unsafe_allow_html=True,
        )

st.divider()
filter_cols = st.columns([1, 1, 2])
with filter_cols[0]:
    show_completed = st.checkbox("Show finished reviews", value=False)
with filter_cols[1]:
    level_filter = st.selectbox("How urgent?", ["All", "URGENT", "PRIORITY"])

tasks = all_tasks if show_completed else active_tasks
if level_filter != "All":
    tasks = [task for task in tasks if task["alert_level"] == level_filter]

if not tasks:
    st.info("No review tasks match this filter. An empty list does not mean every person is safe or supported.")

for task in tasks:
    urgent = task["alert_level"] == "URGENT"
    css_class = "alert-critical" if urgent else "alert-warning"
    icon = "🚨" if urgent else "⚠️"
    try:
        timestamp = datetime.fromisoformat(task.get("timestamp", "")).strftime("%d %b %Y, %I:%M %p")
    except (ValueError, TypeError):
        timestamp = task.get("timestamp", "")
    completed = task.get("review_status") == "COMPLETED"
    status = "COMPLETED" if completed else "PENDING HUMAN REVIEW"
    st.markdown(
        f"""
        <div class="{css_class}" style="{'opacity: .6;' if completed else ''}">
            <strong>{icon} {task['alert_level']} REVIEW • {status}</strong>
            <span style="color:rgba(255,255,255,.45); font-size:.8rem; margin-left:1rem;">{timestamp}</span>
            <div style="margin-top:.5rem;"><strong>Case:</strong> {task['case_id']} • {task.get('state', '')} / {task.get('district', '')}</div>
            <div style="margin-top:.6rem;">{task['reason']}</div>
            <div style="margin-top:.7rem; padding:.6rem; background:rgba(255,255,255,.03); border-radius:6px;">
                <strong>Suggested next step — only a suggestion, not an instruction:</strong><br/>{task.get('recommended_intervention', '')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if completed:
        st.caption(f"Reviewed by {task.get('reviewer_name') or 'not recorded'} on {task.get('reviewed_at') or 'not recorded'}.")
        if task.get("review_notes"):
            st.caption(f"Review outcome: {task['review_notes']}")
        continue

    with st.expander("Complete your review", expanded=False):
        with st.form(f"review_task_{task['id']}"):
            st.caption(f"Verified reviewer context: {actor.user_id}")
            review_notes = st.text_area(
                "What you found and what happens next",
                placeholder="Describe what you reviewed, the person's choice where relevant, and any follow-up. Do not include unnecessary personal details.",
            )
            attestation = st.checkbox(
                "I am authorised and have looked at the evidence, limitations, permission records, and how this person prefers to be contacted."
            )
            submitted = st.form_submit_button("Complete review")
            if submitted:
                if not attestation:
                    st.error("Please confirm the review statement above before completing this task.")
                else:
                    try:
                        complete_scoped_review(actor, task["id"], review_notes, purpose="case_review")
                        st.success("Review recorded. No automatic action was taken.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
