"""Comprehensive tests for the multilingual check-in journey system.

Covers: language-pack completeness across en/hi/bn/ta, journey validation,
channel delivery guidance for all 6 channels, blueprint ordering (safety
before wellbeing), IVRS accessibility, no-stigma checks, per-language
performance evaluation, extensibility, and database persistence.
"""

import json
import os
import tempfile
import unittest

from config import (
    CHECKIN_ACCESSIBILITY_NEEDS,
    CHECKIN_BASE_LANGUAGE_PACKS,
    CHECKIN_CHANNELS,
    CHECKIN_SUPPORT_CHOICES,
    SAFE_FOLLOW_UP_CHANNELS,
)
from src.checkin_journeys import (
    EXTENSIBILITY_GUIDE,
    CheckinJourneyValidationError,
    channel_delivery_guidance,
    get_language_pack,
    ivrs_accessibility_fallback,
    journey_blueprint,
    language_catalog,
    language_evaluation_report,
    option_label,
    register_language_pack,
    validate_checkin_start,
    validate_checkin_update,
)
import src.database as database
import src.privacy_architecture as privacy
from src.database import (
    create_checkin_session,
    get_checkin_session,
    get_checkin_sessions_for_case,
    init_db,
    insert_case,
    update_checkin_session,
)

SUPPORTED_LANGUAGES = list(CHECKIN_BASE_LANGUAGE_PACKS.keys())


def _valid_start_payload(*, channel="chatbot", lang="en"):
    return {
        "channel": channel,
        "language_code": lang,
        "consent_recorded": True,
        "safe_time": "safe_now",
        "safe_channel": "chatbot",
        "programme_mention_allowed": False,
        "accessibility_needs": [],
    }


class LanguagePackTests(unittest.TestCase):
    """Every base language pack must have the exact same set of keys."""

    def test_all_base_languages_are_registered(self):
        for code in SUPPORTED_LANGUAGES:
            pack = get_language_pack(code)
            self.assertIn("copy", pack)
            self.assertIn("options", pack)

    def test_copy_keys_match_english_for_all_languages(self):
        en_pack = get_language_pack("en")
        en_keys = set(en_pack["copy"])
        for code in SUPPORTED_LANGUAGES:
            pack = get_language_pack(code)
            self.assertEqual(set(pack["copy"]), en_keys,
                             f"Language {code} copy keys do not match English.")

    def test_option_keys_match_english_for_all_languages(self):
        en_pack = get_language_pack("en")
        en_keys = set(en_pack["options"])
        for code in SUPPORTED_LANGUAGES:
            pack = get_language_pack(code)
            self.assertEqual(set(pack["options"]), en_keys,
                             f"Language {code} option keys do not match English.")

    def test_no_empty_values_in_any_language(self):
        for code in SUPPORTED_LANGUAGES:
            pack = get_language_pack(code)
            for key, value in pack["copy"].items():
                self.assertTrue(str(value).strip(), f"{code} copy.{key} is empty.")
            for key, value in pack["options"].items():
                self.assertTrue(str(value).strip(), f"{code} option.{key} is empty.")

    def test_language_catalog_lists_all_base_languages(self):
        catalog = language_catalog()
        codes = {entry["code"] for entry in catalog}
        for code in SUPPORTED_LANGUAGES:
            self.assertIn(code, codes)

    def test_unregistered_language_raises(self):
        with self.assertRaises(CheckinJourneyValidationError):
            get_language_pack("xx")


class JourneyValidationTests(unittest.TestCase):
    """validate_checkin_start accepts correct payloads and rejects bad ones."""

    def test_valid_payload_accepted_for_all_channels_and_languages(self):
        for channel in CHECKIN_CHANNELS:
            for lang in SUPPORTED_LANGUAGES:
                result = validate_checkin_start(_valid_start_payload(channel=channel, lang=lang))
                self.assertEqual(result["channel"], channel)
                self.assertEqual(result["language_code"], lang)

    def test_non_dict_payload_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_start("not a dict")

    def test_missing_field_rejected(self):
        payload = _valid_start_payload()
        del payload["safe_time"]
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_start(payload)

    def test_extra_field_rejected(self):
        payload = _valid_start_payload()
        payload["extra_field"] = "bad"
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_start(payload)

    def test_invalid_channel_rejected(self):
        payload = _valid_start_payload()
        payload["channel"] = "carrier_pigeon"
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_start(payload)

    def test_consent_must_be_bool(self):
        payload = _valid_start_payload()
        payload["consent_recorded"] = "yes"
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_start(payload)

    def test_accessibility_needs_must_be_list(self):
        payload = _valid_start_payload()
        payload["accessibility_needs"] = "low_literacy"
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_start(payload)

    def test_all_accessibility_needs_accepted(self):
        payload = _valid_start_payload()
        payload["accessibility_needs"] = list(CHECKIN_ACCESSIBILITY_NEEDS)
        result = validate_checkin_start(payload)
        self.assertEqual(len(result["accessibility_needs"]), len(CHECKIN_ACCESSIBILITY_NEEDS))

    def test_all_safe_follow_up_channels_accepted(self):
        for ch in SAFE_FOLLOW_UP_CHANNELS:
            payload = _valid_start_payload()
            payload["safe_channel"] = ch
            result = validate_checkin_start(payload)
            self.assertEqual(result["safe_channel"], ch)


class JourneyUpdateTests(unittest.TestCase):
    """validate_checkin_update handles all step responses and controls."""

    def test_immediate_safety_options(self):
        for option in ["safe_now", "not_sure", "need_human_help_now", "skip"]:
            result = validate_checkin_update({"immediate_safety": option})
            self.assertEqual(result["immediate_safety"], option)

    def test_wellbeing_options(self):
        for option in ["want_to_talk", "doing_ok", "skip"]:
            result = validate_checkin_update({"wellbeing": option})
            self.assertEqual(result["wellbeing"], option)

    def test_support_choices(self):
        result = validate_checkin_update({"support_choices": ["counselling", "legal_aid", "transport"]})
        self.assertEqual(len(result["support_choices"]), 3)

    def test_all_support_choices_accepted(self):
        result = validate_checkin_update({"support_choices": list(CHECKIN_SUPPORT_CHOICES)})
        self.assertEqual(len(result["support_choices"]), len(CHECKIN_SUPPORT_CHOICES))

    def test_control_actions(self):
        for action in ["pause", "stop", "complete"]:
            result = validate_checkin_update({"control": action})
            self.assertEqual(result["control"], action)

    def test_request_human_help(self):
        result = validate_checkin_update({"request_human_help": True})
        self.assertTrue(result["request_human_help"])

    def test_empty_update_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_update({})

    def test_non_dict_update_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_update("pause")

    def test_unsupported_field_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_update({"incident_details": "should never be accepted"})

    def test_invalid_safety_option_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_update({"immediate_safety": "very_dangerous"})

    def test_duplicate_support_choices_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            validate_checkin_update({"support_choices": ["counselling", "counselling"]})


class ChannelDeliveryTests(unittest.TestCase):
    """channel_delivery_guidance for all 6 channels × 4 languages."""

    def test_all_channels_and_languages_produce_guidance(self):
        for channel in CHECKIN_CHANNELS:
            for lang in SUPPORTED_LANGUAGES:
                guidance = channel_delivery_guidance(lang, channel, programme_mention_allowed=False)
                self.assertEqual(guidance["channel"], channel)
                self.assertIn("first_touch", guidance)
                self.assertIn("rules", guidance)
                self.assertIsInstance(guidance["rules"], list)
                self.assertGreater(len(guidance["rules"]), 0)

    def test_sms_never_includes_case_or_health_information(self):
        for lang in SUPPORTED_LANGUAGES:
            guidance = channel_delivery_guidance(lang, "sms", programme_mention_allowed=False)
            rules_text = " ".join(guidance["rules"]).lower()
            self.assertIn("never include case", rules_text)

    def test_programme_mention_only_when_allowed(self):
        for lang in SUPPORTED_LANGUAGES:
            no_mention = channel_delivery_guidance(lang, "chatbot", programme_mention_allowed=False)
            with_mention = channel_delivery_guidance(lang, "chatbot", programme_mention_allowed=True)
            self.assertNotIn("programme", no_mention["first_touch"].lower().split("control")[0] if "control" in no_mention["first_touch"].lower() else no_mention["first_touch"].lower())
            self.assertIn("programme", with_mention["first_touch"].lower())

    def test_ivrs_guidance_includes_keypad_instructions(self):
        for lang in SUPPORTED_LANGUAGES:
            guidance = channel_delivery_guidance(lang, "ivrs", programme_mention_allowed=False)
            rules_text = " ".join(guidance["rules"])
            self.assertIn("0", rules_text)  # trained person
            self.assertIn("8", rules_text)  # pause
            self.assertIn("9", rules_text)  # stop

    def test_invalid_channel_rejected(self):
        with self.assertRaises(CheckinJourneyValidationError):
            channel_delivery_guidance("en", "telegram", programme_mention_allowed=False)


class BlueprintTests(unittest.TestCase):
    """journey_blueprint must enforce safety-before-wellbeing ordering."""

    def test_blueprint_has_correct_step_order(self):
        for channel in CHECKIN_CHANNELS:
            for lang in SUPPORTED_LANGUAGES:
                bp = journey_blueprint(lang, channel)
                step_names = [s["step"] for s in bp]
                self.assertIn("consent_and_contact", step_names)
                self.assertIn("immediate_safety", step_names)
                self.assertIn("wellbeing_optional", step_names)
                self.assertIn("practical_support", step_names)
                # Safety MUST come before wellbeing
                safety_idx = step_names.index("immediate_safety")
                wellbeing_idx = step_names.index("wellbeing_optional")
                self.assertLess(safety_idx, wellbeing_idx,
                                f"Safety must precede wellbeing on {channel}/{lang}")

    def test_consent_is_first_step(self):
        bp = journey_blueprint("en", "chatbot")
        self.assertEqual(bp[0]["step"], "consent_and_contact")
        self.assertTrue(bp[0]["required_before_next"])

    def test_safety_is_required_before_next(self):
        bp = journey_blueprint("en", "chatbot")
        safety = [s for s in bp if s["step"] == "immediate_safety"][0]
        self.assertTrue(safety["required_before_next"])

    def test_wellbeing_is_optional(self):
        bp = journey_blueprint("en", "chatbot")
        wellbeing = [s for s in bp if s["step"] == "wellbeing_optional"][0]
        self.assertFalse(wellbeing["required_before_next"])

    def test_practical_support_includes_all_choices(self):
        bp = journey_blueprint("en", "chatbot")
        support = [s for s in bp if s["step"] == "practical_support"][0]
        for choice in CHECKIN_SUPPORT_CHOICES:
            self.assertIn(choice, support["includes"])


class IVRSAccessibilityTests(unittest.TestCase):
    """IVRS accessibility fallback must be available for all languages."""

    def test_fallback_available_for_all_languages(self):
        for lang in SUPPORTED_LANGUAGES:
            fallback = ivrs_accessibility_fallback(lang)
            self.assertIn("design", fallback)
            self.assertIn("not_supported", fallback)
            self.assertGreater(len(fallback["design"]), 0)

    def test_fallback_includes_keypad_and_repeat(self):
        fallback = ivrs_accessibility_fallback("en")
        design_text = " ".join(fallback["design"]).lower()
        self.assertIn("keypad", design_text)
        self.assertIn("repeat", design_text)

    def test_no_repeated_calling_in_not_supported(self):
        fallback = ivrs_accessibility_fallback("en")
        self.assertIn("Repeated calling after no response", fallback["not_supported"])

    def test_fallback_rejects_unregistered_language(self):
        with self.assertRaises(CheckinJourneyValidationError):
            ivrs_accessibility_fallback("xx")


class NoStigmaTests(unittest.TestCase):
    """No survivor-facing copy may contain stigmatizing or diagnostic labels."""

    STIGMATIZING_TERMS = [
        "severe", "critical", "case level", "diagnosis", "disorder",
        "victim", "abnormal", "pathological", "mentally ill",
    ]

    def test_journey_copy_has_no_stigmatizing_labels(self):
        for lang in SUPPORTED_LANGUAGES:
            pack = get_language_pack(lang)
            for key, value in pack["copy"].items():
                lower = value.lower()
                for term in self.STIGMATIZING_TERMS:
                    self.assertNotIn(term, lower,
                                     f"Stigmatizing term '{term}' found in {lang} copy.{key}")

    def test_option_labels_have_no_stigmatizing_labels(self):
        for lang in SUPPORTED_LANGUAGES:
            pack = get_language_pack(lang)
            for key, value in pack["options"].items():
                lower = value.lower()
                for term in self.STIGMATIZING_TERMS:
                    self.assertNotIn(term, lower,
                                     f"Stigmatizing term '{term}' found in {lang} option.{key}")

    def test_channel_guidance_has_no_stigmatizing_labels(self):
        for channel in CHECKIN_CHANNELS:
            guidance = channel_delivery_guidance("en", channel, programme_mention_allowed=False)
            text = (guidance["first_touch"] + " " + " ".join(guidance["rules"])).lower()
            for term in self.STIGMATIZING_TERMS:
                self.assertNotIn(term, text,
                                 f"Stigmatizing term '{term}' found in {channel} guidance")


class PerLanguagePerformanceTests(unittest.TestCase):
    """Each language pack evaluated independently for deployment readiness."""

    def test_evaluation_report_for_all_languages(self):
        for code in SUPPORTED_LANGUAGES:
            report = language_evaluation_report(code)
            self.assertTrue(report["registered"], f"{code} not registered")
            self.assertTrue(report["copy_keys_complete"], f"{code} copy keys incomplete")
            self.assertTrue(report["option_keys_complete"], f"{code} option keys incomplete")
            self.assertEqual(report["missing_copy_keys"], [], f"{code} has missing copy keys")
            self.assertEqual(report["missing_option_keys"], [], f"{code} has missing option keys")
            self.assertEqual(report["empty_values"], [], f"{code} has empty values")
            self.assertTrue(report["reviewed"], f"{code} not marked as reviewed")

    def test_unregistered_language_report(self):
        report = language_evaluation_report("xx")
        self.assertFalse(report["registered"])
        self.assertFalse(report["reviewed"])
        self.assertIn("not registered", report["notes"][0].lower())

    def test_key_count_parity_across_languages(self):
        reports = {code: language_evaluation_report(code) for code in SUPPORTED_LANGUAGES}
        en_copy_count = reports["en"]["copy_key_count"]
        en_option_count = reports["en"]["option_key_count"]
        for code, report in reports.items():
            self.assertEqual(report["copy_key_count"], en_copy_count,
                             f"{code} copy key count differs from English")
            self.assertEqual(report["option_key_count"], en_option_count,
                             f"{code} option key count differs from English")


class ExtensibilityTests(unittest.TestCase):
    """Adding a new language pack must validate completeness."""

    def test_incomplete_copy_raises(self):
        with self.assertRaises(CheckinJourneyValidationError):
            register_language_pack(
                code="mr_test", name="Test", autonym="Test",
                copy_dict={"control": "Test"},  # missing keys
                option_dict=get_language_pack("en")["options"],
            )

    def test_incomplete_options_raises(self):
        with self.assertRaises(CheckinJourneyValidationError):
            register_language_pack(
                code="mr_test", name="Test", autonym="Test",
                copy_dict=get_language_pack("en")["copy"],
                option_dict={"yes": "Yes"},  # missing keys
            )

    def test_complete_pack_registers_successfully(self):
        en = get_language_pack("en")
        register_language_pack(
            code="test_lang", name="TestLang", autonym="TestLang",
            copy_dict=en["copy"], option_dict=en["options"],
        )
        pack = get_language_pack("test_lang")
        self.assertEqual(set(pack["copy"]), set(en["copy"]))
        # Verify it appears in catalog
        catalog = language_catalog()
        codes = {entry["code"] for entry in catalog}
        self.assertIn("test_lang", codes)
        # Verify evaluation report
        report = language_evaluation_report("test_lang")
        self.assertTrue(report["reviewed"])

    def test_extensibility_guide_is_non_empty(self):
        self.assertTrue(len(EXTENSIBILITY_GUIDE.strip()) > 100)
        self.assertIn("register_language_pack", EXTENSIBILITY_GUIDE)


class DatabasePersistenceTests(unittest.TestCase):
    """Check-in sessions are correctly persisted and retrieved."""

    def setUp(self):
        handle, self.path = tempfile.mkstemp(prefix="nhaa-checkin-test-", suffix=".db")
        os.close(handle)
        self.previous_path = database.DB_PATH
        self.previous_identity_path = privacy.IDENTITY_DB_PATH
        self.previous_audit_path = privacy.AUDIT_DB_PATH
        database.DB_PATH = self.path
        privacy.IDENTITY_DB_PATH = self.path + ".identity"
        privacy.AUDIT_DB_PATH = self.path + ".audit"
        init_db()
        insert_case("CHECKIN-TEST", "Test State", "Test District")

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

    def test_create_and_retrieve_session(self):
        validated = validate_checkin_start(_valid_start_payload())
        session_id = create_checkin_session("CHECKIN-TEST", validated)
        self.assertIsInstance(session_id, int)
        session = get_checkin_session(session_id)
        self.assertEqual(session["case_id"], "CHECKIN-TEST")
        self.assertEqual(session["channel"], "chatbot")
        self.assertEqual(session["language_code"], "en")
        self.assertEqual(session["status"], "OPEN")

    def test_update_session_with_safety_response(self):
        validated = validate_checkin_start(_valid_start_payload())
        session_id = create_checkin_session("CHECKIN-TEST", validated)
        update = validate_checkin_update({"immediate_safety": "safe_now"})
        result = update_checkin_session(session_id, update)
        self.assertEqual(result["status"], "OPEN")
        session = get_checkin_session(session_id)
        self.assertEqual(len(session["responses"]), 1)
        self.assertEqual(session["responses"][0]["response_key"], "immediate_safety")

    def test_pause_stop_complete_transitions(self):
        validated = validate_checkin_start(_valid_start_payload())
        session_id = create_checkin_session("CHECKIN-TEST", validated)

        update_checkin_session(session_id, validate_checkin_update({"control": "pause"}))
        self.assertEqual(get_checkin_session(session_id)["status"], "PAUSED")

        # Re-open by adding a response (status goes to OPEN since no control action)
        update_checkin_session(session_id, validate_checkin_update({"immediate_safety": "safe_now"}))
        self.assertEqual(get_checkin_session(session_id)["status"], "OPEN")

        update_checkin_session(session_id, validate_checkin_update({"control": "complete"}))
        self.assertEqual(get_checkin_session(session_id)["status"], "COMPLETE")

    def test_stop_transition(self):
        validated = validate_checkin_start(_valid_start_payload())
        session_id = create_checkin_session("CHECKIN-TEST", validated)
        update_checkin_session(session_id, validate_checkin_update({"control": "stop"}))
        self.assertEqual(get_checkin_session(session_id)["status"], "STOPPED")

    def test_list_sessions_for_case(self):
        for lang in ["en", "hi"]:
            validated = validate_checkin_start(_valid_start_payload(lang=lang))
            create_checkin_session("CHECKIN-TEST", validated)
        sessions = get_checkin_sessions_for_case("CHECKIN-TEST")
        self.assertEqual(len(sessions), 2)

    def test_session_not_found_raises(self):
        with self.assertRaises(ValueError):
            get_checkin_session(99999)

    def test_update_nonexistent_session_raises(self):
        with self.assertRaises(ValueError):
            update_checkin_session(99999, {"immediate_safety": "safe_now"})

    def test_all_channels_and_languages_persist(self):
        for channel in CHECKIN_CHANNELS:
            for lang in SUPPORTED_LANGUAGES:
                validated = validate_checkin_start(_valid_start_payload(channel=channel, lang=lang))
                sid = create_checkin_session("CHECKIN-TEST", validated)
                session = get_checkin_session(sid)
                self.assertEqual(session["channel"], channel)
                self.assertEqual(session["language_code"], lang)

    def test_full_journey_flow(self):
        """Complete a full check-in journey through all steps."""
        validated = validate_checkin_start(_valid_start_payload())
        session_id = create_checkin_session("CHECKIN-TEST", validated)

        # Step 1: Safety
        update_checkin_session(session_id, validate_checkin_update({"immediate_safety": "safe_now"}))
        # Step 2: Wellbeing
        update_checkin_session(session_id, validate_checkin_update({"wellbeing": "want_to_talk"}))
        # Step 3: Support choices
        update_checkin_session(session_id, validate_checkin_update({
            "support_choices": ["counselling", "legal_aid"]
        }))
        # Step 4: Complete
        update_checkin_session(session_id, validate_checkin_update({"control": "complete"}))

        session = get_checkin_session(session_id)
        self.assertEqual(session["status"], "COMPLETE")
        self.assertEqual(len(session["responses"]), 4)


if __name__ == "__main__":
    unittest.main()
