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
from src.scoring import assess_spi_trend, compute_support_priority_indicator
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


if __name__ == "__main__":
    unittest.main()
