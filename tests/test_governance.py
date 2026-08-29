"""Tests for the Pre-Deployment Governance Module.

Verifies that model promotion enforces domain sign-offs and offline 
metrics thresholds, and tests the rollback functionality.
"""

import os
import tempfile
import unittest
import json

from src.database import (
    init_db,
    get_model_versions,
    get_domain_signoffs,
    update_domain_signoff,
    insert_evaluation_run,
)
from src.governance import (
    register_new_version,
    simulate_offline_evaluation,
    promote_to_production,
    rollback_version,
    GovernanceValidationError,
)
from config import GOVERNANCE_DOMAINS
import src.database as database
import src.privacy_architecture as privacy


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(prefix="nhaa-gov-test-", suffix=".db")
        os.close(handle)
        self.previous_path = database.DB_PATH
        self.previous_identity_path = privacy.IDENTITY_DB_PATH
        self.previous_audit_path = privacy.AUDIT_DB_PATH
        database.DB_PATH = self.path
        privacy.IDENTITY_DB_PATH = self.path + ".identity"
        privacy.AUDIT_DB_PATH = self.path + ".audit"
        init_db()

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

    def test_register_creates_pending_signoffs(self):
        version = "test-v1"
        register_new_version(version, "url", "url")
        versions = get_model_versions()
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]["status"], "STAGING")
        
        signoffs = get_domain_signoffs(version)
        self.assertEqual(len(signoffs), len(GOVERNANCE_DOMAINS))
        for s in signoffs:
            self.assertEqual(s["status"], "PENDING")

    def test_cannot_promote_without_signoffs(self):
        version = "test-v2"
        register_new_version(version, "url", "url")
        simulate_offline_evaluation(version)
        
        with self.assertRaisesRegex(GovernanceValidationError, "Missing or rejected approvals"):
            promote_to_production(version)

    def test_cannot_promote_without_evaluation(self):
        version = "test-v3"
        register_new_version(version, "url", "url")
        # Approve all signoffs
        for domain in GOVERNANCE_DOMAINS:
            update_domain_signoff(version, domain, "APPROVED", "reviewer1", "ok")
            
        with self.assertRaisesRegex(GovernanceValidationError, "without an offline evaluation run"):
            promote_to_production(version)

    def test_cannot_promote_if_metrics_fail_threshold(self):
        version = "test-v4"
        register_new_version(version, "url", "url")
        for domain in GOVERNANCE_DOMAINS:
            update_domain_signoff(version, domain, "APPROVED", "reviewer1", "ok")
            
        bad_metrics = {
            "global": {
                "sensitivity": 0.50,  # Below threshold
                "precision": 0.90,
                "false_negative_urgent": 0.005,
                "false_alert_burden": 0.10,
            }
        }
        insert_evaluation_run(version, bad_metrics)
        
        with self.assertRaisesRegex(GovernanceValidationError, "Sensitivity falls below"):
            promote_to_production(version)

    def test_successful_promotion_and_demotion_of_old_version(self):
        v1 = "v1"
        v2 = "v2"
        register_new_version(v1, "url", "url")
        simulate_offline_evaluation(v1)
        for domain in GOVERNANCE_DOMAINS:
            update_domain_signoff(v1, domain, "APPROVED", "r", "ok")
        
        promote_to_production(v1)
        self.assertEqual(get_model_versions()[-1]["status"], "PRODUCTION")
        
        register_new_version(v2, "url", "url")
        simulate_offline_evaluation(v2)
        for domain in GOVERNANCE_DOMAINS:
            update_domain_signoff(v2, domain, "APPROVED", "r", "ok")
            
        promote_to_production(v2)
        
        versions = {v["version"]: v["status"] for v in get_model_versions()}
        self.assertEqual(versions[v2], "PRODUCTION")
        self.assertEqual(versions[v1], "DEPRECATED")

    def test_rollback(self):
        v1 = "v1"
        register_new_version(v1, "url", "url")
        rollback_version(v1)
        
        versions = get_model_versions()
        self.assertEqual(versions[0]["status"], "ROLLED_BACK")


if __name__ == "__main__":
    unittest.main()
