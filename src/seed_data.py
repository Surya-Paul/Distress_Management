"""Synthetic, non-diagnostic data for a demonstration environment only."""

from datetime import datetime, timedelta

from src.alerts import check_and_create_review_tasks
from src.database import get_connection, insert_case, insert_interaction
from src.scoring import compute_support_priority_indicator


def is_seeded():
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    conn.close()
    return count > 0


def _signals(safety=0, wellbeing=0, service=0, *, threat=False, evidence=None, confidence="medium"):
    return {
        "schema_version": "support_triage.synthetic.v1",
        "physical_safety": {
            "level": safety,
            "reported_concerns": ["Reported concern about attending a hearing"] if safety else [],
            "explicit_threat_or_immediate_danger": threat,
            "status": "detected" if safety else "insufficient_information",
        },
        "wellbeing": {
            "level": wellbeing,
            "reported_indicators": ["Reported worry affecting sleep"] if wellbeing else [],
            "explicit_self_harm_statement": False,
            "status": "detected" if wellbeing else "insufficient_information",
        },
        "service_access": {
            "level": service,
            "reported_barriers": ["Requested help understanding compensation paperwork"] if service else [],
            "status": "detected" if service else "insufficient_information",
        },
        "immediate_self_harm_or_suicide": {"status": "insufficient_information", "explicit_statement": False},
        "evidence": evidence or [],
        "data_quality": {
            "confidence": confidence,
            "limitations": ["Synthetic demonstration record; not a real person or assessment."],
        },
        "suggested_review_urgency": "timely",
    }


def _save_synthetic_interaction(case_id, transcript, channel, timestamp, signals):
    assessment = compute_support_priority_indicator(signals)
    scores = {item["key"]: item["score"] for item in assessment["dimensions"]}
    interaction_id = insert_interaction(
        case_id=case_id,
        transcript=transcript,
        channel=channel,
        support_signals=signals,
        support_priority_indicator=assessment["spi"],
        priority_band=assessment["priority_band"],
        confidence=assessment["confidence"],
        data_quality_limitations=assessment["limitations"],
        evidence=assessment["evidence"],
        physical_safety_score=scores["physical_safety"],
        wellbeing_concern_score=scores["wellbeing"],
        service_access_score=scores["service_access"],
        consent_recorded=True,
        analysis_language="English",
        score_version=assessment["score_version"],
        threshold_version=assessment["threshold_version"],
        model_version=assessment["model_version"],
        feature_set=assessment["feature_set"],
        evidence_references=assessment["evidence_references"],
        trend_status=assessment["trend"]["status"],
        trend_delta=assessment["trend"]["delta"],
        trend_quality_issues=assessment["trend"]["quality_issues"],
        timestamp=timestamp,
    )
    check_and_create_review_tasks(case_id, interaction_id, assessment, signals)


def seed_mock_data():
    """Seed a small, clearly synthetic v2 data set only when the DB is empty."""
    if is_seeded():
        return

    base_time = datetime.now() - timedelta(days=45)
    cases = [
        ("NHAA-DEMO-001", "Maharashtra", "Pune"),
        ("NHAA-DEMO-002", "Rajasthan", "Jaipur"),
        ("NHAA-DEMO-003", "Bihar", "Patna"),
    ]
    for case_id, state, district in cases:
        insert_case(case_id, state, district, base_time.isoformat())

    _save_synthetic_interaction(
        "NHAA-DEMO-001",
        "[Synthetic] The person said they are worried about a hearing and asked for a follow-up at a safe time.",
        "follow_up_call",
        (base_time + timedelta(days=5)).isoformat(),
        _signals(
            wellbeing=0.35,
            evidence=[{"dimension": "wellbeing", "quote": "worried about a hearing", "confidence": "high"}],
        ),
    )
    _save_synthetic_interaction(
        "NHAA-DEMO-002",
        "[Synthetic] The person reported that they had received threats and wants to discuss safe options with a trained worker.",
        "helpline_call",
        (base_time + timedelta(days=20)).isoformat(),
        _signals(
            safety=0.9,
            threat=True,
            evidence=[{"dimension": "physical_safety", "quote": "had received threats", "confidence": "high"}],
        ),
    )
    _save_synthetic_interaction(
        "NHAA-DEMO-003",
        "[Synthetic] The person asked for help understanding compensation paperwork and transport support.",
        "text_message",
        (base_time + timedelta(days=35)).isoformat(),
        _signals(
            service=0.8,
            evidence=[{"dimension": "service_access", "quote": "help understanding compensation paperwork and transport support", "confidence": "high"}],
        ),
    )


# Retained only as historical dashboard context for the demo; not used for triage.
NCRB_PENDING_CASES = {}
