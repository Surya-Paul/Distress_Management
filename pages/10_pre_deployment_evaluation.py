"""Pre-deployment evaluation and governance dashboard.

This page is the gateway for a model or prompt version to go to production.
It tracks the offline evaluation performance (sensitivity, equity fairness) 
and enforces multi-disciplinary domain sign-offs (clinical, legal, etc.).
"""

import json
import streamlit as st
import pandas as pd
from datetime import datetime

from src.translations import t

from config import DEPLOYMENT_MODE, GOVERNANCE_DOMAINS, GO_NO_GO_THRESHOLDS
from src.database import (
    get_domain_signoffs,
    get_evaluation_runs,
    get_model_versions,
    update_domain_signoff,
    insert_incident,
    get_incidents,
)
from src.governance import (
    register_new_version,
    simulate_offline_evaluation,
    promote_to_production,
    rollback_version,
    GovernanceValidationError,
)


st.markdown(f"""
    <div class="main-header">
        <h1>{t("p10_heading")}</h1>
        <p>{t("p10_subheading")}</p>
    </div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="safety-note" style="margin-bottom: 1.5rem;">
    <strong>Current Mode:</strong> {DEPLOYMENT_MODE}<br>
    All production models must pass clinical, survivor-advocate, legal, child-protection, 
    security, privacy, and district-operations review against offline consented data before deployment.
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_registry, tab_eval, tab_signoffs, tab_incidents = st.tabs([
    t("p10_tab_registry"), 
    t("p10_tab_eval"),
    t("p10_tab_signoffs"),
    t("p10_tab_incidents")
])

versions = get_model_versions()
version_names = [v["version"] for v in versions]

# ========================= TAB 1: MODEL REGISTRY =========================
with tab_registry:
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Register a new AI version")
        with st.form("register_version"):
            new_v = st.text_input("Version ID (e.g., triage-llm-v1.2)")
            mc_url = st.text_input("Model Card URL", value="https://internal/models/card")
            ds_url = st.text_input("Data Sheet URL", value="https://internal/data/sheet")
            if st.form_submit_button("Register for Staging"):
                if new_v:
                    register_new_version(new_v, mc_url, ds_url)
                    st.success(f"Version {new_v} registered. Pending evaluation.")
                    st.rerun()

    with col2:
        st.subheader("Active Registry")
        for v in versions:
            status_color = {
                "STAGING": "grey", 
                "PILOT": "blue", 
                "PRODUCTION": "green", 
                "DEPRECATED": "orange",
                "ROLLED_BACK": "red"
            }.get(v["status"], "grey")
            
            with st.expander(f"**{v['version']}**  ({v['status']})", expanded=(v['status'] == 'PRODUCTION')):
                st.write(f"**Status:** :{status_color}[{v['status']}]")
                st.write(f"**Created:** {v['created_at']}")
                st.write(f"**[Model Card]({v['model_card_url']})** • **[Data Sheet]({v['data_sheet_url']})**")
                
                if v["status"] == "PRODUCTION":
                    if st.button("🚨 Roll back to previous version", key=f"rb_{v['version']}", type="primary"):
                        rollback_version(v["version"])
                        st.warning(f"{v['version']} has been rolled back.")
                        st.rerun()


# ========================= TAB 2: EVALUATION & EQUITY =========================
with tab_eval:
    st.subheader("Test results")
    st.caption("Evaluation against clinician-reviewed, consented, de-identified data.")
    
    if not version_names:
        st.info("No models registered.")
    else:
        eval_v = st.selectbox("Select Version to Review", version_names, key="eval_version")
        runs = get_evaluation_runs(eval_v)
        
        if not runs:
            st.warning("No offline evaluation recorded for this version.")
            if st.button("▶️ Run Offline Evaluation Simulation"):
                simulate_offline_evaluation(eval_v)
                st.success("Simulation complete.")
                st.rerun()
        else:
            metrics = json.loads(runs[0]["metrics_json"])
            st.write(f"**Ran at:** {runs[0]['ran_at']}")
            
            st.markdown("#### Global Performance & Go/No-Go Criteria")
            g = metrics.get("global", {})
            g_cols = st.columns(4)
            
            def metric_display(col, label, val, threshold, is_min=True):
                passed = (val >= threshold) if is_min else (val <= threshold)
                icon = "✅" if passed else "❌"
                col.metric(label, f"{val:.2f} {icon}", help=f"Threshold: {'≥' if is_min else '≤'} {threshold}")
                
            with g_cols[0]:
                metric_display(st, "Sensitivity", g.get("sensitivity", 0), GO_NO_GO_THRESHOLDS["min_sensitivity"], True)
            with g_cols[1]:
                metric_display(st, "Precision", g.get("precision", 0), GO_NO_GO_THRESHOLDS["min_precision"], True)
            with g_cols[2]:
                metric_display(st, "FN Rate (Urgent)", g.get("false_negative_urgent", 1), GO_NO_GO_THRESHOLDS["max_false_negative_urgent"], False)
            with g_cols[3]:
                metric_display(st, "False Alert Burden", g.get("false_alert_burden", 1), GO_NO_GO_THRESHOLDS["max_false_alert_burden"], False)
                
            st.divider()
            st.markdown("#### Equity & Fairness Matrix")
            st.caption("Sensitivity breakdowns across demographic and operational slices.")
            eq = metrics.get("equity_fairness", {})
            
            eq_cols = st.columns(3)
            with eq_cols[0]:
                st.write("**Language**")
                st.dataframe(pd.DataFrame(list(eq.get("language", {}).items()), columns=["Language", "Sensitivity"]))
            with eq_cols[1]:
                st.write("**Gender**")
                st.dataframe(pd.DataFrame(list(eq.get("gender", {}).items()), columns=["Gender", "Sensitivity"]))
            with eq_cols[2]:
                st.write("**Disability**")
                st.dataframe(pd.DataFrame(list(eq.get("disability", {}).items()), columns=["Status", "Sensitivity"]))


# ========================= TAB 3: DOMAIN SIGN-OFFS =========================
with tab_signoffs:
    st.subheader("Approval checklist")
    if not version_names:
        st.info("No models registered.")
    else:
        sign_v = st.selectbox("Select Version", version_names, key="sign_version")
        signoffs = get_domain_signoffs(sign_v)
        
        st.markdown(f"**Sign-offs for {sign_v}**")
        
        for s in signoffs:
            dom = s["domain"]
            stat = s["status"]
            color = "green" if stat == "APPROVED" else ("red" if stat == "REJECTED" else "grey")
            
            with st.expander(f":{color}[{stat}] • {dom.replace('_', ' ').title()}", expanded=(stat == "PENDING")):
                st.write(f"**Reviewer:** {s['reviewer'] or 'Unassigned'}")
                st.write(f"**Notes:** {s['notes'] or 'None'}")
                st.write(f"**Last Updated:** {s['updated_at']}")
                
                with st.form(f"form_{dom}"):
                    new_stat = st.radio("Decision", ["PENDING", "APPROVED", "REJECTED"], index=["PENDING", "APPROVED", "REJECTED"].index(stat), horizontal=True)
                    reviewer = st.text_input("Reviewer ID", value=s['reviewer'] or "")
                    notes = st.text_area("Review Notes", value=s['notes'] or "")
                    if st.form_submit_button("Update Sign-off"):
                        update_domain_signoff(sign_v, dom, new_stat, reviewer, notes)
                        st.rerun()
                        
        st.divider()
        if st.button("🚀 Approve for live use", type="primary", use_container_width=True):
            try:
                promote_to_production(sign_v)
                st.success(f"{sign_v} has been successfully promoted to PRODUCTION!")
                st.balloons()
            except GovernanceValidationError as e:
                st.error(f"**Deployment Blocked:** {e}")


# ========================= TAB 4: INCIDENTS & DRIFT =========================
with tab_incidents:
    st.subheader("Report an issue")
    if version_names:
        with st.form("log_incident"):
            inc_v = st.selectbox("Version", version_names)
            inc_type = st.selectbox("Type", ["Data Drift", "False Negative Escalation", "System Latency", "Fairness Degradation"])
            desc = st.text_area("Description")
            reporter = st.text_input("Reported By")
            if st.form_submit_button("Log Incident"):
                insert_incident(inc_v, inc_type, desc, reporter)
                st.success("Incident logged.")
                st.rerun()
                
    st.divider()
    st.write("**Recent Incidents**")
    incidents = get_incidents()
    for inc in incidents:
        st.markdown(f"**{inc['reported_at']}** | Version: `{inc['version']}` | **{inc['incident_type']}**")
        st.write(f"> {inc['description']}")
        st.caption(f"Reported by: {inc['reported_by']}")
