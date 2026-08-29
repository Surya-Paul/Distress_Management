"""Non-diagnostic Support Priority Indicator (SPI) calculations.

SPI orders human review from explicit, evidence-linked support signals. It is not
a clinical instrument, credibility assessment, prediction, or authority for an
outreach, service, legal, compensation, protection, or irreversible action.
"""

from copy import deepcopy

from config import (
    DEFAULT_SPI_THRESHOLD_CONFIG,
    DIMENSION_LABELS,
    SPI_FEATURE_SET,
    SPI_FEATURE_SET_VERSION,
    SUPPORT_PRIORITY_BANDS,
)


CONFIDENCE_VALUES = {"low", "medium", "high"}


def _bounded_number(value, default=0.0):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def normalise_threshold_config(config=None):
    """Validate a versioned SPI configuration before it can be used."""
    result = deepcopy(DEFAULT_SPI_THRESHOLD_CONFIG)
    if config:
        if not isinstance(config, dict):
            raise ValueError("SPI threshold configuration must be an object.")
        result.update({key: value for key, value in config.items() if key in result})
    if not isinstance(result["version"], str) or not result["version"].strip():
        raise ValueError("SPI threshold configuration requires a version.")
    numeric_keys = (
        "physical_safety_weight", "wellbeing_weight", "service_access_weight",
        "explicit_statement_weight", "recent_change_weight", "unanswered_followups_weight",
        "reported_threat_floor", "explicit_self_harm_floor", "timely_review_threshold",
        "prompt_review_threshold", "urgent_review_threshold", "material_change_points",
    )
    for key in numeric_keys:
        try:
            result[key] = float(result[key])
        except (TypeError, ValueError) as error:
            raise ValueError(f"SPI configuration field {key} must be numeric.") from error
        if not 0 <= result[key] <= 100:
            raise ValueError(f"SPI configuration field {key} must be between 0 and 100.")
    try:
        result["unanswered_followups_reference"] = int(result["unanswered_followups_reference"])
    except (TypeError, ValueError) as error:
        raise ValueError("SPI unanswered-follow-up reference must be a whole number.") from error
    if result["unanswered_followups_reference"] < 1:
        raise ValueError("SPI unanswered-follow-up reference must be at least one.")
    weights = (
        "physical_safety_weight", "wellbeing_weight", "service_access_weight",
        "explicit_statement_weight", "recent_change_weight", "unanswered_followups_weight",
    )
    if sum(result[key] for key in weights) > 100:
        raise ValueError("SPI feature weights may not total more than 100.")
    if not result["timely_review_threshold"] <= result["prompt_review_threshold"] <= result["urgent_review_threshold"]:
        raise ValueError("SPI review thresholds must progress from timely to prompt to urgent.")
    return result


def get_priority_band(spi, threshold_config=None):
    """Return configurable review-timeliness metadata for a 0–100 SPI."""
    spi = max(0.0, min(100.0, float(spi or 0)))
    config = normalise_threshold_config(threshold_config)
    timely, prompt, urgent = (
        config["timely_review_threshold"],
        config["prompt_review_threshold"],
        config["urgent_review_threshold"],
    )
    bands = [
        {**SUPPORT_PRIORITY_BANDS[0], "min": 0, "max": timely - 0.1},
        {**SUPPORT_PRIORITY_BANDS[1], "min": timely, "max": prompt - 0.1},
        {**SUPPORT_PRIORITY_BANDS[2], "min": prompt, "max": urgent - 0.1},
        {**SUPPORT_PRIORITY_BANDS[3], "min": urgent, "max": 100},
    ]
    return next((band for band in bands if band["min"] <= spi <= band["max"]), bands[-1])


def _legacy_signals_to_dimensions(signals):
    """Read old synthetic records without presenting them as clinical data."""
    threat = bool(signals.get("threat_mentions", False))
    physical = max(_bounded_number(signals.get("fear")), 0.85 if threat else 0.0)
    wellbeing = max(
        _bounded_number(signals.get("hopelessness")),
        _bounded_number(signals.get("anxiety_indicators")),
        _bounded_number(signals.get("sleep_disturbance")),
        _bounded_number(signals.get("isolation_language")),
    )
    status = lambda level: "detected" if level else "insufficient_information"
    return {
        "physical_safety": {
            "level": physical, "reported_concerns": ["Reported threat or safety concern"] if threat else [],
            "explicit_threat_or_immediate_danger": threat, "status": status(physical),
        },
        "wellbeing": {
            "level": wellbeing, "reported_indicators": [], "explicit_self_harm_statement": False,
            "status": status(wellbeing),
        },
        "service_access": {"level": 0.0, "reported_barriers": [], "status": "insufficient_information"},
        "immediate_self_harm_or_suicide": {"status": "insufficient_information", "explicit_statement": False},
        "evidence": [],
        "data_quality": {
            "confidence": "low",
            "limitations": ["This legacy synthetic record was converted from a retired prototype format."],
        },
    }


def _dimension(signals, key):
    if not isinstance(signals, dict):
        signals = {}
    if key in signals and isinstance(signals[key], dict):
        return signals[key]
    return _legacy_signals_to_dimensions(signals)[key]


def _supported_level(dimension):
    """Use a level only where strict extraction identified direct support."""
    if not isinstance(dimension, dict) or dimension.get("status") != "detected":
        return 0.0
    return _bounded_number(dimension.get("level"))


def _validated_unanswered_count(value):
    if type(value) is bool:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def assess_spi_trend(current, history, threshold_config=None):
    """Interpret change only when scores are genuinely comparable.

    Missing scores, low-confidence extraction, a changed channel, a changed
    language, or score-version changes prevent a numerical delta from being
    presented as deterioration.
    """
    config = normalise_threshold_config(threshold_config)
    history = history if isinstance(history, list) else []
    previous = next(
        (row for row in history if isinstance(row, dict) and row.get("support_priority_indicator") is not None),
        None,
    )
    result = {
        "status": "not_comparable", "comparable": False, "delta": None,
        "quality_issues": [], "summary": "No comparable prior SPI is available.",
    }
    if not isinstance(current, dict) or current.get("support_priority_indicator") is None:
        result.update(quality_issues=["missing_current_score"], summary="The current SPI is missing, so no trend was calculated.")
        return result
    if previous is None:
        result["quality_issues"] = ["no_prior_score"]
        return result
    issues = []
    try:
        current_score = float(current["support_priority_indicator"])
        prior_score = float(previous["support_priority_indicator"])
    except (TypeError, ValueError):
        issues.append("missing_score")
        current_score = prior_score = 0.0
    for prefix, record in (("current", current), ("prior", previous)):
        if record.get("confidence") not in {"medium", "high"}:
            issues.append(f"low_confidence_{prefix}_extraction")
        if not record.get("channel"):
            issues.append(f"missing_{prefix}_channel")
        if not record.get("analysis_language"):
            issues.append(f"missing_{prefix}_language")
    if current.get("channel") and previous.get("channel") and current["channel"] != previous["channel"]:
        issues.append("channel_changed")
    if current.get("analysis_language") and previous.get("analysis_language") and current["analysis_language"] != previous["analysis_language"]:
        issues.append("language_changed")
    current_version = current.get("score_version") or current.get("threshold_version")
    previous_version = previous.get("score_version") or previous.get("threshold_version")
    if current_version and previous_version and current_version != previous_version:
        issues.append("score_version_changed")
    if issues:
        result.update(
            quality_issues=list(dict.fromkeys(issues)),
            summary="Trend not interpreted because data quality or collection context changed.",
        )
        return result
    delta = round(current_score - prior_score, 1)
    if delta >= config["material_change_points"]:
        status, summary = "worsening", "Comparable SPI increased materially; a trained reviewer should examine the source evidence."
    elif delta <= -config["material_change_points"]:
        status, summary = "improving", "Comparable SPI decreased materially; this does not establish that support is no longer needed."
    else:
        status, summary = "stable", "Comparable SPI did not change materially."
    return {"status": status, "comparable": True, "delta": delta, "quality_issues": [], "summary": summary}


def compute_support_priority_indicator(signals, *, threshold_config=None, trend=None, unanswered_follow_up_count=0):
    """Calculate transparent, versioned SPI features for human review.

    Only strict-extraction signals marked ``detected`` contribute. Validated
    PHQ-9/GAD-7 totals are intentionally not an SPI feature.
    """
    config = normalise_threshold_config(threshold_config)
    physical = _dimension(signals, "physical_safety")
    wellbeing = _dimension(signals, "wellbeing")
    service = _dimension(signals, "service_access")
    self_harm = signals.get("immediate_self_harm_or_suicide", {}) if isinstance(signals, dict) else {}
    physical_level, wellbeing_level, service_level = (
        _supported_level(physical), _supported_level(wellbeing), _supported_level(service)
    )
    physical_score, wellbeing_score, service_score = (
        round(physical_level * 100, 1), round(wellbeing_level * 100, 1), round(service_level * 100, 1)
    )
    explicit_danger = physical.get("status") == "detected" and physical.get("explicit_threat_or_immediate_danger") is True
    explicit_self_harm = (
        self_harm.get("status") == "detected" and self_harm.get("explicit_statement") is True
    ) or (
        wellbeing.get("status") == "detected" and wellbeing.get("explicit_self_harm_statement") is True
    )
    trend = trend if isinstance(trend, dict) else {
        "status": "not_calculated", "comparable": False, "delta": None,
        "quality_issues": ["trend_not_calculated"], "summary": "Trend has not been calculated yet.",
    }
    unanswered_count = _validated_unanswered_count(unanswered_follow_up_count)
    unanswered_level = min(1.0, unanswered_count / config["unanswered_followups_reference"])
    contributions = {
        "explicit_supported_physical_safety": round(physical_level * config["physical_safety_weight"], 1),
        "explicit_supported_wellbeing": round(wellbeing_level * config["wellbeing_weight"], 1),
        "unmet_service_needs": round(service_level * config["service_access_weight"], 1),
        "reported_threat_or_explicit_statement": round((1.0 if explicit_danger or explicit_self_harm else 0.0) * config["explicit_statement_weight"], 1),
        "comparable_recent_worsening": round((1.0 if trend.get("comparable") is True and trend.get("status") == "worsening" else 0.0) * config["recent_change_weight"], 1),
        "unanswered_follow_ups": round(unanswered_level * config["unanswered_followups_weight"], 1),
    }
    spi = sum(contributions.values())
    if explicit_danger:
        spi = max(spi, config["reported_threat_floor"])
    if explicit_self_harm:
        spi = max(spi, config["explicit_self_harm_floor"])
    spi = round(max(0.0, min(100.0, spi)), 1)

    quality = signals.get("data_quality", {}) if isinstance(signals, dict) else {}
    confidence = quality.get("confidence", "low") if isinstance(quality, dict) else "low"
    confidence = confidence if confidence in CONFIDENCE_VALUES else "low"
    limitations = quality.get("limitations", []) if isinstance(quality, dict) else []
    limitations = limitations if isinstance(limitations, list) else [str(limitations)]
    if not limitations:
        limitations = ["Automated extraction may miss context; a trained reviewer must interpret this record."]
    trend_issues = trend.get("quality_issues", []) if isinstance(trend.get("quality_issues", []), list) else []
    if trend_issues and trend.get("status") in {"not_comparable", "not_calculated"}:
        limitations.append("Trend was not used: " + ", ".join(str(item).replace("_", " ") for item in trend_issues) + ".")
    evidence = signals.get("evidence", []) if isinstance(signals, dict) else []
    evidence = [item for item in evidence if isinstance(item, dict) and item.get("quote")][:10] if isinstance(evidence, list) else []
    if not evidence:
        limitations.append("No short evidence excerpt was available; review the source notes before acting.")
    band = get_priority_band(spi, config)
    dimensions = [
        {"key": "physical_safety", "label": DIMENSION_LABELS["physical_safety"], "score": physical_score, "reported_items": physical.get("reported_concerns", [])},
        {"key": "wellbeing", "label": DIMENSION_LABELS["wellbeing"], "score": wellbeing_score, "reported_items": wellbeing.get("reported_indicators", [])},
        {"key": "service_access", "label": DIMENSION_LABELS["service_access"], "score": service_score, "reported_items": service.get("reported_barriers", [])},
    ]
    return {
        "spi": spi, "priority_band": band["label"], "color": band["color"], "emoji": band["emoji"],
        "confidence": confidence, "limitations": list(dict.fromkeys(limitations))[:8], "evidence": evidence,
        "evidence_references": [item["id"] for item in evidence if isinstance(item.get("id"), str)],
        "dimensions": dimensions, "contributions": contributions, "unanswered_follow_up_count": unanswered_count,
        "trend": trend, "explicit_danger": explicit_danger, "explicit_self_harm_statement": explicit_self_harm,
        "score_version": f"spi-calculation.v2@{config['version']}", "threshold_version": config["version"],
        "review_thresholds": {
            "timely": config["timely_review_threshold"], "prompt": config["prompt_review_threshold"],
            "urgent": config["urgent_review_threshold"], "material_change": config["material_change_points"],
        },
        "model_version": (signals.get("schema_version") if isinstance(signals, dict) else None) or "unavailable",
        "feature_set": SPI_FEATURE_SET, "feature_set_version": SPI_FEATURE_SET_VERSION,
        "model_note": (
            "This is only an estimate to help staff decide what to look at next. "
            "It is not a medical diagnosis, a judgement about truthfulness, or an instruction to act. "
            "No score on its own can be used to force an action or make a decision that cannot be undone."
        ),
    }
