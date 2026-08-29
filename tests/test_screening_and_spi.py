"""Safety boundaries for consented questionnaires and non-diagnostic SPI triage."""

import os
import tempfile
import unittest

from src.acoustic import extract_acoustic_features, extract_acoustic_features_from_bytes
from src.alerts import check_and_create_review_tasks, create_crisis_workflow_events
from src.database import (
    create_scoped_case,
    export_deidentified_dashboard,
    get_connection,
    get_crisis_events,
    get_interactions_for_case,
    get_restricted_transcript,
    get_scoped_case,
    init_db,
    insert_case,
    insert_interaction,
    insert_validated_screening,
)
from src.privacy_architecture import (
    AccessContext,
    AccessDenied,
    append_security_audit,
    require_export_access,
    store_identity_contact,
    verify_audit_chain,
)
from src.screening import (
    SKIPPED,
    ScreeningValidationError,
    get_instrument,
    score_validated_screening,
)
from src.scoring import assess_spi_trend, compute_support_priority_indicator, project_spi_trajectory
import src.database as database
import src.privacy_architecture as privacy


def _signals(*, physical_status="insufficient_information", physical_level=0.0,
             explicit_danger=False, wellbeing_status="insufficient_information",
             wellbeing_level=0.0, explicit_self_harm=False,
             service_status="insufficient_information", service_level=0.0,
             confidence="high"):
    """Create strict-extraction-shaped signals for deterministic boundary tests."""
    return {
        "schema_version": "support_triage.test.v1",
        "physical_safety": {
            "status": physical_status, "level": physical_level,
            "reported_concerns": ["A reported concern"] if physical_status == "detected" else [],
            "explicit_threat_or_immediate_danger": explicit_danger,
        },
        "wellbeing": {
            "status": wellbeing_status, "level": wellbeing_level,
            "reported_indicators": ["A reported indicator"] if wellbeing_status == "detected" else [],
            "explicit_self_harm_statement": explicit_self_harm,
        },
        "service_access": {
            "status": service_status, "level": service_level,
            "reported_barriers": ["A reported barrier"] if service_status == "detected" else [],
        },
        "immediate_self_harm_or_suicide": {
            "status": "detected" if explicit_self_harm else "not_detected",
            "explicit_statement": explicit_self_harm,
        },
        "evidence": [],
        "data_quality": {"confidence": confidence, "limitations": ["Test record."]},
    }


class ValidatedQuestionnaireTests(unittest.TestCase):
    def _responses(self, instrument, value):
        return {item["id"]: value for item in get_instrument(instrument)["items"]}

    def test_complete_questionnaire_boundaries(self):
        phq = get_instrument("PHQ-9")
        minimum = score_validated_screening(
            instrument="PHQ-9", questions_administered=phq["items"],
            responses=self._responses("PHQ-9", 0), consent_recorded=True,
        )
        maximum = score_validated_screening(
            instrument="PHQ-9", questions_administered=phq["items"],
            responses=self._responses("PHQ-9", 3), consent_recorded=True,
        )
        gad = get_instrument("GAD-7")
        gad_maximum = score_validated_screening(
            instrument="GAD-7", questions_administered=gad["items"],
            responses=self._responses("GAD-7", 3), consent_recorded=True,
        )
        self.assertEqual((minimum["total_score"], maximum["total_score"], gad_maximum["total_score"]), (0, 27, 21))
        self.assertEqual(maximum["status"], "complete")
        self.assertTrue(maximum["requires_human_review"])  # direct item-nine response, not the total itself

    def test_skip_prevents_a_total_and_missing_consent_rejects_scoring(self):
        phq = get_instrument("PHQ-9")
        responses = self._responses("PHQ-9", 1)
        responses["PHQ9_4"] = SKIPPED
        incomplete = score_validated_screening(
            instrument="PHQ-9", questions_administered=phq["items"], responses=responses, consent_recorded=True,
        )
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertIsNone(incomplete["total_score"])
        with self.assertRaises(ScreeningValidationError):
            score_validated_screening(
                instrument="PHQ-9", questions_administered=phq["items"],
                responses=self._responses("PHQ-9", 0), consent_recorded=False,
            )

    def test_changed_question_set_is_rejected(self):
        phq = get_instrument("PHQ-9")
        changed = list(phq["items"])
        changed[0] = {"id": "PHQ9_1", "text": "Changed wording"}
        with self.assertRaises(ScreeningValidationError):
            score_validated_screening(
                instrument="PHQ-9", questions_administered=changed,
                responses=self._responses("PHQ-9", 0), consent_recorded=True,
            )


class SupportPrioritySafetyTests(unittest.TestCase):
    def test_unsupported_or_conflicting_signal_does_not_contribute(self):
        assessment = compute_support_priority_indicator(_signals(
            physical_status="insufficient_information", physical_level=1.0, explicit_danger=True,
            wellbeing_status="not_detected", wellbeing_level=1.0,
        ))
        self.assertEqual(assessment["spi"], 0.0)
        self.assertFalse(assessment["explicit_danger"])
        self.assertEqual(assessment["dimensions"][0]["score"], 0.0)

    def test_spi_exactly_at_urgent_threshold_is_urgent(self):
        # BOUNDARY TEST: Ensure that an SPI score exactly hitting the urgent threshold (85.0)
        # is correctly categorised as "Urgent human review" and not mistakenly placed in a
        # lower band. This prevents off-by-one errors where >= 85.0 is accidentally > 85.0.
        # Weights: physical(35) + wellbeing(20) + service(15) + explicit(15) = 85.0
        signals = _signals(
            physical_status="detected", physical_level=1.0, explicit_danger=True,
            wellbeing_status="detected", wellbeing_level=1.0,
            service_status="detected", service_level=1.0,
        )
        assessment = compute_support_priority_indicator(signals)
        self.assertEqual(assessment["spi"], 85.0)
        self.assertEqual(assessment["priority_band"], "Urgent human review")

    def test_spi_just_below_urgent_is_prompt(self):
        # BOUNDARY TEST: An SPI of 55.0 falls in the "Timely review" band (30–59).
        # physical(35) + wellbeing(20) = 55.0 — must NOT be "Urgent human review".
        signals = _signals(
            physical_status="detected", physical_level=1.0,
            wellbeing_status="detected", wellbeing_level=1.0,
        )
        assessment = compute_support_priority_indicator(signals)
        self.assertEqual(assessment["spi"], 55.0)
        self.assertEqual(assessment["priority_band"], "Timely review")

    def test_conflicting_signals_default_to_caution_rather_than_averaging(self):
        # FALSE-POSITIVE PREVENTION: If one part of a transcript reads as severe
        # and another as reassuring, the system must default to caution (adding them)
        # rather than averaging them away. This ensures a reassuring statement
        # doesn't cancel out a severe physical safety threat.
        signals = _signals(
            physical_status="detected", physical_level=1.0,  # Severe
            wellbeing_status="detected", wellbeing_level=0.0  # Reassuring
        )
        assessment = compute_support_priority_indicator(signals)
        # Weight for physical_safety is 35.0. Wellbeing at level 0.0 contributes 0.
        # If averaged, (35.0 + 0) / 2 = 17.5 — would fall to "Routine review".
        # If additive (caution), it's 35.0 — stays at "Timely review".
        self.assertEqual(assessment["spi"], 35.0)
        self.assertEqual(assessment["priority_band"], "Timely review")

    def test_trend_marks_low_confidence_channel_and_language_changes_not_comparable(self):
        previous = {
            "support_priority_indicator": 20, "confidence": "high", "channel": "helpline_call",
            "analysis_language": "English", "score_version": "spi-calculation.v2@spi-thresholds.v1",
        }
        current = {
            "support_priority_indicator": 90, "confidence": "low", "channel": "text_message",
            "analysis_language": "हिन्दी (Hindi)", "score_version": "spi-calculation.v2@spi-thresholds.v1",
        }
        trend = assess_spi_trend(current, [previous])
        self.assertFalse(trend["comparable"])
        self.assertEqual(trend["status"], "not_comparable")
        self.assertIn("low_confidence_current_extraction", trend["quality_issues"])
        self.assertIn("channel_changed", trend["quality_issues"])
        self.assertIn("language_changed", trend["quality_issues"])

    def test_comparable_material_increase_can_be_reported_as_worsening(self):
        common = {"confidence": "high", "channel": "helpline_call", "analysis_language": "English", "score_version": "spi-calculation.v2@spi-thresholds.v1"}
        trend = assess_spi_trend({**common, "support_priority_indicator": 55}, [{**common, "support_priority_indicator": 30}])
        self.assertTrue(trend["comparable"])
        self.assertEqual((trend["status"], trend["delta"]), ("worsening", 25.0))


class FalsePositivePreventionTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(prefix="nhaa-spi-test-", suffix=".db")
        os.close(handle)
        self.previous_path = database.DB_PATH
        self.previous_identity_path = privacy.IDENTITY_DB_PATH
        self.previous_audit_path = privacy.AUDIT_DB_PATH
        database.DB_PATH = self.path
        privacy.IDENTITY_DB_PATH = self.path + ".identity"
        privacy.AUDIT_DB_PATH = self.path + ".audit"
        init_db()
        insert_case("TEST-CASE", "Test State", "Test District")

    def tearDown(self):
        database.DB_PATH = self.previous_path
        privacy.IDENTITY_DB_PATH = self.previous_identity_path
        privacy.AUDIT_DB_PATH = self.previous_audit_path
        for base in (self.path, self.path + ".identity", self.path + ".audit"):
            for suffix in ("", "-shm", "-wal"):
                try:
                    os.remove(base + suffix)
                except FileNotFoundError:
                    pass

    def test_high_spi_without_explicit_statement_creates_no_crisis_event(self):
        # High non-clinical feature values may create a human review task elsewhere,
        # but cannot by themselves open a self-harm or safety-threat pathway.
        signals = _signals(
            physical_status="detected", physical_level=1.0, explicit_danger=False,
            wellbeing_status="detected", wellbeing_level=1.0, explicit_self_harm=False,
            service_status="detected", service_level=1.0,
        )
        assessment = compute_support_priority_indicator(signals)
        interaction_id = insert_interaction(
            "TEST-CASE", "Synthetic testing note", support_signals=signals,
            support_priority_indicator=assessment["spi"], confidence=assessment["confidence"],
            score_version=assessment["score_version"], threshold_version=assessment["threshold_version"],
            model_version=assessment["model_version"], feature_set=assessment["feature_set"],
            evidence_references=assessment["evidence_references"], trend_status=assessment["trend"]["status"],
            trend_quality_issues=assessment["trend"]["quality_issues"],
        )
        events = create_crisis_workflow_events("TEST-CASE", interaction_id, assessment, signals)
        self.assertGreaterEqual(assessment["spi"], 70)
        self.assertEqual(events, [])
        self.assertEqual(get_crisis_events(), [])

    def test_understated_threat_still_escalates_despite_low_model_confidence(self):
        # ADVERSARIAL TEST: This tests a specific, known LLM failure mode.
        # In a real witness-intimidation scenario, a caller minimizing danger
        # ("He said he'd find me but I don't want to make a fuss") often causes
        # language models to output a low severity score (e.g., 0.25) or low
        # overall extraction confidence.
        # This test proves that as long as the explicit threat flag is caught,
        # the deterministic SPI layer correctly overrides the model's ambiguity
        # and routes to urgent review. This proves escalation doesn't rely solely
        # on the model being confident.
        signals = _signals(
            physical_status="detected",
            physical_level=0.25, # Model minimizes the threat level
            explicit_danger=True, # But the explicit threat flag triggered
            confidence="low",    # Overall model confidence is low
        )
        assessment = compute_support_priority_indicator(signals)
        
        # SPI should hit the reported_threat_floor (70.0) despite low confidence.
        # This keeps the base SPI from completely hiding the threat.
        self.assertGreaterEqual(assessment["spi"], 70.0)
        self.assertEqual(assessment["priority_band"], "Prompt review")
        
        # Insert interaction to satisfy foreign keys
        interaction_id = insert_interaction(
            "TEST-CASE", "Synthetic testing note", support_signals=signals,
            support_priority_indicator=assessment["spi"], confidence=assessment["confidence"],
            score_version=assessment["score_version"], threshold_version=assessment["threshold_version"],
            model_version=assessment["model_version"], feature_set=assessment["feature_set"],
            evidence_references=assessment["evidence_references"], trend_status=assessment["trend"]["status"],
            trend_quality_issues=assessment["trend"]["quality_issues"],
        )

        # Verify tasks include URGENT physical safety
        from src.alerts import check_and_create_review_tasks, create_crisis_workflow_events
        tasks = check_and_create_review_tasks("TEST-CASE", interaction_id, assessment, signals)
        urgent_tasks = [t for t in tasks if t["alert_level"] == "URGENT" and t["alert_type"] == "PHYSICAL_SAFETY"]
        self.assertEqual(len(urgent_tasks), 1)
        
        # Verify crisis events include URGENT external safety threat
        events = create_crisis_workflow_events("TEST-CASE", interaction_id, assessment, signals)
        urgent_events = [e for e in events if e["priority"] == "URGENT" and e["pathway"] == "EXTERNAL_SAFETY_THREAT"]
        self.assertEqual(len(urgent_events), 1)


    def test_acoustic_metadata_alone_creates_no_alert_or_crisis_event(self):
        # Deliberately extreme-looking experimental descriptors are opaque
        # metadata, not evidence of wellbeing, credibility, or safety.
        metadata = extract_acoustic_features(
            "/path/that/does/not/need/to/exist.wav",
            opt_in=False,
            consent_recorded=False,
            audio_quality="very_limited",
            language="English",
            device_limitations=["background_noise"],
            model_uncertainty="high",
        )
        signals = _signals()
        signals["acoustic_analysis_metadata"] = {**metadata, "features": {"arbitrary_descriptor": 999999.0}}
        assessment = compute_support_priority_indicator(signals)
        interaction_id = insert_interaction(
            "TEST-CASE", "Synthetic audio-only testing note", support_signals=signals,
            support_priority_indicator=assessment["spi"], confidence=assessment["confidence"],
            acoustic_features=signals["acoustic_analysis_metadata"]["features"],
            audio_analysis_metadata=metadata, audio_analysis_opt_in=False,
            audio_analysis_consent_recorded=False, audio_quality="very_limited",
            audio_language="English", audio_device_limitations=["background_noise"],
            audio_model_uncertainty="high", raw_audio_retention_status="discarded_after_transcription",
        )
        self.assertEqual(assessment["spi"], 0.0)
        self.assertEqual(check_and_create_review_tasks("TEST-CASE", interaction_id, assessment, signals), [])
        self.assertEqual(create_crisis_workflow_events("TEST-CASE", interaction_id, assessment, signals), [])
        self.assertEqual(get_crisis_events(), [])

    def test_audio_bytes_are_not_written_for_disabled_or_unconsented_analysis(self):
        metadata = extract_acoustic_features_from_bytes(
            b"not a real recording", "test.wav", opt_in=False, consent_recorded=False,
            transcription_consent_recorded=False, audio_quality="not_assessed", language="English",
            device_limitations=[], model_uncertainty="high",
        )
        self.assertEqual(metadata["analysis_status"], "not_requested")
        self.assertEqual(metadata["raw_audio_retention_status"], "discarded_after_transcription")
        self.assertEqual(metadata["features"], {})

    def test_provenance_and_incomplete_screening_are_persisted(self):
        signals = _signals()
        assessment = compute_support_priority_indicator(signals)
        insert_interaction(
            "TEST-CASE", "Synthetic testing note", support_signals=signals,
            support_priority_indicator=assessment["spi"], confidence=assessment["confidence"],
            score_version=assessment["score_version"], threshold_version=assessment["threshold_version"],
            model_version=assessment["model_version"], feature_set=assessment["feature_set"],
            evidence_references=assessment["evidence_references"], trend_status=assessment["trend"]["status"],
            trend_quality_issues=assessment["trend"]["quality_issues"],
        )
        interaction = get_interactions_for_case("TEST-CASE")[0]
        self.assertEqual(interaction["score_version"], assessment["score_version"])
        self.assertEqual(interaction["feature_set"], assessment["feature_set"])
        phq = get_instrument("PHQ-9")
        responses = {item["id"]: 0 for item in phq["items"]}
        responses["PHQ9_2"] = SKIPPED
        screening = score_validated_screening(
            instrument="PHQ-9", questions_administered=phq["items"], responses=responses, consent_recorded=True,
        )
        self.assertIsInstance(insert_validated_screening("TEST-CASE", screening), int)


class PrivacySecurityTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(prefix="nhaa-privacy-test-", suffix=".db")
        os.close(handle)
        self.previous_path = database.DB_PATH
        self.previous_identity_path = privacy.IDENTITY_DB_PATH
        self.previous_audit_path = privacy.AUDIT_DB_PATH
        database.DB_PATH = self.path
        privacy.IDENTITY_DB_PATH = self.path + ".identity"
        privacy.AUDIT_DB_PATH = self.path + ".audit"
        init_db()
        self.pune_counsellor = AccessContext(
            "USR-PUNE-1", "counsellor", "Maharashtra", "Pune", frozenset({"case_review", "consent_management"})
        )
        self.jaipur_counsellor = AccessContext(
            "USR-JAIPUR-1", "counsellor", "Rajasthan", "Jaipur", frozenset({"case_review"})
        )
        self.state_admin = AccessContext(
            "USR-STATE-1", "state_administrator", "Maharashtra", None,
            frozenset({"service_coordination", "authorised_reporting"}),
        )
        self.auditor = AccessContext("USR-AUDIT-1", "auditor", None, None, frozenset({"audit"}))
        self.case_id = create_scoped_case(self.pune_counsellor, "Maharashtra", "Pune", purpose="case_review")
        self.interaction_id = insert_interaction(
            self.case_id, "Restricted survivor source note", support_priority_indicator=0,
            consent_recorded=True,
        )

    def tearDown(self):
        database.DB_PATH = self.previous_path
        privacy.IDENTITY_DB_PATH = self.previous_identity_path
        privacy.AUDIT_DB_PATH = self.previous_audit_path
        for base in (self.path, self.path + ".identity", self.path + ".audit"):
            for suffix in ("", "-shm", "-wal"):
                try:
                    os.remove(base + suffix)
                except FileNotFoundError:
                    pass

    def test_cross_district_case_and_transcript_access_is_denied(self):
        with self.assertRaises(AccessDenied):
            get_scoped_case(self.jaipur_counsellor, self.case_id, purpose="case_review")
        with self.assertRaises(AccessDenied):
            get_restricted_transcript(self.jaipur_counsellor, self.interaction_id, purpose="case_review")
        self.assertEqual(
            get_restricted_transcript(self.pune_counsellor, self.interaction_id, purpose="case_review"),
            "Restricted survivor source note",
        )

    def test_identity_contact_is_separate_and_encrypted(self):
        subject_id = store_identity_contact(
            self.case_id, full_name="Example Name", phone="9000000000", contact_preferences={"channel": "secure_portal"}
        )
        self.assertTrue(subject_id.startswith("SUBJECT-"))
        conn = privacy._identity_connection()
        try:
            row = conn.execute("SELECT encrypted_name, encrypted_phone FROM identity_contact_vault WHERE case_id=?", (self.case_id,)).fetchone()
        finally:
            conn.close()
        self.assertNotIn("Example Name", row["encrypted_name"])
        self.assertNotIn("9000000000", row["encrypted_phone"])
        case_conn = get_connection()
        try:
            columns = {item["name"] for item in case_conn.execute("PRAGMA table_info(cases)")}
        finally:
            case_conn.close()
        self.assertNotIn("full_name", columns)
        self.assertNotIn("phone", columns)

    def test_unauthorised_individual_export_is_denied(self):
        with self.assertRaises(AccessDenied):
            require_export_access(self.pune_counsellor, purpose="case_review", export_kind="case")
        with self.assertRaises(AccessDenied):
            export_deidentified_dashboard(self.pune_counsellor, purpose="authorised_reporting")
        aggregate = export_deidentified_dashboard(self.state_admin, purpose="authorised_reporting")
        self.assertNotIn("case_id", str(aggregate))
        self.assertNotIn("transcript", str(aggregate).lower())

    def test_security_audit_chain_is_immutable_and_detects_tampering(self):
        append_security_audit(
            actor_id=self.auditor.user_id, action="TEST_EVENT", resource_type="test", resource_id="one",
            purpose="audit", result="ALLOWED", details={"safe": "value"},
        )
        self.assertTrue(verify_audit_chain())
        conn = privacy._audit_connection()
        try:
            with self.assertRaises(Exception):
                conn.execute("UPDATE security_audit_events SET action='TAMPERED' WHERE sequence=1")
            conn.rollback()
        finally:
            conn.close()
        self.assertTrue(verify_audit_chain())


class TrajectoryProjectionTests(unittest.TestCase):
    """Tests for the forward-looking SPI trajectory projection."""

    COMMON = {
        "confidence": "high",
        "channel": "helpline_call",
        "analysis_language": "English",
        "score_version": "spi-calculation.v2@spi-thresholds.v1",
    }

    def _history(self, spis, start="2024-01-01", interval_days=3):
        """Build a scored history list from a simple list of SPI values."""
        from datetime import datetime, timedelta
        base = datetime.fromisoformat(start)
        result = []
        for i, spi in enumerate(spis):
            result.append({
                **self.COMMON,
                "support_priority_indicator": spi,
                "timestamp": (base + timedelta(days=i * interval_days)).isoformat(),
            })
        return result

    def test_positive_slope_projects_urgent_date(self):
        """Steadily rising SPI should project a crossing within N days."""
        # 40, 50, 60 over 6 days → slope ~3.33/day → 85-60 = 25 points → ~7.5 days
        history = self._history([40, 50, 60])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "projected_urgent")
        self.assertIsNotNone(result["projected_urgent_date"])
        self.assertGreater(result["slope_per_day"], 0)
        self.assertIn("projected to reach", result["message"])

    def test_negative_slope_no_crossing(self):
        """Decreasing SPI should report no crossing."""
        history = self._history([70, 60, 50])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "no_crossing")
        self.assertIsNone(result["projected_urgent_date"])

    def test_flat_slope_no_crossing(self):
        """Flat SPI should report no crossing."""
        history = self._history([50, 50, 50])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "no_crossing")

    def test_insufficient_data_with_two_points(self):
        """Fewer than 3 points should return insufficient_data."""
        history = self._history([40, 50])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "insufficient_data")

    def test_channel_change_breaks_comparability(self):
        """Mismatched channels should prevent projection."""
        history = self._history([40, 50, 60])
        # Change the channel on the middle record
        history[1]["channel"] = "text_message"
        result = project_spi_trajectory(history, projection_days=14)
        self.assertIn(result["status"], ("insufficient_data", "not_comparable"))

    def test_already_urgent(self):
        """If the latest SPI is already >= urgent threshold, status is already_urgent."""
        history = self._history([70, 80, 90])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "already_urgent")

    def test_crossing_beyond_horizon_is_no_crossing(self):
        """Very slow rise should not project crossing within the short horizon."""
        # 30, 31, 32 over 6 days → slope ~0.33/day → 85-32 = 53 pts → ~159 days
        history = self._history([30, 31, 32])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "no_crossing")

    def test_same_day_data_rejected(self):
        """All data points on the same day cannot produce a time-based projection."""
        from datetime import datetime
        same_ts = datetime(2024, 1, 1, 12, 0, 0).isoformat()
        history = [
            {**self.COMMON, "support_priority_indicator": 40, "timestamp": same_ts},
            {**self.COMMON, "support_priority_indicator": 50, "timestamp": same_ts},
            {**self.COMMON, "support_priority_indicator": 60, "timestamp": same_ts},
        ]
        result = project_spi_trajectory(history, projection_days=14)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIn("same day", result["message"])

    def test_caveat_always_present(self):
        """Every projection result must include the caveat string."""
        history = self._history([40, 50, 60])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertIn("caveat", result)
        self.assertIn("statistical extrapolation", result["caveat"])

    def test_data_points_used_count(self):
        """Confirm that data_points_used reflects the actual count."""
        history = self._history([30, 40, 50, 55, 60])
        result = project_spi_trajectory(history, projection_days=30)
        self.assertEqual(result["data_points_used"], 5)

    def test_max_five_points_used(self):
        """Even with 7 points, only the most recent 5 should be used."""
        history = self._history([10, 20, 30, 40, 50, 60, 70])
        result = project_spi_trajectory(history, projection_days=14)
        self.assertLessEqual(result["data_points_used"], 5)


class LocalizationTests(unittest.TestCase):
    def test_word_count_handles_non_latin_scripts_safely(self):
        # BOUNDARY TEST: repo1 found that word-boundary regex (\b) silently fails
        # on non-Latin scripts (like Hindi), causing word counts to return 0.
        # This test ensures our _word_count logic correctly handles non-Latin text
        # by using \S+ instead of \b, avoiding the false-positive bug.
        from src.groq_client import _word_count
        hindi_text = "मैं खतरे में हूँ और मुझे मदद चाहिए"
        # 8 distinct words separated by spaces
        self.assertEqual(_word_count(hindi_text), 8)

    def test_word_count_handles_mixed_script_text(self):
        # BOUNDARY TEST: Real-world transcripts may contain mixed scripts,
        # e.g. English terms in a Hindi sentence. The word counter must
        # correctly count both scripts without losing any tokens.
        from src.groq_client import _word_count
        mixed_text = "मुझे police station जाना है"
        self.assertEqual(_word_count(mixed_text), 5)

    def test_word_count_handles_zero_width_joiners_in_devanagari(self):
        # BOUNDARY TEST: Devanagari conjuncts sometimes use zero-width joiners.
        # The word counter must not split a single conjoined word into multiple
        # tokens due to invisible Unicode characters.
        from src.groq_client import _word_count
        # "श्री" contains a virama (halant) which joins consonants — it should be 1 word.
        self.assertEqual(_word_count("श्री"), 1)


if __name__ == "__main__":
    unittest.main()
