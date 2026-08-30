"""Create human-review tasks from non-diagnostic support signals.

No task created here contacts a survivor, changes a record, or triggers a
protection, counselling, legal, compensation, or rehabilitation action.
"""

from config import (
    INTERVENTION_CATEGORIES,
    PROMPT_REVIEW_THRESHOLD,
    URGENT_REVIEW_THRESHOLD,
)
from src.database import create_crisis_event, insert_alert


def _create_task(case_id, interaction_id, level, task_type, reason, suggestion):
    insert_alert(
        case_id=case_id,
        interaction_id=interaction_id,
        alert_level=level,
        alert_type=task_type,
        reason=reason,
        recommended_intervention=suggestion,
    )
    return {
        "alert_level": level,
        "alert_type": task_type,
        "reason": reason,
        "intervention": suggestion,
    }


def _priority_level(score, urgent_threshold=URGENT_REVIEW_THRESHOLD):
    return "URGENT" if score >= urgent_threshold else "PRIORITY"


def _format_intervention(dimension):
    categories = INTERVENTION_CATEGORIES.get(dimension, [])
    if not categories:
        return ""
    labels = [cat.replace('_', ' ').capitalize() for cat in categories]
    return f"Suggested for consideration: {', '.join(labels)}"


def _evidence_for_signal(signals, signal_name):
    """Select only evidence linked to the high-priority source signal."""
    target_aliases = {
        "immediate_self_harm_or_suicide": {"immediate_self_harm_or_suicide", "wellbeing"},
        "physical_safety": {"physical_safety"},
    }
    allowed = target_aliases[signal_name]
    return [
        item for item in signals.get("evidence", [])
        if isinstance(item, dict) and item.get("signal", item.get("dimension")) in allowed
    ]


def create_crisis_workflow_events(case_id, interaction_id, assessment, signals):
    """Create separate crisis pathways for explicit self-harm and external threats.

    This only creates auditable, internal review events. It does not contact a
    survivor, send an SMS, notify a third party, or start a service intervention.
    """
    events = []
    context_snapshot = {
        "support_priority_indicator": assessment.get("spi"),
        "priority_band": assessment.get("priority_band"),
        "confidence": assessment.get("confidence"),
        "limitations": assessment.get("limitations", []),
        "contact_preferences": signals.get("contact_preferences", {}),
        "model_note": assessment.get("model_note"),
    }
    self_harm = signals.get("immediate_self_harm_or_suicide", {})
    if assessment.get("explicit_self_harm_statement") and self_harm.get("status") == "detected":
        events.append(
            create_crisis_event(
                case_id,
                interaction_id,
                "SELF_HARM_CONCERN",
                "URGENT",
                _evidence_for_signal(signals, "immediate_self_harm_or_suicide"),
                context_snapshot,
            )
        )

    safety = signals.get("physical_safety", {})
    if assessment.get("explicit_danger") and safety.get("status") == "detected":
        events.append(
            create_crisis_event(
                case_id,
                interaction_id,
                "EXTERNAL_SAFETY_THREAT",
                "URGENT",
                _evidence_for_signal(signals, "physical_safety"),
                context_snapshot,
            )
        )
    return events


def check_and_create_review_tasks(case_id, interaction_id, assessment, signals):
    """Create dimension-specific review tasks for trained human staff.

    A task represents a need to review information. It must never be interpreted
    as a finding, diagnosis, or instruction to take action without human review.
    """
    tasks = []
    dimensions = {item["key"]: item for item in assessment.get("dimensions", [])}
    safety = dimensions.get("physical_safety", {})
    wellbeing = dimensions.get("wellbeing", {})
    service = dimensions.get("service_access", {})
    thresholds = assessment.get("review_thresholds", {})
    prompt_threshold = thresholds.get("prompt", PROMPT_REVIEW_THRESHOLD)
    urgent_threshold = thresholds.get("urgent", URGENT_REVIEW_THRESHOLD)

    if assessment.get("explicit_danger") or safety.get("score", 0) >= prompt_threshold:
        tasks.append(
            _create_task(
                case_id,
                interaction_id,
                "URGENT" if assessment.get("explicit_danger") else _priority_level(safety.get("score", 0), urgent_threshold),
                "PHYSICAL_SAFETY",
                (
                    "A reported physical-safety concern needs trained human review. "
                    "This task does not establish that danger is present."
                ),
                _format_intervention("physical_safety"),
            )
        )

    if assessment.get("explicit_self_harm_statement") or wellbeing.get("score", 0) >= urgent_threshold:
        tasks.append(
            _create_task(
                case_id,
                interaction_id,
                "URGENT",
                "WELLBEING",
                (
                    "The interaction includes a reported urgent wellbeing concern that needs trained human review. "
                    "It is not a diagnosis or assessment of intent."
                ),
                _format_intervention("wellbeing"),
            )
        )

    if service.get("score", 0) >= prompt_threshold:
        tasks.append(
            _create_task(
                case_id,
                interaction_id,
                _priority_level(service.get("score", 0), urgent_threshold),
                "SERVICE_ACCESS",
                "A reported barrier to support or services needs trained human review.",
                _format_intervention("service_access"),
            )
        )

    if not tasks and assessment.get("trend", {}).get("comparable") and assessment.get("trend", {}).get("status") == "worsening":
        tasks.append(
            _create_task(
                case_id,
                interaction_id,
                "PRIORITY",
                "TREND",
                (
                    "The support-priority estimate increased materially from the prior interaction. "
                    "Review source notes and data-quality limitations before deciding whether to follow up."
                ),
                _format_intervention("trend"),
            )
        )
    return tasks
