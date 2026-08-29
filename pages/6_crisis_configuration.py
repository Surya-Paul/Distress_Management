"""Authorised configuration for crisis SLAs, safe contact, and verified services."""

import streamlit as st

from config import SAFE_OUTREACH_CHANNELS, SERVICE_DIRECTORY_TYPES
from src.database import (
    add_service_directory_entry,
    create_spi_threshold_version,
    get_all_cases,
    get_case_safe_contact_protocol,
    get_crisis_workflow_config,
    get_service_directory_entries,
    get_active_spi_threshold_config,
    get_spi_threshold_versions,
    save_case_safe_contact_protocol,
    update_crisis_workflow_config,
    verify_service_directory_entry,
)
from src.translations import t
from src.ui_access import get_active_actor


try:
    actor = get_active_actor()
except Exception as error:
    st.error(f"Configuration access is unavailable: {error}")
    st.stop()
if actor.role not in {"state_administrator", "national_administrator"}:
    st.error("Only State or national administrators may access configuration. Casework roles cannot change shared workflow settings.")
    st.stop()


st.markdown(
    f"""
    <div class="main-header">
        <h1>{t("p6_heading")}</h1>
        <p>{t("p6_subheading")}</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.warning(t("p6_warning"))

config_tab, spi_tab, contact_tab, services_tab = st.tabs([
    "Response times & assigned staff", t("p6_tab_triage_settings"), t("p6_tab_safe_contact"), t("p6_tab_directory")
])

with config_tab:
    current = get_crisis_workflow_config()
    st.caption("An event without a default reviewer is recorded as pending assignment and its internal escalation is blocked until an authorised staff member assigns accountability.")
    with st.form("crisis_config"):
        editor = actor.user_id
        st.caption(f"Verified configuration editor: {editor}")
        self_harm_sla = st.number_input(
            "Response time target for self-harm reports (minutes)",
            min_value=1,
            value=int(current["self_harm_sla_minutes"]),
        )
        safety_sla = st.number_input(
            "Response time target for external safety threats (minutes)",
            min_value=1,
            value=int(current["external_safety_sla_minutes"]),
        )
        self_harm_assignee = st.text_input(
            "Default responsible counsellor", value=current.get("default_self_harm_assignee") or ""
        )
        safety_assignee = st.text_input(
            "Default responsible district safety officer", value=current.get("default_external_safety_assignee") or ""
        )
        if st.form_submit_button("Save workflow configuration"):
            try:
                update_crisis_workflow_config(
                    self_harm_sla, safety_sla, self_harm_assignee, safety_assignee, actor=editor
                )
                st.success("Crisis configuration saved and audited.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

with spi_tab:
    active_spi = get_active_spi_threshold_config()
    st.caption(
        f"Active configuration: {active_spi['version']}. Creating a new version preserves prior settings and applies only to future SPI records. "
        "No SPI or questionnaire total can independently trigger coercive or irreversible action."
    )
    with st.form("spi_threshold_version"):
        editor = actor.user_id
        st.caption(f"Verified SPI configuration editor: {editor}")
        version = st.text_input("New unique version", placeholder="spi-thresholds.v2")
        rationale = st.text_area("Change rationale", placeholder="Why this version is needed and who approved it.")
        feature_cols = st.columns(3)
        with feature_cols[0]:
            physical_weight = st.number_input("Physical-safety weight", 0.0, 100.0, float(active_spi["physical_safety_weight"]))
            wellbeing_weight = st.number_input("Wellbeing weight", 0.0, 100.0, float(active_spi["wellbeing_weight"]))
        with feature_cols[1]:
            service_weight = st.number_input("Service-access weight", 0.0, 100.0, float(active_spi["service_access_weight"]))
            statement_weight = st.number_input("Explicit-statement weight", 0.0, 100.0, float(active_spi["explicit_statement_weight"]))
        with feature_cols[2]:
            change_weight = st.number_input("Comparable-worsening weight", 0.0, 100.0, float(active_spi["recent_change_weight"]))
            unanswered_weight = st.number_input("Unanswered-follow-up weight", 0.0, 100.0, float(active_spi["unanswered_followups_weight"]))
            unanswered_reference = st.number_input("Follow-ups for full contribution", 1, 20, int(active_spi["unanswered_followups_reference"]))
        threshold_cols = st.columns(3)
        with threshold_cols[0]:
            timely = st.number_input("Timely-review threshold", 0.0, 100.0, float(active_spi["timely_review_threshold"]))
            prompt = st.number_input("Prompt-review threshold", 0.0, 100.0, float(active_spi["prompt_review_threshold"]))
        with threshold_cols[1]:
            urgent = st.number_input("Urgent-review threshold", 0.0, 100.0, float(active_spi["urgent_review_threshold"]))
            change_points = st.number_input("Material comparable change", 0.0, 100.0, float(active_spi["material_change_points"]))
        with threshold_cols[2]:
            threat_floor = st.number_input("Reported-threat SPI floor", 0.0, 100.0, float(active_spi["reported_threat_floor"]))
            self_harm_floor = st.number_input("Explicit self-harm statement SPI floor", 0.0, 100.0, float(active_spi["explicit_self_harm_floor"]))
        if st.form_submit_button("Create and activate new follow-up priority version"):
            try:
                create_spi_threshold_version(
                    {
                        "version": version,
                        "physical_safety_weight": physical_weight,
                        "wellbeing_weight": wellbeing_weight,
                        "service_access_weight": service_weight,
                        "explicit_statement_weight": statement_weight,
                        "recent_change_weight": change_weight,
                        "unanswered_followups_weight": unanswered_weight,
                        "unanswered_followups_reference": unanswered_reference,
                        "reported_threat_floor": threat_floor,
                        "explicit_self_harm_floor": self_harm_floor,
                        "timely_review_threshold": timely,
                        "prompt_review_threshold": prompt,
                        "urgent_review_threshold": urgent,
                        "material_change_points": change_points,
                    },
                    rationale,
                    actor=editor,
                )
                st.success("New SPI threshold version activated and audited. Existing interaction scores were not changed.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    with st.expander("Follow-up priority version history", expanded=False):
        for record in get_spi_threshold_versions():
            st.write(
                f"{'✅ Active' if record['active'] else 'Archived'} — **{record['version']}** · "
                f"created by {record['created_by']} · {record['created_at']}"
            )
            st.caption(record["change_rationale"])

with contact_tab:
    # State/national configuration roles must not enumerate individual cases or
    # contact protocols. Case-specific safe-contact setup belongs in a
    # district-scoped casework workflow.
    cases = []
    if not cases:
        st.info("Case-specific safe-contact protocols are intentionally unavailable to aggregate configuration roles.")
    else:
        case_options = {case["case_id"]: case for case in cases}
        case_id = st.selectbox("Opaque case ID", list(case_options))
        existing = get_case_safe_contact_protocol(case_id) or {}
        st.caption("Safe-contact details must be explicit, consented, and minimal. This configuration never initiates contact.")
        with st.form("safe_contact_protocol"):
            editor = actor.user_id
            st.caption(f"Verified protocol editor: {editor}")
            protocol_label = st.text_input("Protocol label", value=existing.get("protocol_label") or "")
            consent = st.checkbox("Informed consent for this safe-contact protocol is recorded", value=bool(existing.get("consent_recorded")))
            allowed = st.multiselect(
                "Permitted channels (SMS is not available)",
                list(SAFE_OUTREACH_CHANNELS),
                default=existing.get("allowed_channels") or [],
            )
            safe_window = st.text_input("Safe contact window or constraint", value=existing.get("safe_contact_window") or "")
            no_third_parties = True
            st.checkbox(
                "Do not contact third parties (required by this workflow)",
                value=True,
                disabled=True,
            )
            maximum_attempts = st.number_input(
                "Maximum human-recorded contact attempts", min_value=1, max_value=3,
                value=int(existing.get("maximum_attempts", 1)),
            )
            retry_minutes = st.number_input(
                "Minimum minutes before a repeat attempt", min_value=0,
                value=int(existing.get("minimum_retry_minutes", 240)),
            )
            enabled = st.checkbox("Enable this protocol", value=bool(existing.get("enabled", False)))
            if st.form_submit_button("Save safe-contact protocol"):
                try:
                    save_case_safe_contact_protocol(
                        case_id, protocol_label, consent, allowed, safe_window, no_third_parties,
                        maximum_attempts, retry_minutes, enabled, actor=editor,
                    )
                    st.success("Safe-contact protocol saved and audited. No outreach was sent.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

with services_tab:
    st.caption("Entries are unverified when added. They become available in the crisis-review directory only after an authorised verifier confirms them.")
    with st.form("add_service_directory_entry"):
        editor = actor.user_id
        st.caption(f"Verified directory editor: {editor}")
        left, right = st.columns(2)
        with left:
            service_type = st.selectbox("Service type", list(SERVICE_DIRECTORY_TYPES))
            service_name = st.text_input("Service name")
            state = st.text_input("State")
        with right:
            district = st.text_input("District (optional for state-wide service)")
            contact_reference = st.text_input("Verified contact reference or authorised directory reference")
            availability_notes = st.text_area("Availability notes (optional)")
        if st.form_submit_button("Add as unverified"):
            try:
                service_id = add_service_directory_entry(
                    service_type, service_name, state, district, contact_reference, availability_notes, actor=editor
                )
                st.success(f"Service entry {service_id} added as unverified and audited.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    entries = get_service_directory_entries()
    if not entries:
        st.info("No local services have been configured.")
    for entry in entries:
        status = "✅ Verified" if entry["verified"] else "⏳ Unverified"
        st.markdown(
            f"**{entry['service_type'].replace('_', ' ').title()} — {entry['service_name']}**  \n"
            f"{entry['state']}{' / ' + entry['district'] if entry.get('district') else ''} • {status}"
        )
        st.caption(f"Contact reference: {entry['contact_reference']}")
        if entry.get("availability_notes"):
            st.caption(entry["availability_notes"])
        if not entry["verified"]:
            with st.form(f"verify_service_{entry['id']}"):
                verifier = actor.user_id
                st.caption(f"Verified service verifier: {verifier}")
                if st.form_submit_button("Mark verified"):
                    try:
                        verify_service_directory_entry(entry["id"], actor=verifier)
                        st.success("Service verified and audit record appended.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
