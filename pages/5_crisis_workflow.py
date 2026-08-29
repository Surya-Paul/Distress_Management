"""Pathway-specific, human-operated crisis review workflow.

This page never sends SMS, calls a person, or contacts a third party. It records
internal assignment, acknowledgement, safe-contact attempts performed by a human,
and a documented closure outcome.
"""

from datetime import date, datetime

import streamlit as st

from config import SAFE_OUTREACH_CHANNELS
from src.database import (
    acknowledge_scoped_crisis_event,
    assign_scoped_crisis_event,
    close_scoped_crisis_event,
    get_case_safe_contact_protocol,
    get_crisis_escalations,
    get_scoped_crisis_events,
    get_scoped_interactions,
    get_safe_contact_attempts,
    get_service_directory_entries,
    record_scoped_safe_contact_attempt,
)
from src.translations import t
from src.ui_access import get_active_actor


def _format_time(value):
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %I:%M %p")
    except (ValueError, TypeError):
        return value or "Not recorded"


def _event_is_overdue(event):
    if event["status"] not in {"PENDING_ASSIGNMENT", "AWAITING_ACKNOWLEDGEMENT"}:
        return False
    try:
        return datetime.now() > datetime.fromisoformat(event["acknowledgement_due_at"])
    except (ValueError, TypeError):
        return False


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p5_heading")}</h1>
        <p>{t("p5_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.error(t("p5_error_banner"))

show_closed = st.checkbox(t("p5_show_closed"), value=False)
try:
    actor = get_active_actor()
    events = get_scoped_crisis_events(actor, purpose="crisis_review", include_closed=show_closed)
except Exception as error:
    st.error(f"{t('p5_load_error')}: {error}")
    st.stop()
if not events:
    st.info(t("p5_no_events"))

for event in events:
    pathway_label = "Self-harm/suicide statement" if event["pathway"] == "SELF_HARM_CONCERN" else "External safety threat"
    overdue = _event_is_overdue(event)
    banner_type = "alert-critical" if event["priority"] == "URGENT" else "alert-warning"
    with st.expander(
        f"{'⏰ ' if overdue else '🚨 '} {pathway_label} — Case {event['case_id']} — {event['status'].replace('_', ' ').title()}",
        expanded=event["status"] != "CLOSED",
    ):
        st.markdown(
            f"""
            <div class="{banner_type}">
                <strong>{event['priority']} • {pathway_label}</strong><br/>
                Accountable role: {event['assigned_role']}<br/>
                Assigned staff member: {event.get('assigned_to') or 'Not assigned — assignment required'}<br/>
                Response needed by: {_format_time(event['acknowledgement_due_at'])}
                {'<br/><strong>⚠️ Response overdue</strong>' if overdue else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"**Suggested next action — human judgement required:** {event['recommended_next_action']}")

        left, right = st.columns(2)
        with left:
            st.markdown("**What was shared and how reliable it is**")
            evidence = event.get("evidence_snapshot") or []
            if evidence:
                for item in evidence:
                    st.write(f"- “{item.get('quote', '')}” ({item.get('confidence', 'low')} confidence)")
            else:
                st.caption("No evidence snapshot is available. Review the source notes before acting.")
            context = event.get("context_snapshot") or {}
            st.caption(f"How sure the system is: {context.get('confidence', 'low')}")
            for limitation in context.get("limitations", []):
                st.caption(f"Keep in mind: {limitation}")

        with right:
            st.markdown("**Safe ways to reach this person**")
            protocol = get_case_safe_contact_protocol(event["case_id"])
            if protocol:
                st.write(f"- Label: {protocol['protocol_label']}")
                st.write(f"- Recorded consent: {'Yes' if protocol['consent_recorded'] else 'No'}")
                st.write(f"- Allowed channels: {', '.join(protocol['allowed_channels']) or 'None'}")
                st.write(f"- Safe window: {protocol.get('safe_contact_window') or 'Not specified'}")
                st.write(f"- Do not contact third parties: {'Yes' if protocol['do_not_contact_third_parties'] else 'No'}")
                st.write(f"- Max attempts: {protocol['maximum_attempts']}; retry interval: {protocol['minimum_retry_minutes']} minutes")
            else:
                st.warning("No safe way to contact this person has been recorded. Do not contact them.")

        contact_preferences = context.get("contact_preferences", {})
        if contact_preferences.get("status") == "detected":
            st.info(
                "Stated interaction preferences: "
                f"language: {contact_preferences.get('preferred_language') or 'not specified'}; "
                f"constraints: {', '.join(contact_preferences.get('safe_contact_constraints') or []) or 'none extracted'}."
            )

        with st.expander("Case history for review", expanded=False):
            history = get_scoped_interactions(actor, event["case_id"], purpose="crisis_review")
            if not history:
                st.caption("No interaction history is available.")
            for record in history[-5:]:
                st.write(
                    f"- {_format_time(record.get('timestamp'))}: Priority {record.get('support_priority_indicator', 0):.0f}/100; "
                    f"confidence {record.get('confidence') or 'low'}; channel {record.get('channel') or 'not recorded'}"
                )

        with st.expander("Verified local support directory", expanded=False):
            services = get_service_directory_entries(event["state"], event["district"], verified_only=True)
            if not services:
                st.caption("No verified local services are configured. Do not substitute unverified contact information.")
            for service in services:
                st.write(
                    f"- **{service['service_type'].replace('_', ' ').title()}** — {service['service_name']} "
                    f"({service['contact_reference']})"
                )
                if service.get("availability_notes"):
                    st.caption(service["availability_notes"])

        with st.expander("Internal referral history", expanded=False):
            escalations = get_crisis_escalations(event["id"])
            for escalation in escalations:
                st.write(
                    f"- {_format_time(escalation['created_at'])}: {escalation['channel']} — "
                    f"{escalation['status']}. {escalation['reason']}"
                )
            st.caption("Only secure internal queue escalation is automated. No outward channel is available here.")

        if event["status"] == "PENDING_ASSIGNMENT":
            with st.form(f"assign_crisis_{event['id']}"):
                assignee = st.text_input("Accountable reviewer name or authorised staff ID")
                role = st.selectbox("Accountable role", ["Counsellor", "District safety officer"])
                if st.form_submit_button("Assign staff member"):
                    try:
                        assign_scoped_crisis_event(actor, event["id"], assignee, role, purpose="crisis_review")
                        st.success("Staff member assigned. No outreach was sent.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

        if event["status"] == "AWAITING_ACKNOWLEDGEMENT":
            with st.form(f"ack_crisis_{event['id']}"):
                st.caption(f"Verified reviewer context: {actor.user_id}")
                attestation = st.checkbox("I am the assigned reviewer and have reviewed the evidence, limitations, consent, and safe-contact protocol.")
                if st.form_submit_button("Confirm you've seen this"):
                    if not attestation:
                        st.error("Confirm the acknowledgement attestation first.")
                    else:
                        try:
                            acknowledge_scoped_crisis_event(actor, event["id"], purpose="crisis_review")
                            st.success("Acknowledgement recorded. No automatic outreach was performed.")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))

        if event["status"] == "ACKNOWLEDGED":
            attempts = get_safe_contact_attempts(event["id"])
            st.markdown("**Safe-contact attempt log**")
            if attempts:
                for attempt in attempts:
                    st.write(
                        f"- Attempt {attempt['attempt_number']}: {attempt['channel']} — {attempt['outcome']} "
                        f"at {_format_time(attempt['attempted_at'])}"
                    )
                    if attempt.get("next_eligible_at"):
                        st.caption(f"Next eligible attempt: {_format_time(attempt['next_eligible_at'])}")
            else:
                st.caption("No contact attempt has been logged.")

            with st.expander("Record a human-performed safe-contact attempt", expanded=False):
                with st.form(f"contact_attempt_{event['id']}"):
                    st.caption(f"Verified reviewer context: {actor.user_id}")
                    channel = st.selectbox("Approved safe channel", list(SAFE_OUTREACH_CHANNELS), key=f"contact_channel_{event['id']}")
                    outcome = st.selectbox("Outcome", ["REACHED", "NOT_REACHED"], key=f"contact_outcome_{event['id']}")
                    notes = st.text_area("Minimal attempt note", key=f"contact_notes_{event['id']}")
                    if st.form_submit_button("Record attempt only"):
                        try:
                            record_scoped_safe_contact_attempt(actor, event["id"], channel, outcome, notes, purpose="crisis_review")
                            st.success("Attempt logged. This system did not initiate the contact.")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))

            with st.expander("Mark as resolved", expanded=False):
                with st.form(f"close_crisis_{event['id']}"):
                    st.caption(f"Verified reviewer context: {actor.user_id}")
                    action_taken = st.text_area("Action taken")
                    outcome = st.text_area("Outcome")
                    follow_up_at = st.date_input("Follow-up date", value=date.today())
                    closure_rationale = st.text_area("Closure rationale")
                    if st.form_submit_button("Mark as resolved with documented outcome"):
                        try:
                            close_scoped_crisis_event(
                                actor, event["id"], action_taken, outcome, follow_up_at, closure_rationale,
                                purpose="crisis_review",
                            )
                            st.success("Crisis event closed with an auditable human outcome.")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))
