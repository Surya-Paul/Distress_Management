"""Consent-gated scoring for complete, validated PHQ-9 and GAD-7 questionnaires.

This module intentionally does *not* diagnose anyone, interpret credibility, or
feed a score into the Support Priority Indicator (SPI).  A total is available
only after the application's exact, versioned questions have been administered,
screening consent is recorded, and every response is provided.  A respondent
may skip any item; a skipped item produces an incomplete record rather than an
estimated or imputed score.
"""

from copy import deepcopy


SKIPPED = "skipped"
RESPONSE_OPTIONS = {
    0: "Not at all",
    1: "Several days",
    2: "More than half the days",
    3: "Nearly every day",
}


INSTRUMENTS = {
    "PHQ-9": {
        "instrument_version": "phq-9.canonical.en.v1",
        "timeframe": "Over the last 2 weeks, how often have you been bothered by any of the following problems?",
        "maximum_score": 27,
        "items": [
            ("PHQ9_1", "Little interest or pleasure in doing things"),
            ("PHQ9_2", "Feeling down, depressed, or hopeless"),
            ("PHQ9_3", "Trouble falling or staying asleep, or sleeping too much"),
            ("PHQ9_4", "Feeling tired or having little energy"),
            ("PHQ9_5", "Poor appetite or overeating"),
            ("PHQ9_6", "Feeling bad about yourself — or that you are a failure or have let yourself or your family down"),
            ("PHQ9_7", "Trouble concentrating on things, such as reading the newspaper or watching television"),
            ("PHQ9_8", "Moving or speaking so slowly that other people could have noticed? Or the opposite — being so fidgety or restless that you have been moving around a lot more than usual"),
            ("PHQ9_9", "Thoughts that you would be better off dead or of hurting yourself in some way"),
        ],
    },
    "GAD-7": {
        "instrument_version": "gad-7.canonical.en.v1",
        "timeframe": "Over the last 2 weeks, how often have you been bothered by the following problems?",
        "maximum_score": 21,
        "items": [
            ("GAD7_1", "Feeling nervous, anxious, or on edge"),
            ("GAD7_2", "Not being able to stop or control worrying"),
            ("GAD7_3", "Worrying too much about different things"),
            ("GAD7_4", "Trouble relaxing"),
            ("GAD7_5", "Being so restless that it is hard to sit still"),
            ("GAD7_6", "Becoming easily annoyed or irritable"),
            ("GAD7_7", "Feeling afraid as if something awful might happen"),
        ],
    },
}


class ScreeningValidationError(ValueError):
    """Raised when a screening request is incomplete or not the exact instrument."""


def get_instrument(instrument):
    """Return a copy of the approved question set for a screening form."""
    if instrument not in INSTRUMENTS:
        raise ScreeningValidationError("Only PHQ-9 or GAD-7 are supported.")
    definition = deepcopy(INSTRUMENTS[instrument])
    definition["instrument"] = instrument
    definition["items"] = [
        {"id": item_id, "text": text} for item_id, text in definition["items"]
    ]
    return definition


def _require_exact_questions(instrument, questions_administered):
    """Reject changed, reordered, or partial item text instead of scoring it."""
    expected = get_instrument(instrument)["items"]
    if questions_administered != expected:
        raise ScreeningValidationError(
            "A total can be calculated only after this application's complete, exact versioned question set is administered."
        )


def _validate_responses(instrument, responses):
    if not isinstance(responses, dict):
        raise ScreeningValidationError("Responses must be an item-ID to response mapping.")
    item_ids = [item[0] for item in INSTRUMENTS[instrument]["items"]]
    if set(responses) != set(item_ids):
        raise ScreeningValidationError("Responses must contain every approved item exactly once; use 'skipped' for a skipped item.")
    normalized = {}
    for item_id in item_ids:
        response = responses[item_id]
        if response == SKIPPED or response is None:
            normalized[item_id] = SKIPPED
        elif type(response) is int and response in RESPONSE_OPTIONS:
            normalized[item_id] = response
        else:
            raise ScreeningValidationError(
                f"{item_id} must be 0, 1, 2, 3, or 'skipped'; booleans and free text are not valid responses."
            )
    return normalized


def score_validated_screening(*, instrument, questions_administered, responses, consent_recorded):
    """Return a non-diagnostic questionnaire record with an exact, complete total.

    No response is imputed.  A direct non-zero PHQ-9 item-nine response asks a
    trained human to review the source response; it does not establish intent,
    imminence, or authorise contact or any other action.
    """
    if type(consent_recorded) is not bool or not consent_recorded:
        raise ScreeningValidationError("Recorded screening consent is required before questionnaire scoring.")
    _require_exact_questions(instrument, questions_administered)
    normalized = _validate_responses(instrument, responses)
    definition = INSTRUMENTS[instrument]
    skipped_item_ids = [item_id for item_id, value in normalized.items() if value == SKIPPED]
    complete = not skipped_item_ids
    total_score = sum(normalized.values()) if complete else None
    item_nine_response = normalized.get("PHQ9_9")
    return {
        "instrument": instrument,
        "instrument_version": definition["instrument_version"],
        "questionnaire_score_version": "validated-questionnaire-score.v1",
        "status": "complete" if complete else "incomplete",
        "consent_recorded": True,
        "questions_administered": get_instrument(instrument)["items"],
        "responses": normalized,
        "skipped_item_ids": skipped_item_ids,
        "total_score": total_score,
        "maximum_score": definition["maximum_score"],
        "requires_human_review": bool(item_nine_response not in (None, SKIPPED, 0)),
        "review_reason": (
            "The person's answer to the last PHQ-9 question should be looked at by a trained staff member. "
            "It does not by itself tell us what the person intends or how immediate any risk might be."
            if item_nine_response not in (None, SKIPPED, 0)
            else None
        ),
        "limitation_notice": (
            "This score is not a medical diagnosis. On its own, it cannot be used to contact the person, "
            "start services, change their records, or make any legal or protection decision."
        ),
    }
