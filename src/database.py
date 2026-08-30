"""SQLite persistence for the survivor-support triage prototype.

The schema retains a few legacy MVP fields only to read existing synthetic demo
data. New records use SPI, independent support dimensions, evidence, limitations,
and a documented human-review status.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from config import (
    APPROVED_AUTOMATIC_ESCALATION_CHANNELS,
    CRISIS_PATHWAYS,
    DB_PATH,
    DEFAULT_SPI_THRESHOLD_CONFIG,
    SAFE_OUTREACH_CHANNELS,
    SERVICE_DIRECTORY_TYPES,
    SUPPORT_PRIORITY_BANDS,
    DEFAULT_RETENTION_DAYS,
)
from src.privacy_architecture import (
    AccessContext,
    AccessDenied,
    append_security_audit,
    decrypt_text,
    encrypt_json,
    encrypt_text,
    init_audit_store,
    init_identity_store,
    redact_identity_contact,
    require_case_access,
    validate_production_transport,
)
from src.scoring import get_priority_band, normalise_threshold_config


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_column(conn, table, definition):
    """Add a column only when opening a database created by the previous MVP."""
    column = definition.split()[0]
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _priority_label(spi):
    return get_priority_band(spi)["label"]


def init_db():
    """Create the separated case/wellbeing schema and privacy-control tables."""
    validate_production_transport()
    init_identity_store()
    init_audit_store()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            district TEXT NOT NULL,
            registered_at TIMESTAMP NOT NULL,
            data_status TEXT NOT NULL DEFAULT 'ACTIVE',
            case_type TEXT NOT NULL DEFAULT 'other'
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            channel TEXT NOT NULL DEFAULT 'text',
            transcript TEXT,
            transcript_ciphertext TEXT,
            support_signals TEXT,
            support_priority_indicator REAL,
            priority_band TEXT,
            confidence TEXT,
            data_quality_limitations TEXT,
            evidence TEXT,
            physical_safety_score REAL,
            wellbeing_concern_score REAL,
            service_access_score REAL,
            consent_recorded BOOLEAN NOT NULL DEFAULT 0,
            analysis_language TEXT,
            human_review_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED',
            human_reviewed_by TEXT,
            human_reviewed_at TIMESTAMP,
            unanswered_follow_up_count INTEGER NOT NULL DEFAULT 0,
            score_version TEXT,
            threshold_version TEXT,
            model_version TEXT,
            feature_set TEXT,
            evidence_references TEXT,
            trend_status TEXT,
            trend_delta REAL,
            trend_quality_issues TEXT,
            reviewer_override TEXT,
            audio_analysis_metadata TEXT,
            audio_analysis_opt_in BOOLEAN NOT NULL DEFAULT 0,
            audio_transcription_consent_recorded BOOLEAN NOT NULL DEFAULT 0,
            audio_analysis_consent_recorded BOOLEAN NOT NULL DEFAULT 0,
            audio_quality TEXT,
            audio_language TEXT,
            audio_device_limitations TEXT,
            audio_model_uncertainty TEXT,
            raw_audio_retention_status TEXT NOT NULL DEFAULT 'not_retained',
            -- Retained only to read the v1 synthetic prototype database.
            groq_signals TEXT,
            acoustic_features TEXT,
            distress_score REAL,
            severity_band TEXT,
            shap_explanations TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            interaction_id INTEGER,
            alert_level TEXT NOT NULL,
            alert_type TEXT NOT NULL DEFAULT 'REVIEW',
            reason TEXT NOT NULL,
            recommended_intervention TEXT,
            timestamp TIMESTAMP NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'PENDING',
            reviewer_name TEXT,
            review_notes TEXT,
            reviewed_at TIMESTAMP,
            resolved BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        );

        CREATE TABLE IF NOT EXISTS crisis_workflow_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            self_harm_sla_minutes INTEGER NOT NULL DEFAULT 30 CHECK (self_harm_sla_minutes > 0),
            external_safety_sla_minutes INTEGER NOT NULL DEFAULT 30 CHECK (external_safety_sla_minutes > 0),
            default_self_harm_assignee TEXT,
            default_external_safety_assignee TEXT,
            updated_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS case_safe_contact_protocols (
            case_id TEXT PRIMARY KEY,
            protocol_label TEXT NOT NULL,
            consent_recorded BOOLEAN NOT NULL DEFAULT 0,
            allowed_channels TEXT NOT NULL DEFAULT '[]',
            safe_contact_window TEXT,
            do_not_contact_third_parties BOOLEAN NOT NULL DEFAULT 1,
            maximum_attempts INTEGER NOT NULL DEFAULT 1 CHECK (maximum_attempts BETWEEN 1 AND 3),
            minimum_retry_minutes INTEGER NOT NULL DEFAULT 240 CHECK (minimum_retry_minutes >= 0),
            enabled BOOLEAN NOT NULL DEFAULT 1,
            last_confirmed_at TIMESTAMP,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE TABLE IF NOT EXISTS crisis_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            interaction_id INTEGER NOT NULL,
            pathway TEXT NOT NULL CHECK (pathway IN ('SELF_HARM_CONCERN', 'EXTERNAL_SAFETY_THREAT')),
            priority TEXT NOT NULL CHECK (priority IN ('URGENT', 'PRIORITY')),
            status TEXT NOT NULL CHECK (status IN ('PENDING_ASSIGNMENT', 'AWAITING_ACKNOWLEDGEMENT', 'ACKNOWLEDGED', 'CLOSED')),
            assigned_to TEXT,
            assigned_role TEXT NOT NULL,
            acknowledgement_due_at TIMESTAMP NOT NULL,
            acknowledged_at TIMESTAMP,
            evidence_snapshot TEXT NOT NULL,
            context_snapshot TEXT NOT NULL,
            recommended_next_action TEXT NOT NULL,
            action_taken TEXT,
            outcome TEXT,
            follow_up_at TIMESTAMP,
            closure_rationale TEXT,
            created_at TIMESTAMP NOT NULL,
            closed_at TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        );

        CREATE TABLE IF NOT EXISTS crisis_escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crisis_event_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('QUEUED', 'BLOCKED', 'ACKNOWLEDGED')),
            reason TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            acknowledged_at TIMESTAMP,
            FOREIGN KEY (crisis_event_id) REFERENCES crisis_events(id)
        );

        CREATE TABLE IF NOT EXISTS safe_contact_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crisis_event_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('REACHED', 'NOT_REACHED')),
            attempted_at TIMESTAMP NOT NULL,
            next_eligible_at TIMESTAMP,
            recorded_by TEXT NOT NULL,
            notes TEXT NOT NULL,
            UNIQUE (crisis_event_id, attempt_number),
            FOREIGN KEY (crisis_event_id) REFERENCES crisis_events(id)
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at TIMESTAMP NOT NULL,
            event_type TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            case_id TEXT,
            actor TEXT NOT NULL,
            details TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_directory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_type TEXT NOT NULL CHECK (service_type IN ('emergency', 'counselling', 'protection', 'medical', 'legal_aid')),
            service_name TEXT NOT NULL,
            state TEXT NOT NULL,
            district TEXT,
            contact_reference TEXT NOT NULL,
            availability_notes TEXT,
            verified BOOLEAN NOT NULL DEFAULT 0,
            verified_by TEXT,
            verified_at TIMESTAMP,
            active BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS spi_threshold_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            active BOOLEAN NOT NULL DEFAULT 0,
            physical_safety_weight REAL NOT NULL,
            wellbeing_weight REAL NOT NULL,
            service_access_weight REAL NOT NULL,
            explicit_statement_weight REAL NOT NULL,
            recent_change_weight REAL NOT NULL,
            unanswered_followups_weight REAL NOT NULL,
            unanswered_followups_reference INTEGER NOT NULL,
            reported_threat_floor REAL NOT NULL,
            explicit_self_harm_floor REAL NOT NULL,
            timely_review_threshold REAL NOT NULL,
            prompt_review_threshold REAL NOT NULL,
            urgent_review_threshold REAL NOT NULL,
            material_change_points REAL NOT NULL,
            change_rationale TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS validated_screenings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            interaction_id INTEGER,
            instrument TEXT NOT NULL CHECK (instrument IN ('PHQ-9', 'GAD-7')),
            instrument_version TEXT NOT NULL,
            questionnaire_score_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('complete', 'incomplete')),
            consent_recorded BOOLEAN NOT NULL,
            questions_administered TEXT NOT NULL,
            responses TEXT NOT NULL,
            skipped_item_ids TEXT NOT NULL,
            total_score INTEGER,
            maximum_score INTEGER NOT NULL,
            requires_human_review BOOLEAN NOT NULL DEFAULT 0,
            review_reason TEXT,
            reviewer_override TEXT,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        );

        CREATE TABLE IF NOT EXISTS consent_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            purpose TEXT NOT NULL,
            channel TEXT NOT NULL,
            language TEXT NOT NULL,
            consent_version TEXT NOT NULL,
            consented_at TIMESTAMP NOT NULL,
            withdrawn_at TIMESTAMP,
            withdrawal_reason TEXT,
            contact_preferences_ciphertext TEXT,
            recorded_by TEXT NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE TABLE IF NOT EXISTS retention_policy_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            retention_days INTEGER NOT NULL CHECK (retention_days >= 0),
            active BOOLEAN NOT NULL DEFAULT 0,
            rationale TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deletion_workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            request_reason TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('PENDING_APPROVAL', 'APPROVED', 'EXECUTED', 'REJECTED')),
            requested_at TIMESTAMP NOT NULL,
            approved_by TEXT,
            approved_at TIMESTAMP,
            scheduled_for TIMESTAMP,
            executed_at TIMESTAMP,
            execution_note TEXT,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE INDEX IF NOT EXISTS idx_interactions_case ON interactions(case_id);
        CREATE INDEX IF NOT EXISTS idx_alerts_case ON alerts(case_id);
        CREATE INDEX IF NOT EXISTS idx_crisis_events_case ON crisis_events(case_id);
        CREATE INDEX IF NOT EXISTS idx_crisis_events_status ON crisis_events(status);
        CREATE INDEX IF NOT EXISTS idx_crisis_escalations_event ON crisis_escalations(crisis_event_id);
        CREATE INDEX IF NOT EXISTS idx_safe_contact_attempts_event ON safe_contact_attempts(crisis_event_id);
        CREATE INDEX IF NOT EXISTS idx_audit_events_entity ON audit_events(entity_type, entity_id);
        CREATE INDEX IF NOT EXISTS idx_spi_threshold_versions_active ON spi_threshold_versions(active);
        CREATE INDEX IF NOT EXISTS idx_validated_screenings_case ON validated_screenings(case_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_consent_ledger_case ON consent_ledger(case_id, consented_at DESC);
        CREATE INDEX IF NOT EXISTS idx_deletion_workflows_case ON deletion_workflows(case_id, status);

        CREATE TABLE IF NOT EXISTS checkin_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            language_code TEXT NOT NULL,
            consent_recorded BOOLEAN NOT NULL,
            safe_time TEXT NOT NULL,
            safe_channel TEXT NOT NULL,
            programme_mention_allowed BOOLEAN NOT NULL,
            accessibility_needs TEXT NOT NULL DEFAULT '[]',
            journey_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PAUSED', 'STOPPED', 'COMPLETE')),
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        );

        CREATE TABLE IF NOT EXISTS checkin_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            step TEXT NOT NULL,
            response_key TEXT NOT NULL,
            response_value TEXT NOT NULL,
            recorded_at TIMESTAMP NOT NULL,
            FOREIGN KEY (session_id) REFERENCES checkin_sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_checkin_sessions_case ON checkin_sessions(case_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_checkin_responses_session ON checkin_responses(session_id);

        CREATE TABLE IF NOT EXISTS model_registry (
            version TEXT PRIMARY KEY,
            model_card_url TEXT NOT NULL,
            data_sheet_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'STAGING' CHECK (status IN ('STAGING', 'PILOT', 'PRODUCTION', 'DEPRECATED', 'ROLLED_BACK')),
            created_at TIMESTAMP NOT NULL
        );

        CREATE TABLE IF NOT EXISTS domain_signoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
            reviewer TEXT,
            notes TEXT,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY (version) REFERENCES model_registry(version),
            UNIQUE (version, domain)
        );

        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            ran_at TIMESTAMP NOT NULL,
            FOREIGN KEY (version) REFERENCES model_registry(version)
        );

        CREATE TABLE IF NOT EXISTS incidents_and_drift (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            description TEXT NOT NULL,
            reported_by TEXT NOT NULL,
            reported_at TIMESTAMP NOT NULL,
            FOREIGN KEY (version) REFERENCES model_registry(version)
        );

        """
    )

    cursor.execute(
        """INSERT OR IGNORE INTO crisis_workflow_config
           (id, self_harm_sla_minutes, external_safety_sla_minutes, updated_at)
           VALUES (1, 30, 30, ?)""",
        (datetime.now().isoformat(),),
    )
    default_spi = normalise_threshold_config(DEFAULT_SPI_THRESHOLD_CONFIG)
    cursor.execute(
        """INSERT OR IGNORE INTO spi_threshold_versions (
            version, active, physical_safety_weight, wellbeing_weight, service_access_weight,
            explicit_statement_weight, recent_change_weight, unanswered_followups_weight,
            unanswered_followups_reference, reported_threat_floor, explicit_self_harm_floor,
            timely_review_threshold, prompt_review_threshold, urgent_review_threshold,
            material_change_points, change_rationale, created_by, created_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            default_spi["version"], default_spi["physical_safety_weight"], default_spi["wellbeing_weight"],
            default_spi["service_access_weight"], default_spi["explicit_statement_weight"],
            default_spi["recent_change_weight"], default_spi["unanswered_followups_weight"],
            default_spi["unanswered_followups_reference"], default_spi["reported_threat_floor"],
            default_spi["explicit_self_harm_floor"], default_spi["timely_review_threshold"],
            default_spi["prompt_review_threshold"], default_spi["urgent_review_threshold"],
            default_spi["material_change_points"], "Initial versioned non-diagnostic SPI configuration.",
            "system", datetime.now().isoformat(),
        ),
    )
    active_spi = cursor.execute(
        "SELECT id FROM spi_threshold_versions WHERE active = 1 LIMIT 1"
    ).fetchone()
    if not active_spi:
        cursor.execute(
            "UPDATE spi_threshold_versions SET active = 1 WHERE version = ?",
            (default_spi["version"],),
        )
    cursor.execute(
        """INSERT OR IGNORE INTO retention_policy_versions
           (version, retention_days, active, rationale, created_by, created_at)
           VALUES ('retention.v1', ?, 1, 'Initial configurable retention policy.', 'system', ?)""",
        (DEFAULT_RETENTION_DAYS, datetime.now().isoformat()),
    )
    cursor.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_audit_event_update
        BEFORE UPDATE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit_events are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_audit_event_delete
        BEFORE DELETE ON audit_events
        BEGIN
            SELECT RAISE(ABORT, 'audit_events are immutable');
        END;
        """
    )

    # Additive migration for a database created by the prior prototype.
    for definition in [
        "data_status TEXT NOT NULL DEFAULT 'ACTIVE'",
        "case_type TEXT NOT NULL DEFAULT 'other'",
    ]:
        _ensure_column(conn, "cases", definition)
    for definition in [
        "transcript_ciphertext TEXT",
        "support_signals TEXT",
        "support_priority_indicator REAL",
        "priority_band TEXT",
        "confidence TEXT",
        "data_quality_limitations TEXT",
        "evidence TEXT",
        "physical_safety_score REAL",
        "wellbeing_concern_score REAL",
        "service_access_score REAL",
        "consent_recorded BOOLEAN NOT NULL DEFAULT 0",
        "analysis_language TEXT",
        "human_review_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED'",
        "human_reviewed_by TEXT",
        "human_reviewed_at TIMESTAMP",
        "unanswered_follow_up_count INTEGER NOT NULL DEFAULT 0",
        "score_version TEXT",
        "threshold_version TEXT",
        "model_version TEXT",
        "feature_set TEXT",
        "evidence_references TEXT",
        "trend_status TEXT",
        "trend_delta REAL",
        "trend_quality_issues TEXT",
        "reviewer_override TEXT",
        "audio_analysis_metadata TEXT",
        "audio_analysis_opt_in BOOLEAN NOT NULL DEFAULT 0",
        "audio_transcription_consent_recorded BOOLEAN NOT NULL DEFAULT 0",
        "audio_analysis_consent_recorded BOOLEAN NOT NULL DEFAULT 0",
        "audio_quality TEXT",
        "audio_language TEXT",
        "audio_device_limitations TEXT",
        "audio_model_uncertainty TEXT",
        "raw_audio_retention_status TEXT NOT NULL DEFAULT 'not_retained'",
    ]:
        _ensure_column(conn, "interactions", definition)
    for definition in [
        "alert_type TEXT NOT NULL DEFAULT 'REVIEW'",
        "review_status TEXT NOT NULL DEFAULT 'PENDING'",
        "reviewer_name TEXT",
        "review_notes TEXT",
        "reviewed_at TIMESTAMP",
    ]:
        _ensure_column(conn, "alerts", definition)

    # Never convert the retired free-text/0–27 prototype output into an SPI or
    # a PHQ-9 total. The old number was not a validated questionnaire response.
    conn.execute(
        """UPDATE interactions
           SET support_priority_indicator = NULL,
               priority_band = 'Unavailable — legacy score retired',
               confidence = 'low', evidence = '[]', score_version = 'retired-free-text-score',
               data_quality_limitations = ?, human_review_status = 'NOT_REQUIRED'
           WHERE support_signals IS NULL AND distress_score IS NOT NULL""",
        (json.dumps([
            "Legacy free-text score retired: it was not a validated PHQ-9 or GAD-7 response and was not converted to SPI. "
            "Review source notes directly."
        ]),),
    )

    conn.execute(
        """UPDATE alerts SET alert_type = 'LEGACY'
           WHERE alert_type IS NULL OR alert_type = '' OR interaction_id IN (
               SELECT id FROM interactions WHERE support_signals IS NULL
           )"""
    )
    conn.execute(
        """UPDATE alerts
           SET reason = 'Legacy synthetic review task. A trained reviewer must assess the source notes; this task does not establish danger or a diagnosis.',
               recommended_intervention = 'Review source notes, consent, limitations, and safe-contact preferences before considering any action.'
           WHERE alert_type = 'LEGACY'"""
    )
    conn.execute(
        """UPDATE alerts
           SET review_status = CASE WHEN resolved = 1 THEN 'COMPLETED' ELSE 'PENDING' END
           WHERE review_status IS NULL OR review_status = ''"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_review_status ON alerts(review_status)")
    # Field-level encryption migration: plaintext source notes are sealed then
    # cleared. Restricted decryption is available only through
    # get_restricted_transcript after role, location, and purpose checks.
    plaintext_transcripts = conn.execute(
        "SELECT id, case_id, transcript FROM interactions WHERE transcript IS NOT NULL AND transcript_ciphertext IS NULL"
    ).fetchall()
    for row in plaintext_transcripts:
        conn.execute(
            "UPDATE interactions SET transcript_ciphertext = ?, transcript = NULL WHERE id = ?",
            (encrypt_text(row["transcript"], context=f"interaction:{row['case_id']}:transcript"), row["id"]),
        )
    conn.commit()
    conn.close()


def insert_case(case_id, state, district, registered_at=None, case_type="other"):
    """Insert an opaque case record; contact information belongs outside this demo."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO cases (case_id, state, district, registered_at, case_type) VALUES (?, ?, ?, ?, ?)",
            (case_id, state, district, registered_at or datetime.now().isoformat(), case_type),
        )
        conn.commit()
    finally:
        conn.close()


def create_scoped_case(actor: AccessContext, state: str, district: str, *, purpose: str, case_id=None, case_type="other"):
    """Create an opaque internal case ID within the caseworker's own district."""
    provisional = {"state": state, "district": district}
    try:
        require_case_access(actor, provisional, purpose=purpose, write=True)
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="CREATE_CASE", resource_type="case", resource_id="new",
            purpose=purpose, result="DENIED", details={"state": state, "district": district, "case_type": case_type},
        )
        raise
    from src.privacy_architecture import make_opaque_id
    opaque_id = case_id or make_opaque_id("CASE")
    insert_case(opaque_id, state, district, case_type=case_type)
    append_security_audit(
        actor_id=actor.user_id, action="CREATE_CASE", resource_type="case", resource_id=opaque_id,
        case_id=opaque_id, purpose=purpose, result="ALLOWED", details={"state": state, "district": district},
    )
    return opaque_id


def get_case(case_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_cases():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM cases ORDER BY registered_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_case_ids():
    conn = get_connection()
    rows = conn.execute("SELECT case_id FROM cases ORDER BY case_id").fetchall()
    conn.close()
    return [row["case_id"] for row in rows]


def get_scoped_cases(actor: AccessContext, *, purpose: str):
    """Return opaque case metadata only for an in-scope casework user."""
    if actor.role not in {"counsellor", "district_officer"}:
        append_security_audit(
            actor_id=actor.user_id, action="VIEW_CASE_LIST", resource_type="case", resource_id="district-query",
            purpose=purpose, result="DENIED", details={},
        )
        raise AccessDenied("Only district-scoped casework roles may view individual case lists.")
    # Verify the declared purpose before returning even opaque identifiers.
    require_case_access(actor, {"state": actor.state, "district": actor.district}, purpose=purpose)
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT case_id, state, district, registered_at, data_status, case_type FROM cases
               WHERE state = ? AND district = ? AND data_status = 'ACTIVE' ORDER BY registered_at DESC""",
            (actor.state, actor.district),
        ).fetchall()
    finally:
        conn.close()
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_CASE_LIST", resource_type="case", resource_id="district-query",
        purpose=purpose, result="ALLOWED", details={"state": actor.state, "district": actor.district, "count": len(rows)},
    )
    return [dict(row) for row in rows]


def get_scoped_case(actor: AccessContext, case_id: str, *, purpose: str):
    case = get_case(case_id)
    if not case or case.get("data_status") != "ACTIVE":
        return None
    try:
        require_case_access(actor, case, purpose=purpose)
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="VIEW_CASE", resource_type="case", resource_id=case_id,
            case_id=case_id, purpose=purpose, result="DENIED", details={},
        )
        raise
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_CASE", resource_type="case", resource_id=case_id,
        case_id=case_id, purpose=purpose, result="ALLOWED", details={},
    )
    return case


def record_consent(
    actor: AccessContext, case_id: str, *, purpose: str, channel: str, language: str,
    consent_version: str, contact_preferences=None,
):
    """Append a purpose-specific consent entry with encrypted contact preferences."""
    case = get_scoped_case(actor, case_id, purpose="consent_management")
    if not case:
        raise ValueError("Case not found.")
    if not all(isinstance(value, str) and value.strip() for value in [purpose, channel, language, consent_version]):
        raise ValueError("Consent purpose, channel, language, and version are required.")
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO consent_ledger
               (case_id, purpose, channel, language, consent_version, consented_at,
                contact_preferences_ciphertext, recorded_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                case_id, purpose.strip(), channel.strip(), language.strip(), consent_version.strip(),
                datetime.now().isoformat(), encrypt_json(contact_preferences or {}, context=f"consent:{case_id}:preferences"),
                actor.user_id,
            ),
        )
        _append_audit_event(
            conn, "CONSENT_RECORDED", "consent_ledger", cursor.lastrowid, case_id=case_id, actor=actor.user_id,
            details={"purpose": purpose, "channel": channel, "language": language, "version": consent_version},
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def withdraw_consent(actor: AccessContext, consent_id: int, *, purpose: str, reason: str):
    """Record withdrawal without erasing the prior consent event."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A minimal withdrawal reason is required.")
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT l.*, c.state, c.district, c.data_status
               FROM consent_ledger l JOIN cases c ON c.case_id = l.case_id WHERE l.id = ?""", (consent_id,)
        ).fetchone()
        if not row:
            raise ValueError("Consent record not found.")
        record = dict(row)
        require_case_access(actor, record, purpose="consent_management", write=True)
        if record.get("withdrawn_at"):
            raise ValueError("This consent record has already been withdrawn.")
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE consent_ledger SET withdrawn_at = ?, withdrawal_reason = ? WHERE id = ?",
            (now, reason.strip(), consent_id),
        )
        _append_audit_event(
            conn, "CONSENT_WITHDRAWN", "consent_ledger", consent_id, case_id=record["case_id"], actor=actor.user_id,
            details={"purpose": purpose},
        )
        conn.commit()
    finally:
        conn.close()


def get_active_consent(actor: AccessContext, case_id: str, *, purpose: str):
    """Read current consent history without exposing preferences to aggregate roles."""
    get_scoped_case(actor, case_id, purpose="consent_management")
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM consent_ledger WHERE case_id = ? ORDER BY consented_at DESC", (case_id,)
        ).fetchall()
    finally:
        conn.close()
    result = []
    for row in rows:
        record = dict(row)
        record["contact_preferences"] = decrypt_text(
            record.pop("contact_preferences_ciphertext", None), context=f"consent:{case_id}:preferences"
        )
        try:
            record["contact_preferences"] = json.loads(record["contact_preferences"] or "{}")
        except json.JSONDecodeError:
            record["contact_preferences"] = {}
        result.append(record)
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_CONSENT_LEDGER", resource_type="consent_ledger", resource_id=case_id,
        case_id=case_id, purpose=purpose, result="ALLOWED", details={"count": len(result)},
    )
    return result


_SPI_CONFIG_COLUMNS = (
    "physical_safety_weight", "wellbeing_weight", "service_access_weight",
    "explicit_statement_weight", "recent_change_weight", "unanswered_followups_weight",
    "unanswered_followups_reference", "reported_threat_floor", "explicit_self_harm_floor",
    "timely_review_threshold", "prompt_review_threshold", "urgent_review_threshold",
    "material_change_points",
)


def get_active_spi_threshold_config():
    """Return the active, versioned SPI settings; questionnaire totals never use it."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM spi_threshold_versions WHERE active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return normalise_threshold_config(DEFAULT_SPI_THRESHOLD_CONFIG)
    record = dict(row)
    return normalise_threshold_config({"version": record["version"], **{key: record[key] for key in _SPI_CONFIG_COLUMNS}})


def get_spi_threshold_versions():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM spi_threshold_versions ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_spi_threshold_version(config, change_rationale, *, actor):
    """Create and activate a new audited SPI version; existing versions are retained."""
    if not isinstance(change_rationale, str) or not change_rationale.strip():
        raise ValueError("A change rationale is required for every SPI threshold version.")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("An authorised configuration editor is required.")
    validated = normalise_threshold_config(config)
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        if conn.execute("SELECT 1 FROM spi_threshold_versions WHERE version = ?", (validated["version"],)).fetchone():
            raise ValueError("That SPI configuration version already exists; create a new version identifier.")
        conn.execute("UPDATE spi_threshold_versions SET active = 0 WHERE active = 1")
        conn.execute(
            """INSERT INTO spi_threshold_versions (
                version, active, physical_safety_weight, wellbeing_weight, service_access_weight,
                explicit_statement_weight, recent_change_weight, unanswered_followups_weight,
                unanswered_followups_reference, reported_threat_floor, explicit_self_harm_floor,
                timely_review_threshold, prompt_review_threshold, urgent_review_threshold,
                material_change_points, change_rationale, created_by, created_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                validated["version"], *(validated[key] for key in _SPI_CONFIG_COLUMNS),
                change_rationale.strip(), actor.strip(), now,
            ),
        )
        _append_audit_event(
            conn, "SPI_THRESHOLD_VERSION_CREATED", "spi_threshold_versions", validated["version"],
            actor=actor.strip(), details={"version": validated["version"], "change_rationale": change_rationale.strip()},
        )
        conn.commit()
    finally:
        conn.close()
    return get_active_spi_threshold_config()


def insert_validated_screening(case_id, screening, *, interaction_id=None):
    """Store a consented exact-question questionnaire record separate from SPI."""
    if not get_case(case_id):
        raise ValueError("Case not found.")
    if not isinstance(screening, dict):
        raise ValueError("A validated screening record is required.")
    required = {
        "instrument", "instrument_version", "questionnaire_score_version", "status", "consent_recorded",
        "questions_administered", "responses", "skipped_item_ids", "total_score", "maximum_score",
        "requires_human_review", "review_reason",
    }
    if not required.issubset(screening):
        raise ValueError("The screening record is missing required validation fields.")
    if screening["status"] not in {"complete", "incomplete"} or screening["instrument"] not in {"PHQ-9", "GAD-7"}:
        raise ValueError("Invalid screening instrument or completion state.")
    if type(screening["consent_recorded"]) is not bool or not screening["consent_recorded"]:
        raise ValueError("Recorded screening consent is required.")
    if screening["status"] == "incomplete" and screening["total_score"] is not None:
        raise ValueError("An incomplete questionnaire must not store a total score.")
    if screening["status"] == "complete" and type(screening["total_score"]) is not int:
        raise ValueError("A complete questionnaire must have an integer total score.")
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO validated_screenings (
                case_id, interaction_id, instrument, instrument_version, questionnaire_score_version,
                status, consent_recorded, questions_administered, responses, skipped_item_ids,
                total_score, maximum_score, requires_human_review, review_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                case_id, interaction_id, screening["instrument"], screening["instrument_version"],
                screening["questionnaire_score_version"], screening["status"], True,
                _json(screening["questions_administered"]), _json(screening["responses"]),
                _json(screening["skipped_item_ids"]), screening["total_score"], screening["maximum_score"],
                bool(screening["requires_human_review"]), screening["review_reason"], datetime.now().isoformat(),
            ),
        )
        _append_audit_event(
            conn, "VALIDATED_SCREENING_RECORDED", "validated_screening", cursor.lastrowid,
            case_id=case_id, actor="system", details={
                "instrument": screening["instrument"], "status": screening["status"],
                "total_stored": screening["total_score"] is not None,
            },
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def insert_scoped_validated_screening(actor: AccessContext, case_id, screening, *, purpose: str, interaction_id=None):
    get_scoped_case(actor, case_id, purpose=purpose)
    screening_id = insert_validated_screening(case_id, screening, interaction_id=interaction_id)
    append_security_audit(
        actor_id=actor.user_id, action="CREATE_VALIDATED_SCREENING", resource_type="validated_screening",
        resource_id=str(screening_id), case_id=case_id, purpose=purpose, result="ALLOWED",
        details={"instrument": screening.get("instrument"), "status": screening.get("status")},
    )
    return screening_id


def get_validated_screenings_for_case(case_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM validated_screenings WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
        ).fetchall()
    finally:
        conn.close()
    records = []
    for row in rows:
        record = dict(row)
        for field, fallback in (("questions_administered", []), ("responses", {}), ("skipped_item_ids", []), ("reviewer_override", {})):
            record[field] = _parse_json_field(record, field, fallback)
        records.append(record)
    return records


def get_scoped_validated_screenings(actor: AccessContext, case_id: str, *, purpose: str):
    """Return in-scope validated screenings."""
    get_scoped_case(actor, case_id, purpose=purpose)
    records = get_validated_screenings_for_case(case_id)
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_VALIDATED_SCREENINGS", resource_type="validated_screening",
        resource_id=case_id, case_id=case_id, purpose=purpose, result="ALLOWED", details={"count": len(records)},
    )
    return records


def save_interaction_reviewer_override(interaction_id, reviewer_name, rationale, review_priority=None):
    """Store a human review override without changing the calculated SPI."""
    if not isinstance(reviewer_name, str) or not reviewer_name.strip():
        raise ValueError("A named reviewer is required.")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("A reviewer override rationale is required.")
    allowed_priorities = {band["label"] for band in SUPPORT_PRIORITY_BANDS}
    if review_priority is not None and review_priority not in allowed_priorities:
        raise ValueError("Use an approved review-timeliness label or leave the override blank.")
    override = {
        "reviewer": reviewer_name.strip(), "rationale": rationale.strip(),
        "review_priority": review_priority, "recorded_at": datetime.now().isoformat(),
    }
    conn = get_connection()
    try:
        row = conn.execute("SELECT case_id FROM interactions WHERE id = ?", (interaction_id,)).fetchone()
        if not row:
            raise ValueError("Interaction not found.")
        conn.execute(
            """UPDATE interactions SET reviewer_override = ?, human_reviewed_by = ?, human_reviewed_at = ?
               WHERE id = ?""",
            (json.dumps(override), reviewer_name.strip(), override["recorded_at"], interaction_id),
        )
        _append_audit_event(
            conn, "INTERACTION_REVIEWER_OVERRIDE_RECORDED", "interaction", interaction_id,
            case_id=row["case_id"], actor=reviewer_name.strip(),
            details={"review_priority": review_priority, "spi_changed": False},
        )
        conn.commit()
    finally:
        conn.close()


def save_scoped_interaction_reviewer_override(actor: AccessContext, interaction_id, rationale, review_priority=None):
    """Record a reviewer override only for an in-scope authorised caseworker."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT i.case_id, c.state, c.district, c.data_status
               FROM interactions i JOIN cases c ON c.case_id=i.case_id WHERE i.id=?""", (interaction_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("Interaction not found.")
    require_case_access(actor, dict(row), purpose="case_review", write=True)
    save_interaction_reviewer_override(interaction_id, actor.user_id, rationale, review_priority)


def _json(value):
    return json.dumps(value) if isinstance(value, (dict, list)) else value


def _parse_json_fields(record):
    for field in [
        "support_signals", "data_quality_limitations", "evidence", "groq_signals",
        "acoustic_features", "shap_explanations", "evidence_references", "trend_quality_issues",
        "reviewer_override", "audio_analysis_metadata", "audio_device_limitations",
    ]:
        if record.get(field) and isinstance(record[field], str):
            try:
                record[field] = json.loads(record[field])
            except (json.JSONDecodeError, TypeError):
                pass
    record["has_restricted_transcript"] = bool(record.get("transcript_ciphertext"))
    # Never return a plaintext transcript from general interaction retrieval.
    # Call get_restricted_transcript() with an authorised AccessContext instead.
    record["transcript"] = None
    return record


def insert_interaction(
    case_id,
    transcript,
    groq_signals=None,
    distress_score=None,
    severity_band=None,
    channel="text",
    acoustic_features=None,
    shap_explanations=None,
    timestamp=None,
    *,
    support_signals=None,
    support_priority_indicator=None,
    priority_band=None,
    confidence="low",
    data_quality_limitations=None,
    evidence=None,
    physical_safety_score=None,
    wellbeing_concern_score=None,
    service_access_score=None,
    consent_recorded=False,
    analysis_language=None,
    human_review_status="NOT_REQUIRED",
    unanswered_follow_up_count=0,
    score_version=None,
    threshold_version=None,
    model_version=None,
    feature_set=None,
    evidence_references=None,
    trend_status=None,
    trend_delta=None,
    trend_quality_issues=None,
    reviewer_override=None,
    audio_analysis_metadata=None,
    audio_analysis_opt_in=False,
    audio_transcription_consent_recorded=False,
    audio_analysis_consent_recorded=False,
    audio_quality=None,
    audio_language=None,
    audio_device_limitations=None,
    audio_model_uncertainty=None,
    raw_audio_retention_status="not_retained",
):
    """Store a consented interaction and its non-diagnostic support assessment.

    Positional legacy arguments remain temporarily so existing synthetic seed data
    can be opened; all new application writes use the keyword-only v2 fields.
    """
    legacy_score_retired = support_priority_indicator is None and distress_score is not None
    if legacy_score_retired:
        confidence = "low"
        data_quality_limitations = data_quality_limitations or [
            "Legacy free-text score retired; it cannot be converted to PHQ-9, GAD-7, or SPI. Read source notes before acting."
        ]
        score_version = score_version or "retired-free-text-score"
    if support_priority_indicator is None and not legacy_score_retired:
        support_priority_indicator = 0.0
    if support_priority_indicator is not None:
        support_priority_indicator = round(max(0, min(100, float(support_priority_indicator))), 1)
        priority_band = priority_band or _priority_label(support_priority_indicator)
    else:
        priority_band = priority_band or "Unavailable — legacy score retired"
    if any(type(value) is not bool for value in (
        audio_analysis_opt_in, audio_transcription_consent_recorded, audio_analysis_consent_recorded,
    )):
        raise ValueError("Audio opt-in and consent flags must be booleans.")
    if audio_analysis_opt_in and not audio_analysis_consent_recorded:
        raise ValueError("Experimental audio analysis requires separate recorded consent.")
    if raw_audio_retention_status not in {"not_retained", "discarded_after_transcription"}:
        raise ValueError("This prototype cannot retain raw audio; it must be discarded after transcription.")
    if isinstance(audio_analysis_metadata, dict) and audio_analysis_metadata.get("not_used_for_alerts_or_spi") is not True:
        raise ValueError("Audio-analysis metadata must be marked as unavailable for alerts and SPI.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO interactions (
            case_id, timestamp, channel, transcript, transcript_ciphertext, support_signals,
            support_priority_indicator, priority_band, confidence,
            data_quality_limitations, evidence, physical_safety_score,
            wellbeing_concern_score, service_access_score, consent_recorded,
            analysis_language, human_review_status, groq_signals,
            unanswered_follow_up_count, score_version, threshold_version, model_version,
            feature_set, evidence_references, trend_status, trend_delta,
            trend_quality_issues, reviewer_override, acoustic_features, distress_score,
            severity_band, shap_explanations, audio_analysis_metadata,
            audio_analysis_opt_in, audio_transcription_consent_recorded, audio_analysis_consent_recorded, audio_quality,
            audio_language, audio_device_limitations, audio_model_uncertainty,
            raw_audio_retention_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            case_id,
            timestamp or datetime.now().isoformat(),
            channel,
            None,
            encrypt_text(transcript, context=f"interaction:{case_id}:transcript") if transcript else None,
            _json(support_signals),
            support_priority_indicator,
            priority_band,
            confidence,
            _json(data_quality_limitations or []),
            _json(evidence or []),
            physical_safety_score,
            wellbeing_concern_score,
            service_access_score,
            bool(consent_recorded),
            analysis_language,
            human_review_status,
            _json(groq_signals),
            max(0, int(unanswered_follow_up_count or 0)),
            score_version,
            threshold_version,
            model_version,
            feature_set,
            _json(evidence_references or []),
            trend_status,
            trend_delta,
            _json(trend_quality_issues or []),
            _json(reviewer_override) if reviewer_override else None,
            _json(acoustic_features),
            distress_score,
            severity_band,
            _json(shap_explanations),
            _json(audio_analysis_metadata) if audio_analysis_metadata else None,
            bool(audio_analysis_opt_in),
            bool(audio_transcription_consent_recorded),
            bool(audio_analysis_consent_recorded),
            audio_quality,
            audio_language,
            _json(audio_device_limitations or []),
            audio_model_uncertainty,
            raw_audio_retention_status or "not_retained",
        ),
    )
    interaction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return interaction_id


def insert_scoped_interaction(actor: AccessContext, case_id: str, *, purpose: str, **kwargs):
    """Write a consented interaction only within a caseworker's district scope."""
    try:
        get_scoped_case(actor, case_id, purpose=purpose)
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="CREATE_INTERACTION", resource_type="interaction", resource_id="new",
            case_id=case_id, purpose=purpose, result="DENIED", details={},
        )
        raise
    interaction_id = insert_interaction(case_id=case_id, **kwargs)
    append_security_audit(
        actor_id=actor.user_id, action="CREATE_INTERACTION", resource_type="interaction", resource_id=str(interaction_id),
        case_id=case_id, purpose=purpose, result="ALLOWED", details={},
    )
    return interaction_id


def get_interactions_for_case(case_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM interactions WHERE case_id = ? ORDER BY timestamp ASC", (case_id,)
    ).fetchall()
    conn.close()
    return [_parse_json_fields(dict(row)) for row in rows]


def get_scoped_interactions(actor: AccessContext, case_id: str, *, purpose: str):
    """Return in-scope metadata with transcript content redacted by default."""
    get_scoped_case(actor, case_id, purpose=purpose)
    records = get_interactions_for_case(case_id)
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_INTERACTION_METADATA", resource_type="interaction",
        resource_id=case_id, case_id=case_id, purpose=purpose, result="ALLOWED", details={"count": len(records)},
    )
    return records


def get_restricted_transcript(actor: AccessContext, interaction_id: int, *, purpose: str):
    """Decrypt a source transcript only after strict role, district, and purpose checks."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT i.id, i.case_id, i.transcript_ciphertext, c.state, c.district, c.data_status
               FROM interactions i JOIN cases c ON c.case_id = i.case_id WHERE i.id = ?""",
            (interaction_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    record = dict(row)
    try:
        require_case_access(actor, record, purpose=purpose, raw_content=True)
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="VIEW_RAW_TRANSCRIPT", resource_type="interaction",
            resource_id=str(interaction_id), case_id=record["case_id"], purpose=purpose, result="DENIED", details={},
        )
        raise
    if record.get("data_status") != "ACTIVE":
        raise AccessDenied("Restricted content is unavailable for a redacted case.")
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_RAW_TRANSCRIPT", resource_type="interaction",
        resource_id=str(interaction_id), case_id=record["case_id"], purpose=purpose, result="ALLOWED", details={},
    )
    try:
        return decrypt_text(record.get("transcript_ciphertext"), context=f"interaction:{record['case_id']}:transcript")
    except AccessDenied:
        # Compatibility only for fields encrypted during the immediately prior
        # prototype migration; new fields use the stable per-case context above.
        return decrypt_text(
            record.get("transcript_ciphertext"), context=f"interaction:{record['case_id']}:{interaction_id}:transcript"
        )


def get_latest_interactions(case_id, n=3):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM interactions WHERE case_id = ? ORDER BY timestamp DESC LIMIT ?", (case_id, n)
    ).fetchall()
    conn.close()
    return [_parse_json_fields(dict(row)) for row in rows]


def get_all_interactions():
    conn = get_connection()
    rows = conn.execute(
        """SELECT i.*, c.state, c.district FROM interactions i
           JOIN cases c ON i.case_id = c.case_id ORDER BY i.timestamp DESC"""
    ).fetchall()
    conn.close()
    return [_parse_json_fields(dict(row)) for row in rows]


def insert_alert(
    case_id,
    interaction_id,
    alert_level,
    reason,
    recommended_intervention=None,
    timestamp=None,
    *,
    alert_type="REVIEW",
):
    """Create a human-review task; it does not perform an intervention."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO alerts (
            case_id, interaction_id, alert_level, alert_type, reason,
            recommended_intervention, timestamp, review_status, resolved
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', 0)""",
        (
            case_id,
            interaction_id,
            alert_level,
            alert_type,
            reason,
            recommended_intervention,
            timestamp or datetime.now().isoformat(),
        ),
    )
    _append_audit_event(
        conn, "ALERT_CREATED", "alert", cursor.lastrowid, case_id=case_id, actor="system",
        details={"alert_type": alert_type, "alert_level": alert_level, "interaction_id": interaction_id},
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def get_active_alerts():
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, c.state, c.district FROM alerts a
           JOIN cases c ON a.case_id = c.case_id
           WHERE a.review_status = 'PENDING'
           ORDER BY CASE a.alert_level WHEN 'URGENT' THEN 0 WHEN 'PRIORITY' THEN 1 ELSE 2 END,
                    a.timestamp DESC"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_alerts():
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.*, c.state, c.district FROM alerts a
           JOIN cases c ON a.case_id = c.case_id ORDER BY a.timestamp DESC"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_scoped_alerts(actor: AccessContext, *, purpose: str, include_completed=False):
    """Return review tasks only for the caseworker's assigned district."""
    if actor.role not in {"counsellor", "district_officer"}:
        raise AccessDenied("Aggregate and audit roles cannot view individual review tasks.")
    require_case_access(actor, {"state": actor.state, "district": actor.district}, purpose=purpose)
    conn = get_connection()
    try:
        query = """
            SELECT a.*, c.state, c.district,
                   i.support_signals, i.threshold_version, i.unanswered_follow_up_count,
                   i.trend_status, i.trend_delta, i.trend_quality_issues, i.evidence
            FROM alerts a 
            JOIN cases c ON a.case_id = c.case_id
            LEFT JOIN interactions i ON a.interaction_id = i.id
            WHERE c.state=? AND c.district=? AND c.data_status='ACTIVE'
        """
        params = [actor.state, actor.district]
        if not include_completed:
            query += " AND a.review_status='PENDING'"
        query += " ORDER BY a.timestamp DESC"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_REVIEW_QUEUE", resource_type="alert", resource_id="district-query",
        purpose=purpose, result="ALLOWED", details={"count": len(rows)},
    )
    return [dict(row) for row in rows]


def complete_review(alert_id, reviewer_name, review_notes):
    """Close a task only after a named human records the review outcome."""
    if not reviewer_name or not reviewer_name.strip():
        raise ValueError("A reviewer name is required.")
    if not review_notes or not review_notes.strip():
        raise ValueError("Review notes are required before closing a task.")
    conn = get_connection()
    conn.execute(
        """UPDATE alerts
           SET review_status = 'COMPLETED', resolved = 1, reviewer_name = ?,
               review_notes = ?, reviewed_at = ?
           WHERE id = ? AND review_status = 'PENDING'""",
        (reviewer_name.strip(), review_notes.strip(), datetime.now().isoformat(), alert_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Crisis workflow, safe-contact, service-directory, and audit CRUD
# ---------------------------------------------------------------------------

def _append_audit_event(conn, event_type, entity_type, entity_id, *, case_id=None, actor="system", details=None):
    """Dual-write an immutable workflow record and hash-chained security audit."""
    cursor = conn.execute(
        """INSERT INTO audit_events
           (occurred_at, event_type, entity_type, entity_id, case_id, actor, details)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(), event_type, entity_type, str(entity_id), case_id,
            actor or "system", json.dumps(details or {}, sort_keys=True),
        ),
    )
    append_security_audit(
        actor_id=actor or "system", action=event_type, resource_type=entity_type,
        resource_id=str(entity_id), case_id=case_id, result="SYSTEM", details=details or {},
    )
    return cursor.lastrowid


def append_audit_event(event_type, entity_type, entity_id, *, case_id=None, actor="system", details=None):
    """Public append-only audit writer; UPDATE and DELETE are blocked by triggers."""
    conn = get_connection()
    try:
        audit_id = _append_audit_event(
            conn, event_type, entity_type, entity_id, case_id=case_id, actor=actor, details=details
        )
        conn.commit()
        return audit_id
    finally:
        conn.close()


def complete_scoped_review(actor: AccessContext, alert_id: int, review_notes: str, *, purpose: str):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT a.case_id, c.state, c.district, c.data_status FROM alerts a
               JOIN cases c ON c.case_id=a.case_id WHERE a.id=?""", (alert_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("Review task not found.")
    require_case_access(actor, dict(row), purpose=purpose, write=True)
    complete_review(alert_id, actor.user_id, review_notes)
    append_security_audit(
        actor_id=actor.user_id, action="COMPLETE_REVIEW", resource_type="alert", resource_id=str(alert_id),
        case_id=row["case_id"], purpose=purpose, result="ALLOWED", details={},
    )


def _parse_json_field(record, field, fallback):
    value = record.get(field)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return fallback
    return value if value is not None else fallback


def get_crisis_workflow_config():
    conn = get_connection()
    row = conn.execute("SELECT * FROM crisis_workflow_config WHERE id = 1").fetchone()
    conn.close()
    if not row:
        raise RuntimeError("Crisis workflow configuration is not initialised.")
    return dict(row)


def update_crisis_workflow_config(
    self_harm_sla_minutes,
    external_safety_sla_minutes,
    default_self_harm_assignee=None,
    default_external_safety_assignee=None,
    *,
    actor,
):
    """Set configurable SLAs and default accountable reviewers."""
    try:
        self_harm_sla_minutes = int(self_harm_sla_minutes)
        external_safety_sla_minutes = int(external_safety_sla_minutes)
    except (TypeError, ValueError) as error:
        raise ValueError("SLA values must be whole minutes.") from error
    if self_harm_sla_minutes <= 0 or external_safety_sla_minutes <= 0:
        raise ValueError("SLA values must be greater than zero.")
    if not actor or not actor.strip():
        raise ValueError("An authorised configuration editor is required.")
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE crisis_workflow_config
               SET self_harm_sla_minutes = ?, external_safety_sla_minutes = ?,
                   default_self_harm_assignee = ?, default_external_safety_assignee = ?, updated_at = ?
               WHERE id = 1""",
            (
                self_harm_sla_minutes, external_safety_sla_minutes,
                (default_self_harm_assignee or "").strip() or None,
                (default_external_safety_assignee or "").strip() or None,
                datetime.now().isoformat(),
            ),
        )
        _append_audit_event(
            conn, "CRISIS_CONFIGURATION_UPDATED", "crisis_workflow_config", "1", actor=actor.strip(),
            details={
                "self_harm_sla_minutes": self_harm_sla_minutes,
                "external_safety_sla_minutes": external_safety_sla_minutes,
                "has_default_self_harm_assignee": bool((default_self_harm_assignee or "").strip()),
                "has_default_external_safety_assignee": bool((default_external_safety_assignee or "").strip()),
            },
        )
        conn.commit()
    finally:
        conn.close()


def get_case_safe_contact_protocol(case_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM case_safe_contact_protocols WHERE case_id = ?", (case_id,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result["allowed_channels"] = _parse_json_field(result, "allowed_channels", [])
    return result


def save_case_safe_contact_protocol(
    case_id, protocol_label, consent_recorded, allowed_channels, safe_contact_window,
    do_not_contact_third_parties, maximum_attempts, minimum_retry_minutes, enabled, *, actor,
):
    """Store a consented safe-contact protocol; SMS is intentionally unavailable."""
    if not get_case(case_id):
        raise ValueError("Case not found.")
    if not protocol_label or not protocol_label.strip() or not actor or not actor.strip():
        raise ValueError("A protocol label and authorised editor are required.")
    if not isinstance(allowed_channels, list) or any(channel not in SAFE_OUTREACH_CHANNELS for channel in allowed_channels):
        raise ValueError("Only approved secure-call or secure-portal channels may be used.")
    try:
        maximum_attempts = int(maximum_attempts)
        minimum_retry_minutes = int(minimum_retry_minutes)
    except (TypeError, ValueError) as error:
        raise ValueError("Contact-attempt limits must be whole numbers.") from error
    if not 1 <= maximum_attempts <= 3 or minimum_retry_minutes < 0:
        raise ValueError("Use one to three attempts and a non-negative retry interval.")
    if enabled and not consent_recorded:
        raise ValueError("An enabled safe-contact protocol requires recorded consent.")
    if enabled and not allowed_channels:
        raise ValueError("An enabled safe-contact protocol requires at least one approved channel.")
    if not do_not_contact_third_parties:
        raise ValueError("This workflow does not permit third-party contact or disclosure.")
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO case_safe_contact_protocols
               (case_id, protocol_label, consent_recorded, allowed_channels, safe_contact_window,
                do_not_contact_third_parties, maximum_attempts, minimum_retry_minutes, enabled,
                last_confirmed_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(case_id) DO UPDATE SET
                 protocol_label = excluded.protocol_label, consent_recorded = excluded.consent_recorded,
                 allowed_channels = excluded.allowed_channels, safe_contact_window = excluded.safe_contact_window,
                 do_not_contact_third_parties = excluded.do_not_contact_third_parties,
                 maximum_attempts = excluded.maximum_attempts,
                 minimum_retry_minutes = excluded.minimum_retry_minutes, enabled = excluded.enabled,
                 last_confirmed_at = excluded.last_confirmed_at, updated_at = excluded.updated_at""",
            (
                case_id, protocol_label.strip(), bool(consent_recorded), json.dumps(allowed_channels),
                (safe_contact_window or "").strip() or None, bool(do_not_contact_third_parties),
                maximum_attempts, minimum_retry_minutes, bool(enabled), now if consent_recorded else None, now,
            ),
        )
        _append_audit_event(
            conn, "SAFE_CONTACT_PROTOCOL_SAVED", "case_safe_contact_protocol", case_id,
            case_id=case_id, actor=actor.strip(),
            details={"consent_recorded": bool(consent_recorded), "allowed_channels": allowed_channels,
                     "maximum_attempts": maximum_attempts, "minimum_retry_minutes": minimum_retry_minutes,
                     "enabled": bool(enabled)},
        )
        conn.commit()
    finally:
        conn.close()


def _get_default_assignee(config, pathway):
    field = "default_self_harm_assignee" if pathway == "SELF_HARM_CONCERN" else "default_external_safety_assignee"
    return (config.get(field) or "").strip() or None


def _sla_due_at(config, pathway, created_at):
    field = "self_harm_sla_minutes" if pathway == "SELF_HARM_CONCERN" else "external_safety_sla_minutes"
    return (created_at + timedelta(minutes=int(config[field]))).isoformat()


def _queue_internal_escalation(conn, crisis_event_id, case_id, assigned_to, actor="system"):
    """Queue only an approved internal escalation; this function never contacts a survivor."""
    channel = APPROVED_AUTOMATIC_ESCALATION_CHANNELS[0]
    if assigned_to:
        status = "QUEUED"
        reason = "Queued to the assigned accountable reviewer through the approved internal case queue."
    else:
        status = "BLOCKED"
        reason = "No accountable reviewer is configured; no escalation or outreach was sent."
    cursor = conn.execute(
        """INSERT INTO crisis_escalations
           (crisis_event_id, channel, status, reason, created_at) VALUES (?, ?, ?, ?, ?)""",
        (crisis_event_id, channel, status, reason, datetime.now().isoformat()),
    )
    _append_audit_event(
        conn, "CRISIS_ESCALATION_QUEUED" if status == "QUEUED" else "CRISIS_ESCALATION_BLOCKED",
        "crisis_escalation", cursor.lastrowid, case_id=case_id, actor=actor,
        details={"crisis_event_id": crisis_event_id, "channel": channel, "status": status},
    )
    return cursor.lastrowid


def _parse_crisis_event(row):
    result = dict(row)
    result["evidence_snapshot"] = _parse_json_field(result, "evidence_snapshot", [])
    result["context_snapshot"] = _parse_json_field(result, "context_snapshot", {})
    return result


def get_crisis_event(event_id):
    conn = get_connection()
    row = conn.execute(
        """SELECT e.*, c.state, c.district FROM crisis_events e
           JOIN cases c ON c.case_id = e.case_id WHERE e.id = ?""", (event_id,)
    ).fetchone()
    conn.close()
    return _parse_crisis_event(row) if row else None


def get_crisis_events(include_closed=False):
    conn = get_connection()
    query = """SELECT e.*, c.state, c.district FROM crisis_events e
               JOIN cases c ON c.case_id = e.case_id"""
    if not include_closed:
        query += " WHERE e.status != 'CLOSED'"
    query += " ORDER BY CASE e.priority WHEN 'URGENT' THEN 0 ELSE 1 END, e.acknowledgement_due_at ASC"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [_parse_crisis_event(row) for row in rows]


def get_scoped_crisis_events(actor: AccessContext, *, purpose: str, include_closed=False):
    """Limit crisis-review metadata to the accountable user's district scope."""
    if actor.role not in {"counsellor", "district_officer"}:
        raise AccessDenied("Aggregate and audit roles cannot view individual crisis events.")
    require_case_access(actor, {"state": actor.state, "district": actor.district}, purpose=purpose)
    events = [
        event for event in get_crisis_events(include_closed=include_closed)
        if event.get("state") == actor.state and event.get("district") == actor.district
    ]
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_CRISIS_QUEUE", resource_type="crisis_event", resource_id="district-query",
        purpose=purpose, result="ALLOWED", details={"count": len(events)},
    )
    return events


def _authorise_crisis_event(actor: AccessContext, event_id: int, *, purpose: str, write=False):
    event = get_crisis_event(event_id)
    if not event:
        raise ValueError("Crisis event not found.")
    require_case_access(actor, event, purpose=purpose, write=write)
    return event


def assign_scoped_crisis_event(actor: AccessContext, event_id: int, assigned_to: str, assigned_role: str, *, purpose: str):
    _authorise_crisis_event(actor, event_id, purpose=purpose, write=True)
    assign_crisis_event(event_id, assigned_to, assigned_role, actor=actor.user_id)
    append_security_audit(
        actor_id=actor.user_id, action="ASSIGN_CRISIS_EVENT", resource_type="crisis_event", resource_id=str(event_id),
        purpose=purpose, result="ALLOWED", details={"assigned_role": assigned_role},
    )


def acknowledge_scoped_crisis_event(actor: AccessContext, event_id: int, *, purpose: str):
    _authorise_crisis_event(actor, event_id, purpose=purpose, write=True)
    acknowledge_crisis_event(event_id, actor=actor.user_id)
    append_security_audit(
        actor_id=actor.user_id, action="ACKNOWLEDGE_CRISIS_EVENT", resource_type="crisis_event", resource_id=str(event_id),
        purpose=purpose, result="ALLOWED", details={},
    )


def record_scoped_safe_contact_attempt(actor: AccessContext, event_id: int, channel: str, outcome: str, notes: str, *, purpose: str):
    _authorise_crisis_event(actor, event_id, purpose=purpose, write=True)
    record_safe_contact_attempt(event_id, channel, outcome, notes, actor=actor.user_id)
    append_security_audit(
        actor_id=actor.user_id, action="RECORD_SAFE_CONTACT_ATTEMPT", resource_type="crisis_event", resource_id=str(event_id),
        purpose=purpose, result="ALLOWED", details={"channel": channel, "outcome": outcome},
    )


def close_scoped_crisis_event(actor: AccessContext, event_id: int, action_taken: str, outcome: str, follow_up_at, closure_rationale: str, *, purpose: str):
    _authorise_crisis_event(actor, event_id, purpose=purpose, write=True)
    close_crisis_event(event_id, action_taken, outcome, follow_up_at, closure_rationale, actor=actor.user_id)
    append_security_audit(
        actor_id=actor.user_id, action="CLOSE_CRISIS_EVENT", resource_type="crisis_event", resource_id=str(event_id),
        purpose=purpose, result="ALLOWED", details={},
    )


def get_crisis_escalations(crisis_event_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM crisis_escalations WHERE crisis_event_id = ? ORDER BY created_at ASC", (crisis_event_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_crisis_event(
    case_id, interaction_id, pathway, priority, evidence_snapshot, context_snapshot, *, actor="system",
):
    """Create a pathway-specific event, immutable audit record, and internal queue item."""
    if pathway not in CRISIS_PATHWAYS:
        raise ValueError("Unsupported crisis pathway.")
    if priority not in {"URGENT", "PRIORITY"}:
        raise ValueError("Unsupported crisis priority.")
    if not get_case(case_id):
        raise ValueError("Case not found.")
    created = datetime.now()
    config = get_crisis_workflow_config()
    assigned_to = _get_default_assignee(config, pathway)
    pathway_config = CRISIS_PATHWAYS[pathway]
    status = "AWAITING_ACKNOWLEDGEMENT" if assigned_to else "PENDING_ASSIGNMENT"
    acknowledgement_due_at = _sla_due_at(config, pathway, created)
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO crisis_events
               (case_id, interaction_id, pathway, priority, status, assigned_to, assigned_role,
                acknowledgement_due_at, evidence_snapshot, context_snapshot, recommended_next_action, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                case_id, interaction_id, pathway, priority, status, assigned_to,
                pathway_config["default_role"], acknowledgement_due_at, json.dumps(evidence_snapshot or []),
                json.dumps(context_snapshot or {}), pathway_config["suggested_next_action"], created.isoformat(),
            ),
        )
        event_id = cursor.lastrowid
        _append_audit_event(
            conn, "CRISIS_EVENT_CREATED", "crisis_event", event_id, case_id=case_id, actor=actor,
            details={"pathway": pathway, "priority": priority, "status": status,
                     "assigned_to": assigned_to, "acknowledgement_due_at": acknowledgement_due_at},
        )
        _queue_internal_escalation(conn, event_id, case_id, assigned_to, actor=actor)
        conn.commit()
    finally:
        conn.close()
    return get_crisis_event(event_id)


def assign_crisis_event(event_id, assigned_to, assigned_role, *, actor):
    """Assign an accountable reviewer and queue an approved internal escalation."""
    if not assigned_to or not assigned_to.strip() or not actor or not actor.strip():
        raise ValueError("An accountable reviewer and authorised actor are required.")
    if assigned_role not in {"Counsellor", "District safety officer"}:
        raise ValueError("Use an approved accountable role.")
    event = get_crisis_event(event_id)
    if not event or event["status"] == "CLOSED":
        raise ValueError("This crisis event cannot be assigned.")
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE crisis_events SET assigned_to = ?, assigned_role = ?, status = 'AWAITING_ACKNOWLEDGEMENT'
               WHERE id = ?""", (assigned_to.strip(), assigned_role, event_id)
        )
        _append_audit_event(
            conn, "CRISIS_EVENT_ASSIGNED", "crisis_event", event_id, case_id=event["case_id"],
            actor=actor.strip(), details={"assigned_to": assigned_to.strip(), "assigned_role": assigned_role},
        )
        _queue_internal_escalation(conn, event_id, event["case_id"], assigned_to.strip(), actor=actor.strip())
        conn.commit()
    finally:
        conn.close()


def acknowledge_crisis_event(event_id, *, actor):
    """Require accountable acknowledgement before an action or contact attempt is recorded."""
    event = get_crisis_event(event_id)
    if not event or event["status"] not in {"AWAITING_ACKNOWLEDGEMENT", "ACKNOWLEDGED"}:
        raise ValueError("This event requires an assigned reviewer before acknowledgement.")
    if not event.get("assigned_to") or event["assigned_to"] != (actor or "").strip():
        raise ValueError("Only the assigned accountable reviewer may acknowledge this event.")
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute("UPDATE crisis_events SET status = 'ACKNOWLEDGED', acknowledged_at = ? WHERE id = ?", (now, event_id))
        conn.execute(
            """UPDATE crisis_escalations SET status = 'ACKNOWLEDGED', acknowledged_at = ?
               WHERE crisis_event_id = ? AND status = 'QUEUED'""", (now, event_id)
        )
        _append_audit_event(
            conn, "CRISIS_EVENT_ACKNOWLEDGED", "crisis_event", event_id, case_id=event["case_id"],
            actor=actor.strip(), details={"acknowledged_at": now},
        )
        conn.commit()
    finally:
        conn.close()


def get_safe_contact_attempts(crisis_event_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM safe_contact_attempts WHERE crisis_event_id = ? ORDER BY attempt_number ASC",
        (crisis_event_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def record_safe_contact_attempt(crisis_event_id, channel, outcome, notes, *, actor):
    """Record a human-performed outreach attempt within an approved safe protocol.

    This function does not send a message or make a call. It enforces consent,
    approved channels, one-to-three maximum attempts, and retry spacing.
    """
    event = get_crisis_event(crisis_event_id)
    if not event or event["status"] != "ACKNOWLEDGED":
        raise ValueError("A crisis event must be acknowledged before recording a contact attempt.")
    if event.get("assigned_to") != (actor or "").strip():
        raise ValueError("Only the assigned reviewer may record a contact attempt.")
    if channel not in SAFE_OUTREACH_CHANNELS or outcome not in {"REACHED", "NOT_REACHED"}:
        raise ValueError("Use an approved safe channel and a supported outcome.")
    if not notes or not notes.strip():
        raise ValueError("A brief contact-attempt note is required.")
    protocol = get_case_safe_contact_protocol(event["case_id"])
    if not protocol or not protocol["enabled"] or not protocol["consent_recorded"]:
        raise ValueError("No enabled, consented safe-contact protocol is available for this case.")
    if channel not in protocol["allowed_channels"]:
        raise ValueError("This channel is not authorised by the case safe-contact protocol.")
    attempts = get_safe_contact_attempts(crisis_event_id)
    if len(attempts) >= int(protocol["maximum_attempts"]):
        raise ValueError("The case safe-contact protocol has reached its maximum attempt count.")
    now = datetime.now()
    if attempts and attempts[-1].get("next_eligible_at"):
        next_eligible = datetime.fromisoformat(attempts[-1]["next_eligible_at"])
        if now < next_eligible:
            raise ValueError("The configured safe-contact retry interval has not elapsed.")
    attempt_number = len(attempts) + 1
    next_eligible_at = None
    if outcome == "NOT_REACHED" and attempt_number < int(protocol["maximum_attempts"]):
        next_eligible_at = (now + timedelta(minutes=int(protocol["minimum_retry_minutes"]))).isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO safe_contact_attempts
               (crisis_event_id, channel, attempt_number, outcome, attempted_at, next_eligible_at, recorded_by, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                crisis_event_id, channel, attempt_number, outcome, now.isoformat(), next_eligible_at,
                actor.strip(), notes.strip(),
            ),
        )
        _append_audit_event(
            conn, "SAFE_CONTACT_ATTEMPT_RECORDED", "safe_contact_attempt", cursor.lastrowid,
            case_id=event["case_id"], actor=actor.strip(),
            details={"crisis_event_id": crisis_event_id, "channel": channel, "outcome": outcome,
                     "attempt_number": attempt_number, "next_eligible_at": next_eligible_at},
        )
        conn.commit()
    finally:
        conn.close()


def close_crisis_event(event_id, action_taken, outcome, follow_up_at, closure_rationale, *, actor):
    """Close an acknowledged event only after a documented human outcome."""
    event = get_crisis_event(event_id)
    if not event or event["status"] != "ACKNOWLEDGED":
        raise ValueError("Only an acknowledged crisis event can be closed.")
    if event.get("assigned_to") != (actor or "").strip():
        raise ValueError("Only the assigned reviewer may close this event.")
    if not all(isinstance(item, str) and item.strip() for item in [action_taken, outcome, closure_rationale]):
        raise ValueError("Action taken, outcome, and closure rationale are all required.")
    if not follow_up_at:
        raise ValueError("A follow-up date is required before closure.")
    if hasattr(follow_up_at, "isoformat"):
        follow_up_at = follow_up_at.isoformat()
    if not isinstance(follow_up_at, str):
        raise ValueError("Follow-up date is invalid.")
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE crisis_events SET status = 'CLOSED', action_taken = ?, outcome = ?,
               follow_up_at = ?, closure_rationale = ?, closed_at = ? WHERE id = ?""",
            (action_taken.strip(), outcome.strip(), follow_up_at, closure_rationale.strip(), now, event_id),
        )
        _append_audit_event(
            conn, "CRISIS_EVENT_CLOSED", "crisis_event", event_id, case_id=event["case_id"],
            actor=actor.strip(), details={"follow_up_at": follow_up_at, "outcome_recorded": True},
        )
        conn.commit()
    finally:
        conn.close()


def add_service_directory_entry(
    service_type, service_name, state, district, contact_reference, availability_notes, *, actor,
):
    """Add an unverified local service entry; unverified entries cannot be offered as verified."""
    if service_type not in SERVICE_DIRECTORY_TYPES:
        raise ValueError("Use an approved service type.")
    if not all(isinstance(item, str) and item.strip() for item in [service_name, state, contact_reference, actor]):
        raise ValueError("Service name, State, contact reference, and editor are required.")
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO service_directory
               (service_type, service_name, state, district, contact_reference, availability_notes,
                verified, active, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?)""",
            (
                service_type, service_name.strip(), state.strip(), (district or "").strip() or None,
                contact_reference.strip(), (availability_notes or "").strip() or None, now, now,
            ),
        )
        _append_audit_event(
            conn, "SERVICE_DIRECTORY_ENTRY_ADDED", "service_directory", cursor.lastrowid,
            actor=actor.strip(), details={"service_type": service_type, "verified": False},
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def verify_service_directory_entry(service_id, *, actor):
    """Mark a service entry verified after an authorised staff member checks it."""
    if not actor or not actor.strip():
        raise ValueError("A verifier name or authorised staff ID is required.")
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM service_directory WHERE id = ?", (service_id,)).fetchone()
        if not row:
            raise ValueError("Service directory entry not found.")
        conn.execute(
            """UPDATE service_directory SET verified = 1, verified_by = ?, verified_at = ?, updated_at = ?
               WHERE id = ?""", (actor.strip(), now, now, service_id)
        )
        _append_audit_event(
            conn, "SERVICE_DIRECTORY_ENTRY_VERIFIED", "service_directory", service_id,
            actor=actor.strip(), details={"service_type": row["service_type"]},
        )
        conn.commit()
    finally:
        conn.close()


def get_service_directory_entries(state=None, district=None, *, verified_only=False):
    conn = get_connection()
    clauses, params = ["active = 1"], []
    if state:
        clauses.append("state = ?")
        params.append(state)
    if district:
        clauses.append("(district = ? OR district IS NULL)")
        params.append(district)
    if verified_only:
        clauses.append("verified = 1")
    rows = conn.execute(
        "SELECT * FROM service_directory WHERE " + " AND ".join(clauses) + " ORDER BY service_type, service_name",
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_audit_events(entity_type=None, entity_id=None, case_id=None, limit=100):
    conn = get_connection()
    clauses, params = [], []
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        params.append(str(entity_id))
    if case_id:
        clauses.append("case_id = ?")
        params.append(case_id)
    query = "SELECT * FROM audit_events"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY occurred_at DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(query, params).fetchall()
    conn.close()
    results = []
    for row in rows:
        record = dict(row)
        record["details"] = _parse_json_field(record, "details", {})
        results.append(record)
    return results


def get_cases_by_state():
    conn = get_connection()
    rows = conn.execute(
        "SELECT state, COUNT(*) AS count FROM cases GROUP BY state ORDER BY count DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_priority_distribution():
    """Count the latest support-priority band per case, grouped by state."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.state, i.priority_band, COUNT(*) AS count
           FROM cases c JOIN (
             SELECT case_id, priority_band,
                    ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY timestamp DESC) AS rn
             FROM interactions
           ) i ON c.case_id = i.case_id AND i.rn = 1
           GROUP BY c.state, i.priority_band"""
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_dashboard_stats():
    conn = get_connection()
    stats = {
        "total_cases": conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0],
        "total_interactions": conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0],
        "pending_reviews": conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE review_status = 'PENDING'"
        ).fetchone()[0],
    }
    priority_rows = conn.execute(
        """SELECT priority_band, COUNT(*) AS count FROM (
             SELECT case_id, priority_band,
                    ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY timestamp DESC) AS rn
             FROM interactions
           ) WHERE rn = 1 GROUP BY priority_band"""
    ).fetchall()
    stats["priority_counts"] = {row["priority_band"]: row["count"] for row in priority_rows}
    stats["urgent_reviews"] = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE review_status = 'PENDING' AND alert_level = 'URGENT'"
    ).fetchone()[0]
    stats["pending_crisis_events"] = conn.execute(
        "SELECT COUNT(*) FROM crisis_events WHERE status != 'CLOSED'"
    ).fetchone()[0]
    stats["overdue_crisis_acknowledgements"] = conn.execute(
        """SELECT COUNT(*) FROM crisis_events
           WHERE status IN ('PENDING_ASSIGNMENT', 'AWAITING_ACKNOWLEDGEMENT')
             AND acknowledgement_due_at < ?""",
        (datetime.now().isoformat(),),
    ).fetchone()[0]
    conn.close()
    return stats


def get_deidentified_dashboard(actor: AccessContext, *, purpose: str, scope: str | None = None):
    """Return only aggregate, small-cell-suppressed coordination metrics.

    ``scope`` controls which geographic level is queried:

    - ``"district"`` – actor's own district only (``district_officer``).
    - ``"state"``    – actor's own state only (``state_administrator``).
    - ``"national"`` – all states (``national_administrator``).
    - ``None``       – inferred from role for backward-compatibility.

    All three scopes go through the same WHERE-clause builder and the same
    suppression block so ``MINIMUM_AGGREGATE_CELL_SIZE`` is guaranteed to apply
    everywhere.
    """
    from config import MINIMUM_AGGREGATE_CELL_SIZE
    from src.privacy_architecture import require_aggregate_access

    # ── Resolve scope ────────────────────────────────────────────────────────
    if scope is None:
        if actor.role == "state_administrator":
            scope = "state"
        elif actor.role == "district_officer":
            scope = "district"
        else:
            scope = "national"

    # ── Authorise ────────────────────────────────────────────────────────────
    auth_state = actor.state if scope in ("state", "district") else None
    auth_district = actor.district if scope == "district" else None
    try:
        require_aggregate_access(
            actor, purpose=purpose, state=auth_state, district=auth_district
        )
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="VIEW_DEIDENTIFIED_DASHBOARD",
            resource_type="aggregate_dashboard",
            resource_id=f"{auth_state or 'national'}/{auth_district or ''}".rstrip("/"),
            purpose=purpose, result="DENIED", details={},
        )
        raise

    # ── Build WHERE params and GROUP BY column ───────────────────────────────
    if scope == "district":
        where_clause = "WHERE c.data_status = 'ACTIVE' AND c.state = ? AND c.district = ?"
        count_where = "WHERE data_status = 'ACTIVE' AND state = ? AND district = ?"
        count_params = [actor.state, actor.district]
        group_col = "c.district"
        location_col = "district"
    elif scope == "state":
        where_clause = "WHERE c.data_status = 'ACTIVE' AND c.state = ?"
        count_where = "WHERE data_status = 'ACTIVE' AND state = ?"
        count_params = [actor.state]
        group_col = "c.state"
        location_col = "state"
    else:  # national
        where_clause = "WHERE c.data_status = 'ACTIVE'"
        count_where = "WHERE data_status = 'ACTIVE'"
        count_params = []
        group_col = "c.state"
        location_col = "state"

    conn = get_connection()
    try:
        total_cases = conn.execute(
            f"SELECT COUNT(*) FROM cases {count_where}", count_params
        ).fetchone()[0]

        # Suppress low-count cells to reduce re-identification risk. No case IDs,
        # names, contact details, transcripts, audio, or sub-district rows returned.
        location_rows = conn.execute(
            f"""SELECT {group_col} AS location, COUNT(*) AS count
                FROM cases c
                {where_clause}
                GROUP BY {group_col}
                ORDER BY {group_col}""",
            count_params,
        ).fetchall()

        priority_rows = conn.execute(
            f"""SELECT {group_col} AS location, i.priority_band, COUNT(*) AS count
                FROM cases c
                JOIN (
                    SELECT case_id, priority_band,
                           ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY timestamp DESC) AS rn
                    FROM interactions
                ) i ON i.case_id = c.case_id AND i.rn = 1
                {where_clause}
                GROUP BY {group_col}, i.priority_band""",
            count_params,
        ).fetchall()

        case_type_rows = conn.execute(
            f"""SELECT c.case_type, COUNT(*) AS count
                FROM cases c
                {where_clause}
                GROUP BY c.case_type""",
            count_params,
        ).fetchall()

        case_type_priority_rows = conn.execute(
            f"""SELECT c.case_type, i.priority_band, COUNT(*) AS count
                FROM cases c
                JOIN (
                    SELECT case_id, priority_band,
                           ROW_NUMBER() OVER (PARTITION BY case_id ORDER BY timestamp DESC) AS rn
                    FROM interactions
                ) i ON i.case_id = c.case_id AND i.rn = 1
                {where_clause}
                GROUP BY c.case_type, i.priority_band""",
            count_params,
        ).fetchall()
    finally:
        conn.close()

    # ── Apply small-cell suppression (single shared block for all scopes) ────
    suppressed_locations = [
        dict(row) for row in location_rows if row["count"] >= MINIMUM_AGGREGATE_CELL_SIZE
    ]
    suppressed_priorities = [
        dict(row) for row in priority_rows if row["count"] >= MINIMUM_AGGREGATE_CELL_SIZE
    ]
    suppressed_case_types = [
        dict(row) for row in case_type_rows if row["count"] >= MINIMUM_AGGREGATE_CELL_SIZE
    ]
    suppressed_case_type_priorities = [
        dict(row) for row in case_type_priority_rows if row["count"] >= MINIMUM_AGGREGATE_CELL_SIZE
    ]

    resource_id = (
        f"{actor.state}/{actor.district}" if scope == "district"
        else actor.state if scope == "state"
        else "national"
    )
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_DEIDENTIFIED_DASHBOARD",
        resource_type="aggregate_dashboard", resource_id=resource_id,
        purpose=purpose, result="ALLOWED",
        details={"scope": scope, "small_cell_threshold": MINIMUM_AGGREGATE_CELL_SIZE},
    )
    return {
        "scope": scope,
        "state": actor.state if scope in ("state", "district") else None,
        "district": actor.district if scope == "district" else None,
        "location_col": location_col,
        "total_cases": total_cases if total_cases >= MINIMUM_AGGREGATE_CELL_SIZE else "suppressed",
        "state_counts": suppressed_locations,   # kept for page-4 backward-compat
        "location_counts": suppressed_locations,
        "priority_distribution": suppressed_priorities,
        "case_type_distribution": suppressed_case_types,
        "case_type_priority_distribution": suppressed_case_type_priorities,
        "small_cell_threshold": MINIMUM_AGGREGATE_CELL_SIZE,
    }


def export_deidentified_dashboard(actor: AccessContext, *, purpose: str, scope: str | None = None):
    """Authorise aggregate-only export; individual and raw-content exports are blocked."""
    from src.privacy_architecture import require_export_access
    try:
        require_export_access(actor, purpose=purpose, export_kind="aggregate")
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="EXPORT_DEIDENTIFIED_DASHBOARD",
            resource_type="aggregate_dashboard",
            resource_id=actor.state or "national", purpose=purpose, result="DENIED", details={},
        )
        raise
    result = get_deidentified_dashboard(actor, purpose=purpose, scope=scope)
    append_security_audit(
        actor_id=actor.user_id, action="EXPORT_DEIDENTIFIED_DASHBOARD",
        resource_type="aggregate_dashboard",
        resource_id=result.get("district") or result.get("state") or "national",
        purpose=purpose, result="ALLOWED", details={},
    )
    return result


def create_retention_policy(actor: AccessContext, *, version: str, retention_days: int, rationale: str):
    """Version retention rules; the old rule remains recorded for auditability."""
    from src.privacy_architecture import require_aggregate_access
    require_aggregate_access(actor, purpose="authorised_reporting")
    if not all(isinstance(item, str) and item.strip() for item in [version, rationale]):
        raise ValueError("Retention policy version and rationale are required.")
    if type(retention_days) is not int or retention_days < 0:
        raise ValueError("Retention days must be a non-negative whole number.")
    conn = get_connection()
    try:
        conn.execute("UPDATE retention_policy_versions SET active = 0 WHERE active = 1")
        cursor = conn.execute(
            """INSERT INTO retention_policy_versions
               (version, retention_days, active, rationale, created_by, created_at)
               VALUES (?, ?, 1, ?, ?, ?)""",
            (version.strip(), retention_days, rationale.strip(), actor.user_id, datetime.now().isoformat()),
        )
        _append_audit_event(
            conn, "RETENTION_POLICY_CREATED", "retention_policy", cursor.lastrowid, actor=actor.user_id,
            details={"version": version, "retention_days": retention_days},
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def request_case_deletion(actor: AccessContext, case_id: str, *, purpose: str, reason: str):
    """Create a two-person deletion request; no immediate destructive action occurs."""
    case = get_scoped_case(actor, case_id, purpose=purpose)
    if not case:
        raise ValueError("Case not found.")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("A deletion request reason is required.")
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO deletion_workflows
               (case_id, requested_by, request_reason, status, requested_at)
               VALUES (?, ?, ?, 'PENDING_APPROVAL', ?)""",
            (case_id, actor.user_id, reason.strip(), datetime.now().isoformat()),
        )
        _append_audit_event(
            conn, "DELETION_REQUESTED", "deletion_workflow", cursor.lastrowid, case_id=case_id, actor=actor.user_id,
            details={},
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def approve_case_deletion(actor: AccessContext, workflow_id: int, *, purpose: str, scheduled_for=None):
    """Require a different state/national administrator to approve a deletion request."""
    from src.privacy_architecture import require_aggregate_access
    require_aggregate_access(actor, purpose=purpose)
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM deletion_workflows WHERE id = ?", (workflow_id,)).fetchone()
        if not row:
            raise ValueError("Deletion workflow not found.")
        record = dict(row)
        if record["status"] != "PENDING_APPROVAL" or record["requested_by"] == actor.user_id:
            raise AccessDenied("Deletion needs a pending request and approval by a different authorised person.")
        due = scheduled_for.isoformat() if hasattr(scheduled_for, "isoformat") else (scheduled_for or datetime.now().isoformat())
        now = datetime.now().isoformat()
        conn.execute(
            """UPDATE deletion_workflows SET status='APPROVED', approved_by=?, approved_at=?, scheduled_for=?
               WHERE id=?""", (actor.user_id, now, due, workflow_id)
        )
        _append_audit_event(
            conn, "DELETION_APPROVED", "deletion_workflow", workflow_id, case_id=record["case_id"], actor=actor.user_id,
            details={"scheduled_for": due},
        )
        conn.commit()
    finally:
        conn.close()


def execute_approved_deletion(actor: AccessContext, workflow_id: int, *, purpose: str):
    """Cryptographically erase identity/contact and source-content fields, retaining audit facts."""
    from src.privacy_architecture import require_aggregate_access
    require_aggregate_access(actor, purpose=purpose)
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM deletion_workflows WHERE id = ?", (workflow_id,)).fetchone()
        if not row:
            raise ValueError("Deletion workflow not found.")
        record = dict(row)
        if record["status"] != "APPROVED" or record.get("scheduled_for", "") > datetime.now().isoformat():
            raise AccessDenied("Only a due, approved deletion workflow can be executed.")
        case_id = record["case_id"]
        conn.execute("UPDATE cases SET data_status = 'REDACTED' WHERE case_id = ?", (case_id,))
        conn.execute(
            """UPDATE interactions SET transcript=NULL, transcript_ciphertext=NULL, support_signals=NULL,
               evidence='[]', audio_analysis_metadata=NULL, acoustic_features=NULL,
               raw_audio_retention_status='not_retained' WHERE case_id=?""", (case_id,)
        )
        conn.execute(
            """UPDATE consent_ledger SET contact_preferences_ciphertext=NULL WHERE case_id=?""", (case_id,)
        )
        conn.execute(
            """UPDATE deletion_workflows SET status='EXECUTED', executed_at=?, execution_note=? WHERE id=?""",
            (datetime.now().isoformat(), "Identity and source content cryptographically erased; minimal audit facts retained.", workflow_id),
        )
        _append_audit_event(
            conn, "DELETION_EXECUTED", "deletion_workflow", workflow_id, case_id=case_id, actor=actor.user_id,
            details={"method": "cryptographic_erasure_and_redaction"},
        )
        conn.commit()
    finally:
        conn.close()
    redact_identity_contact(case_id)


def get_deletion_workflows(actor: AccessContext, *, purpose: str):
    """Read deletion workflows without exposing source content or identity fields."""
    from src.privacy_architecture import require_aggregate_access
    require_aggregate_access(actor, purpose=purpose)
    conn = get_connection()
    try:
        query = """SELECT d.*, c.state, c.district FROM deletion_workflows d
                   JOIN cases c ON c.case_id=d.case_id"""
        params = []
        if actor.role == "state_administrator":
            query += " WHERE c.state=?"
            params.append(actor.state)
        query += " ORDER BY d.requested_at DESC"
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_DELETION_WORKFLOWS", resource_type="deletion_workflow",
        resource_id=actor.state or "national", purpose=purpose, result="ALLOWED", details={"count": len(rows)},
    )
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Check-in session persistence
# ---------------------------------------------------------------------------

def create_checkin_session(case_id: str, validated_start: dict) -> int:
    """Persist a new check-in session after consent-and-contact validation.

    The *validated_start* dict must already have been through
    ``checkin_journeys.validate_checkin_start``.
    """
    from config import CHECKIN_JOURNEY_VERSION
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO checkin_sessions
               (case_id, channel, language_code, consent_recorded, safe_time,
                safe_channel, programme_mention_allowed, accessibility_needs,
                journey_version, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)""",
            (
                case_id, validated_start["channel"], validated_start["language_code"],
                validated_start["consent_recorded"], validated_start["safe_time"],
                validated_start["safe_channel"], validated_start["programme_mention_allowed"],
                json.dumps(validated_start["accessibility_needs"]),
                CHECKIN_JOURNEY_VERSION, now, now,
            ),
        )
        session_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()
    return session_id


def update_checkin_session(session_id: int, validated_update: dict) -> dict:
    """Record one or more journey responses and update session status."""
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        session = conn.execute(
            "SELECT * FROM checkin_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise ValueError("Check-in session not found.")
        for key, value in validated_update.items():
            serialised = json.dumps(value) if isinstance(value, (list, dict, bool)) else str(value)
            conn.execute(
                "INSERT INTO checkin_responses (session_id, step, response_key, response_value, recorded_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, key, key, serialised, now),
            )
        new_status = "OPEN"
        control = validated_update.get("control")
        if control == "pause":
            new_status = "PAUSED"
        elif control == "stop":
            new_status = "STOPPED"
        elif control == "complete":
            new_status = "COMPLETE"
        conn.execute(
            "UPDATE checkin_sessions SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, session_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM checkin_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    return dict(updated)


def get_checkin_sessions_for_case(case_id: str) -> list[dict]:
    """Return all check-in sessions for a case, newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM checkin_sessions WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_checkin_session(session_id: int) -> dict:
    """Return a single check-in session with all its responses."""
    conn = get_connection()
    try:
        session = conn.execute(
            "SELECT * FROM checkin_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if not session:
            raise ValueError("Check-in session not found.")
        responses = conn.execute(
            "SELECT * FROM checkin_responses WHERE session_id = ? ORDER BY recorded_at",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    result = dict(session)
    result["responses"] = [dict(r) for r in responses]
    return result


# ---------------------------------------------------------------------------
# Pre-Deployment Governance CRUD
# ---------------------------------------------------------------------------

def insert_model_version(version: str, model_card_url: str, data_sheet_url: str) -> None:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO model_registry (version, model_card_url, data_sheet_url, status, created_at)
               VALUES (?, ?, ?, 'STAGING', ?)""",
            (version, model_card_url, data_sheet_url, now),
        )
        # Initialize pending signoffs
        from config import GOVERNANCE_DOMAINS
        for domain in GOVERNANCE_DOMAINS:
            conn.execute(
                """INSERT INTO domain_signoffs (version, domain, status, updated_at)
                   VALUES (?, ?, 'PENDING', ?)""",
                (version, domain, now),
            )
        conn.commit()
    finally:
        conn.close()


def get_model_versions() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM model_registry ORDER BY created_at DESC").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_domain_signoffs(version: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM domain_signoffs WHERE version = ?", (version,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def update_domain_signoff(version: str, domain: str, status: str, reviewer: str, notes: str) -> None:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE domain_signoffs 
               SET status = ?, reviewer = ?, notes = ?, updated_at = ?
               WHERE version = ? AND domain = ?""",
            (status, reviewer, notes, now, version, domain),
        )
        conn.commit()
    finally:
        conn.close()


def insert_evaluation_run(version: str, metrics: dict) -> None:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO evaluation_runs (version, metrics_json, ran_at) VALUES (?, ?, ?)",
            (version, json.dumps(metrics), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_evaluation_runs(version: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM evaluation_runs WHERE version = ? ORDER BY ran_at DESC", (version,)).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def update_model_status(version: str, new_status: str) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE model_registry SET status = ? WHERE version = ?", (new_status, version))
        conn.commit()
    finally:
        conn.close()


def insert_incident(version: str, incident_type: str, description: str, reported_by: str) -> None:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO incidents_and_drift (version, incident_type, description, reported_by, reported_at)
               VALUES (?, ?, ?, ?, ?)""",
            (version, incident_type, description, reported_by, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_incidents() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM incidents_and_drift ORDER BY reported_at DESC").fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]

