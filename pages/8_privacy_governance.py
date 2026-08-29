"""Retention, deletion, consent, and audit controls for authorised roles."""

from datetime import datetime

import streamlit as st

from src.database import (
    approve_case_deletion,
    create_retention_policy,
    execute_approved_deletion,
    get_deletion_workflows,
    get_scoped_cases,
    request_case_deletion,
)
from src.privacy_architecture import get_security_audit_events, verify_audit_chain
from src.translations import t
from src.ui_access import get_active_actor


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p8_heading")}</h1>
        <p>{t("p8_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t("p8_warning"))

try:
    actor = get_active_actor()
except Exception as error:
    st.error(f"{t('p8_access_error')}: {error}")
    st.stop()

if actor.role in {"counsellor", "district_officer"}:
    st.markdown(f"#### {t('p8_delete_heading')}")
    st.caption(t("p8_delete_caption"))
    try:
        cases = get_scoped_cases(actor, purpose="consent_management")
    except Exception as error:
        st.error(str(error))
        st.stop()
    if not cases:
        st.info(t("p8_no_cases"))
    else:
        with st.form("request_deletion"):
            case_id = st.selectbox(t("p8_case_reference"), [case["case_id"] for case in cases])
            reason = st.text_area(t("p8_delete_reason"))
            if st.form_submit_button(t("p8_request_deletion")):
                try:
                    workflow_id = request_case_deletion(actor, case_id, purpose="consent_management", reason=reason)
                    st.success(f"Deletion request {workflow_id} recorded and audited. No content has been deleted.")
                except (ValueError, PermissionError) as error:
                    st.error(str(error))

elif actor.role in {"state_administrator", "national_administrator"}:
    policy_tab, deletion_tab = st.tabs([t("p8_tab_retention"), t("p8_tab_deletions")])
    with policy_tab:
        st.caption("Creating a new version retains the previous policy for auditability. Apply only after governance approval.")
        with st.form("retention_policy"):
            version = st.text_input(t("p8_retention_version"), placeholder="retention.v2")
            days = st.number_input(t("p8_retention_days"), min_value=0, value=2555, step=1)
            rationale = st.text_area(t("p8_retention_rationale"))
            if st.form_submit_button(t("p8_create_retention")):
                try:
                    policy_id = create_retention_policy(actor, version=version, retention_days=int(days), rationale=rationale)
                    st.success(f"Retention policy {policy_id} created and audited.")
                except (ValueError, PermissionError) as error:
                    st.error(str(error))
    with deletion_tab:
        try:
            workflows = get_deletion_workflows(actor, purpose="authorised_reporting")
        except PermissionError as error:
            st.error(str(error))
            workflows = []
        if not workflows:
            st.info("No deletion workflows are available in this scope.")
        for workflow in workflows:
            st.markdown(
                f"**{workflow['case_id']}** · {workflow['status'].replace('_', ' ').title()} · "
                f"requested {workflow['requested_at']} by {workflow['requested_by']}"
            )
            st.caption(f"Rationale: {workflow['request_reason']}")
            if workflow["status"] == "PENDING_APPROVAL":
                if st.button(t("p8_approve_deletion"), key=f"approve_deletion_{workflow['id']}"):
                    try:
                        approve_case_deletion(actor, workflow["id"], purpose="authorised_reporting")
                        st.success("Deletion approved and audited. Execution remains a separate action.")
                        st.rerun()
                    except (ValueError, PermissionError) as error:
                        st.error(str(error))
            elif workflow["status"] == "APPROVED":
                due = workflow.get("scheduled_for") or ""
                if due <= datetime.now().isoformat() and st.button(t("p8_execute_deletion"), key=f"execute_deletion_{workflow['id']}"):
                    try:
                        execute_approved_deletion(actor, workflow["id"], purpose="authorised_reporting")
                        st.success("Approved deletion executed and audited.")
                        st.rerun()
                    except (ValueError, PermissionError) as error:
                        st.error(str(error))

elif actor.role == "auditor":
    st.markdown(f"#### {t('p8_audit_heading')}")
    integrity = verify_audit_chain()
    st.success(t("p8_audit_pass")) if integrity else st.error(t("p8_audit_fail"))
    try:
        events = get_security_audit_events(actor, purpose="audit")
    except PermissionError as error:
        st.error(str(error))
        events = []
    for event in events:
        st.write(
            f"{event['occurred_at']} · {event['result']} · {event['action']} · "
            f"{event['resource_type']}:{event['resource_id']} · actor {event['actor_id']}"
        )
        st.caption(f"Purpose: {event.get('purpose') or 'system'} • hash: {event['event_hash'][:16]}…")

else:
    st.info(t("p8_no_role"))
