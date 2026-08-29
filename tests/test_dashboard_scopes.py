"""Tests for the district/state/national dashboard scopes.

Verifies that:
  - require_aggregate_access grants / denies the right roles at each scope.
  - get_deidentified_dashboard applies MINIMUM_AGGREGATE_CELL_SIZE suppression
    identically across all three scopes (no unsuppressed path exists).
  - Backward-compat: the old no-scope call still works for state_administrator.

Uses the same DB-patching pattern as the existing DatabasePersistenceTests in
test_checkin_journeys.py to run against a temp SQLite file with the real schema.
"""

import os
import tempfile
import unittest

import src.database as database
import src.privacy_architecture as privacy
from src.database import init_db, insert_case
from src.privacy_architecture import (
    AccessContext,
    AccessDenied,
    require_aggregate_access,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _actor(role, state="MH", district="Pune", purposes=None):
    if purposes is None:
        purposes = frozenset({"service_coordination", "authorised_reporting"})
    needs_state = role in {"counsellor", "district_officer", "state_administrator"}
    needs_district = role in {"counsellor", "district_officer"}
    return AccessContext(
        user_id=f"OP-TEST-{role.upper()}",
        role=role,
        state=state if needs_state else None,
        district=district if needs_district else None,
        purposes=purposes,
    )


# ---------------------------------------------------------------------------
# 1.  Access-control unit tests (no DB needed)
# ---------------------------------------------------------------------------

class TestRequireAggregateAccess(unittest.TestCase):

    def test_national_admin_can_access_national(self):
        self.assertTrue(
            require_aggregate_access(_actor("national_administrator"), purpose="service_coordination")
        )

    def test_national_admin_can_access_any_state(self):
        self.assertTrue(
            require_aggregate_access(_actor("national_administrator"), purpose="service_coordination", state="MH")
        )

    def test_state_admin_can_access_own_state(self):
        self.assertTrue(
            require_aggregate_access(_actor("state_administrator", state="MH"), purpose="service_coordination", state="MH")
        )

    def test_state_admin_denied_other_state(self):
        with self.assertRaises(AccessDenied):
            require_aggregate_access(_actor("state_administrator", state="MH"), purpose="service_coordination", state="KA")

    def test_district_officer_can_access_own_district(self):
        self.assertTrue(
            require_aggregate_access(
                _actor("district_officer", state="MH", district="Pune"),
                purpose="service_coordination",
                state="MH", district="Pune",
            )
        )

    def test_district_officer_denied_other_district(self):
        with self.assertRaises(AccessDenied):
            require_aggregate_access(
                _actor("district_officer", state="MH", district="Pune"),
                purpose="service_coordination",
                state="MH", district="Nashik",
            )

    def test_district_officer_denied_other_state(self):
        with self.assertRaises(AccessDenied):
            require_aggregate_access(
                _actor("district_officer", state="MH", district="Pune"),
                purpose="service_coordination",
                state="KA", district="Pune",
            )

    def test_district_officer_denied_without_district_kwarg(self):
        """No district kwarg → district_officer falls through to the general deny."""
        with self.assertRaises(AccessDenied):
            require_aggregate_access(
                _actor("district_officer", state="MH", district="Pune"),
                purpose="service_coordination",
                state="MH",
            )

    def test_counsellor_denied_aggregate(self):
        with self.assertRaises(AccessDenied):
            require_aggregate_access(_actor("counsellor"), purpose="service_coordination")

    def test_wrong_purpose_denied(self):
        with self.assertRaises(AccessDenied):
            require_aggregate_access(_actor("national_administrator"), purpose="case_review")


# ---------------------------------------------------------------------------
# 2.  Suppression + scope tests (real schema, temp SQLite)
# ---------------------------------------------------------------------------

class TestDashboardSuppression(unittest.TestCase):
    """
    Synthetic data:
      MH / Pune      – 5 cases  (above default threshold of 5)
      MH / Nashik    – 2 cases  (below default threshold → suppressed in district view)
      KA / Bengaluru – 4 cases  (above threshold)

    MINIMUM_AGGREGATE_CELL_SIZE defaults to 5 from config unless overridden by
    the NHAA_MINIMUM_AGGREGATE_CELL_SIZE env var.  We patch the module-level
    attribute so we can use a lower threshold (3) without touching the real env.
    """

    THRESHOLD = 3   # override so Nashik(2) is suppressed but Pune(5)/Bengaluru(4) pass

    def setUp(self):
        handle, self.path = tempfile.mkstemp(prefix="nhaa-dashboard-test-", suffix=".db")
        os.close(handle)

        # Patch module-level DB paths (same pattern as DatabasePersistenceTests)
        self.prev_db = database.DB_PATH
        self.prev_identity = privacy.IDENTITY_DB_PATH
        self.prev_audit = privacy.AUDIT_DB_PATH
        database.DB_PATH = self.path
        privacy.IDENTITY_DB_PATH = self.path + ".identity"
        privacy.AUDIT_DB_PATH = self.path + ".audit"
        init_db()

        # Patch MINIMUM_AGGREGATE_CELL_SIZE to a lower value for the test
        import config as cfg
        self.prev_threshold = cfg.MINIMUM_AGGREGATE_CELL_SIZE
        cfg.MINIMUM_AGGREGATE_CELL_SIZE = self.THRESHOLD

        # Insert synthetic cases
        cases = [
            ("C001", "MH", "Pune"), ("C002", "MH", "Pune"), ("C003", "MH", "Pune"),
            ("C004", "MH", "Pune"), ("C005", "MH", "Pune"),
            ("C006", "MH", "Nashik"), ("C007", "MH", "Nashik"),
            ("C008", "KA", "Bengaluru"), ("C009", "KA", "Bengaluru"),
            ("C010", "KA", "Bengaluru"), ("C011", "KA", "Bengaluru"),
        ]
        for case_id, state, district in cases:
            insert_case(case_id, state, district)

    def tearDown(self):
        import config as cfg
        cfg.MINIMUM_AGGREGATE_CELL_SIZE = self.prev_threshold

        database.DB_PATH = self.prev_db
        privacy.IDENTITY_DB_PATH = self.prev_identity
        privacy.AUDIT_DB_PATH = self.prev_audit
        for base in (self.path, self.path + ".identity", self.path + ".audit"):
            for suffix in ("", "-shm", "-wal"):
                try:
                    os.remove(base + suffix)
                except FileNotFoundError:
                    pass

    # ── National scope ──────────────────────────────────────────────────────

    def test_national_scope_has_correct_keys(self):
        actor = _actor("national_administrator")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="national")
        self.assertEqual(result["scope"], "national")
        self.assertIn("location_counts", result)
        self.assertIn("state_counts", result)      # backward-compat alias
        self.assertIn("priority_distribution", result)

    def test_national_scope_all_states_visible(self):
        actor = _actor("national_administrator")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="national")
        locations = {r["location"] for r in result["location_counts"]}
        # MH(7) and KA(4) both >= threshold(3)
        self.assertIn("MH", locations)
        self.assertIn("KA", locations)

    def test_national_scope_suppresses_below_threshold(self):
        """Suppression at the national level uses the same block as state/district."""
        import config as cfg
        cfg.MINIMUM_AGGREGATE_CELL_SIZE = 5   # KA has only 4 → should be suppressed
        try:
            actor = _actor("national_administrator")
            result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="national")
            locations = {r["location"] for r in result["location_counts"]}
            self.assertNotIn("KA", locations, "KA(4) must be suppressed when threshold=5")
        finally:
            cfg.MINIMUM_AGGREGATE_CELL_SIZE = self.THRESHOLD

    # ── State scope ─────────────────────────────────────────────────────────

    def test_state_scope_total_is_own_state_only(self):
        actor = _actor("state_administrator", state="MH")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="state")
        self.assertEqual(result["scope"], "state")
        self.assertEqual(result["total_cases"], 7)   # 5 Pune + 2 Nashik

    def test_state_scope_does_not_include_other_state(self):
        actor = _actor("state_administrator", state="MH")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="state")
        locations = {r["location"] for r in result["location_counts"]}
        self.assertNotIn("KA", locations)

    # ── District scope ───────────────────────────────────────────────────────

    def test_district_scope_pune_shows_correct_total(self):
        actor = _actor("district_officer", state="MH", district="Pune")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="district")
        self.assertEqual(result["scope"], "district")
        self.assertEqual(result["district"], "Pune")
        self.assertEqual(result["total_cases"], 5)

    def test_district_scope_nashik_suppressed_total(self):
        """Nashik has 2 cases < threshold(3) → total_cases is 'suppressed'."""
        actor = _actor("district_officer", state="MH", district="Nashik")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="district")
        self.assertEqual(result["total_cases"], "suppressed")
        self.assertEqual(result["location_counts"], [])

    def test_district_scope_does_not_include_other_district(self):
        actor = _actor("district_officer", state="MH", district="Pune")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="district")
        locations = {r["location"] for r in result["location_counts"]}
        self.assertNotIn("Nashik", locations)
        self.assertNotIn("KA", locations)

    # ── Backward-compatibility ───────────────────────────────────────────────

    def test_backward_compat_no_scope_state_administrator(self):
        actor = _actor("state_administrator", state="MH")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination")
        self.assertEqual(result["scope"], "state")

    def test_backward_compat_no_scope_national_administrator(self):
        actor = _actor("national_administrator")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination")
        self.assertEqual(result["scope"], "national")

    def test_backward_compat_state_counts_key_always_present(self):
        """page 4 reads dashboard['state_counts']; that key must never disappear."""
        actor = _actor("national_administrator")
        result = database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="national")
        self.assertIn("state_counts", result)

    # ── Cross-scope access denials ───────────────────────────────────────────

    def test_district_officer_denied_national_scope(self):
        actor = _actor("district_officer", state="MH", district="Pune")
        with self.assertRaises(AccessDenied):
            database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="national")

    def test_district_officer_denied_state_scope(self):
        actor = _actor("district_officer", state="MH", district="Pune")
        with self.assertRaises(AccessDenied):
            database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="state")

    def test_state_admin_denied_national_scope(self):
        actor = _actor("state_administrator", state="MH")
        with self.assertRaises(AccessDenied):
            database.get_deidentified_dashboard(actor, purpose="service_coordination", scope="national")


if __name__ == "__main__":
    unittest.main()
