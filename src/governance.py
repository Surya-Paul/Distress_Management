"""Pre-deployment evaluation and governance logic.

Enforces multi-disciplinary domain sign-offs and offline evaluation 
thresholds before promoting any model or prompt version to production.
"""

import json
from src.database import (
    get_domain_signoffs,
    get_evaluation_runs,
    get_model_versions,
    insert_evaluation_run,
    insert_model_version,
    update_domain_signoff,
    update_model_status,
)
from config import GO_NO_GO_THRESHOLDS, GOVERNANCE_DOMAINS


class GovernanceValidationError(Exception):
    """Raised when a deployment attempt fails governance checks."""


def register_new_version(version: str, model_card_url: str, data_sheet_url: str):
    """Register a new model/prompt version for staging."""
    insert_model_version(version, model_card_url, data_sheet_url)


def simulate_offline_evaluation(version: str):
    """Simulate offline evaluation against clinician-reviewed dataset."""
    # In a real system, this would trigger an evaluation pipeline against 
    # de-identified, consented data. Here we mock the output.
    metrics = {
        "global": {
            "sensitivity": 0.92,
            "precision": 0.88,
            "calibration": 0.95,
            "false_negative_urgent": 0.005,
            "false_alert_burden": 0.10,
        },
        "operational": {
            "time_to_human_ack_minutes": 14,
            "intervention_completion_rate": 0.85,
        },
        "equity_fairness": {
            "language": {"en": 0.92, "hi": 0.91, "bn": 0.90, "ta": 0.89},
            "gender": {"female": 0.93, "male": 0.91, "non_binary": 0.92},
            "disability": {"reported": 0.90, "none": 0.92},
        }
    }
    insert_evaluation_run(version, metrics)
    return metrics


def promote_to_production(version: str):
    """Promote a version to production if all governance criteria are met."""
    
    # 1. Check if all domains have signed off
    signoffs = get_domain_signoffs(version)
    if not signoffs:
        raise GovernanceValidationError("No sign-offs found for this version.")
    
    pending_or_rejected = [s for s in signoffs if s["status"] != "APPROVED"]
    if pending_or_rejected:
        domains = [s["domain"] for s in pending_or_rejected]
        raise GovernanceValidationError(f"Cannot deploy. Missing or rejected approvals from: {', '.join(domains)}")
        
    # 2. Check offline evaluation metrics against GO/NO-GO thresholds
    evals = get_evaluation_runs(version)
    if not evals:
        raise GovernanceValidationError("Cannot deploy without an offline evaluation run.")
    
    latest_eval = json.loads(evals[0]["metrics_json"])
    glob = latest_eval.get("global", {})
    
    if glob.get("sensitivity", 0) < GO_NO_GO_THRESHOLDS["min_sensitivity"]:
        raise GovernanceValidationError("Sensitivity falls below the go/no-go threshold.")
    if glob.get("precision", 0) < GO_NO_GO_THRESHOLDS["min_precision"]:
        raise GovernanceValidationError("Precision falls below the go/no-go threshold.")
    if glob.get("false_negative_urgent", 1) > GO_NO_GO_THRESHOLDS["max_false_negative_urgent"]:
        raise GovernanceValidationError("False negative rate for urgent signals exceeds the go/no-go threshold.")
    if glob.get("false_alert_burden", 1) > GO_NO_GO_THRESHOLDS["max_false_alert_burden"]:
        raise GovernanceValidationError("False alert burden exceeds the go/no-go threshold.")

    # 3. Promote!
    # Demote current active version if any
    versions = get_model_versions()
    for v in versions:
        if v["status"] == "PRODUCTION":
            update_model_status(v["version"], "DEPRECATED")
            
    update_model_status(version, "PRODUCTION")


def rollback_version(version: str):
    """Roll back a production version in case of incidents."""
    update_model_status(version, "ROLLED_BACK")
