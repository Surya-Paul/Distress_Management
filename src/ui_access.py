"""Streamlit adapter for a server-authenticated access context.

The selector is deliberately labelled local-development only. A production host
must verify a session/token outside Streamlit and inject immutable claims into
``st.session_state['verified_access_context']``; users must not choose a role
or scope for themselves in production.
"""

import os

import streamlit as st

from config import DEPLOYMENT_ENVIRONMENT, ROLE_NAMES
from src.privacy_architecture import AccessContext, SecurityConfigurationError


PURPOSE_CHOICES = [
    "case_review", "crisis_review", "consent_management", "safe_contact", "screening",
    "service_coordination", "authorised_reporting", "audit", "security_investigation",
]


def get_active_actor() -> AccessContext:
    actor = st.session_state.get("verified_access_context")
    if isinstance(actor, AccessContext):
        return actor
    if DEPLOYMENT_ENVIRONMENT in {"production", "staging"}:
        raise SecurityConfigurationError("No verified server-side access context was supplied.")
    # Local development/test only. It is not an authentication mechanism.
    return AccessContext(
        user_id=os.environ.get("NHAA_DEMO_OPERATOR_ID", "OP-LOCAL-COUNSELLOR"),
        role=os.environ.get("NHAA_DEMO_ROLE", "counsellor"),
        state=os.environ.get("NHAA_DEMO_STATE", "Maharashtra"),
        district=os.environ.get("NHAA_DEMO_DISTRICT", "Pune"),
        purposes=frozenset(PURPOSE_CHOICES),
    )


def configure_local_development_actor():
    """Render a visible non-production stand-in for verified identity claims."""
    if DEPLOYMENT_ENVIRONMENT in {"production", "staging"}:
        return get_active_actor()
    st.caption("Demo login only — a live system verifies your identity automatically.")
    operator_id = st.text_input("Staff ID", value=st.session_state.get("operator_id", "OP-LOCAL-COUNSELLOR"))
    role = st.selectbox("Your role (demo only)", ROLE_NAMES, index=ROLE_NAMES.index(st.session_state.get("operator_role", "counsellor")))
    state = st.text_input("State (demo only)", value=st.session_state.get("operator_state", "Maharashtra"))
    district = st.text_input("District (demo only)", value=st.session_state.get("operator_district", "Pune"))
    purposes = st.multiselect("What you can do (demo only)", PURPOSE_CHOICES, default=st.session_state.get("operator_purposes", PURPOSE_CHOICES))
    actor = AccessContext(
        user_id=operator_id.strip() or "OP-LOCAL-COUNSELLOR", role=role,
        state=state.strip() or None, district=district.strip() or None, purposes=frozenset(purposes),
    )
    st.session_state.update({
        "operator_id": actor.user_id, "operator_role": role, "operator_state": state,
        "operator_district": district, "operator_purposes": list(actor.purposes),
        "verified_access_context": actor,
    })
    return actor
