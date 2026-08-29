"""Privacy, access-control, encryption, and audit primitives.

This module is the application boundary for identifiable or restricted content.
It separates identity/contact records from case/wellbeing records, encrypts
individual sensitive fields, and records security-relevant actions in a
hash-chained immutable audit store. Production deployment must inject verified
user claims, KMS-managed keys, managed encrypted storage, and TLS endpoints;
the isolated SQLite mode exists only for local development and automated tests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from config import (
    AUDIT_DB_PATH,
    DATABASE_URL,
    DEPLOYMENT_ENVIRONMENT,
    FIELD_ENCRYPTION_KEY_ENV,
    FIELD_ENCRYPTION_KEY_VERSION,
    IDENTITY_DB_PATH,
    LOCAL_DEVELOPMENT_KEY_PATH,
    ROLE_NAMES,
    PRODUCTION_STORAGE_BACKEND,
    STORAGE_BACKEND,
)


class AccessDenied(PermissionError):
    """Raised for an unauthorised role, location, purpose, or export."""


class SecurityConfigurationError(RuntimeError):
    """Raised when a production deployment lacks required security controls."""


def _root_key() -> bytes:
    """Read the KMS key; local development uses a protected persistent key file."""
    configured = os.environ.get(FIELD_ENCRYPTION_KEY_ENV)
    if configured:
        try:
            decoded = base64.urlsafe_b64decode(configured.encode("ascii"))
            if len(decoded) != 32:
                raise ValueError
            return decoded
        except Exception as error:
            raise SecurityConfigurationError(
                f"{FIELD_ENCRYPTION_KEY_ENV} must be a urlsafe base64-encoded 32-byte key."
            ) from error
    if DEPLOYMENT_ENVIRONMENT in {"production", "staging"}:
        raise SecurityConfigurationError(
            f"{FIELD_ENCRYPTION_KEY_ENV} must be supplied by an approved KMS or secret manager."
        )
    # This local fallback is intentionally unavailable in production/staging.
    # The key file is mode 0600 and must be excluded from source control; it is
    # still not a substitute for a managed KMS or a hardened host.
    key_path = LOCAL_DEVELOPMENT_KEY_PATH
    try:
        with open(key_path, "rb") as key_file:
            encoded = key_file.read().strip()
    except FileNotFoundError:
        encoded = Fernet.generate_key()
        try:
            descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(encoded + b"\n")
        except FileExistsError:
            with open(key_path, "rb") as key_file:
                encoded = key_file.read().strip()
    try:
        decoded = base64.urlsafe_b64decode(encoded)
        if len(decoded) != 32:
            raise ValueError
        return decoded
    except Exception as error:
        raise SecurityConfigurationError("The local development field-encryption key is invalid.") from error


def _derived_fernet(context: str) -> Fernet:
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"nhaa-field-encryption-v1", info=context.encode("utf-8")
    ).derive(_root_key())
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_text(value: str | None, *, context: str) -> str | None:
    """Encrypt a sensitive field with an independent context-derived key."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Only text fields can be encrypted by this helper.")
    token = _derived_fernet(context).encrypt(value.encode("utf-8")).decode("ascii")
    return f"enc:{FIELD_ENCRYPTION_KEY_VERSION}:{token}"


def decrypt_text(value: str | None, *, context: str) -> str | None:
    """Decrypt a field only after an authorisation decision has been made."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.startswith("enc:"):
        return value
    try:
        _marker, _version, token = value.split(":", 2)
        return _derived_fernet(context).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        raise AccessDenied("Restricted content cannot be decrypted with the active authorised key.")


def encrypt_json(value, *, context: str) -> str:
    return encrypt_text(json.dumps(value, sort_keys=True, separators=(",", ":")), context=context)


def decrypt_json(value: str | None, *, context: str, fallback=None):
    decrypted = decrypt_text(value, context=context)
    if decrypted is None:
        return fallback
    try:
        return json.loads(decrypted)
    except (json.JSONDecodeError, TypeError):
        return fallback


def make_opaque_id(prefix="CASE") -> str:
    """Generate a non-meaningful internal identifier; do not encode identity data."""
    return f"{prefix}-{uuid.uuid4()}"


@dataclass(frozen=True)
class AccessContext:
    """Verified server-side user claims passed to every protected operation."""

    user_id: str
    role: str
    state: str | None = None
    district: str | None = None
    purposes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self):
        if self.role not in ROLE_NAMES:
            raise ValueError("Unsupported application role.")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("An opaque authenticated user ID is required.")
        if self.role in {"counsellor", "district_officer"} and not (self.state and self.district):
            raise ValueError("Counsellor and district-officer access requires a State and district scope.")
        if self.role == "state_administrator" and not self.state:
            raise ValueError("State-administrator access requires a State scope.")


CASE_PURPOSES = frozenset({"case_review", "crisis_review", "consent_management", "safe_contact", "screening"})
RAW_CONTENT_PURPOSES = frozenset({"case_review", "crisis_review", "consent_management"})
AGGREGATE_PURPOSES = frozenset({"service_coordination", "authorised_reporting"})
AUDIT_PURPOSES = frozenset({"audit", "security_investigation"})


def _require_purpose(actor: AccessContext, allowed: Iterable[str], purpose: str):
    if not purpose or purpose not in set(allowed) or purpose not in actor.purposes:
        raise AccessDenied("The requested purpose is not authorised for this operation.")


def require_case_access(actor: AccessContext, case: dict, *, purpose: str, write=False, raw_content=False):
    """Limit individual case access to role, district, and an allowed purpose."""
    _require_purpose(actor, RAW_CONTENT_PURPOSES if raw_content else CASE_PURPOSES, purpose)
    if actor.role not in {"counsellor", "district_officer"}:
        raise AccessDenied("This role is limited to de-identified aggregate data or audit records.")
    if actor.state != case.get("state") or actor.district != case.get("district"):
        raise AccessDenied("The requested case is outside the user's district scope.")
    return True


def require_aggregate_access(actor: AccessContext, *, purpose: str, state=None, district=None):
    """Permit state/national/district roles to see aggregate, de-identified data only.

    - ``national_administrator``: unrestricted national aggregate access.
    - ``state_administrator``: aggregate access within their own state only.
    - ``district_officer``: aggregate access within their own district only.
      Pass ``state`` and ``district`` to scope the check; the officer's own
      ``actor.state`` and ``actor.district`` must match exactly.
    """
    _require_purpose(actor, AGGREGATE_PURPOSES, purpose)
    if actor.role == "national_administrator":
        return True
    if actor.role == "state_administrator" and state is not None and state == actor.state:
        return True
    if actor.role == "district_officer" and district is not None:
        if state == actor.state and district == actor.district:
            return True
        raise AccessDenied(
            "A district officer may only view aggregate data for their own district."
        )
    raise AccessDenied("This role is not authorised for the requested aggregate scope.")


def require_audit_access(actor: AccessContext, *, purpose: str):
    _require_purpose(actor, AUDIT_PURPOSES, purpose)
    if actor.role not in {"auditor", "national_administrator"}:
        raise AccessDenied("Only an auditor or national administrator may view security audit records.")
    return True


def require_export_access(actor: AccessContext, *, purpose: str, export_kind: str):
    if export_kind == "audit":
        return require_audit_access(actor, purpose=purpose)
    # Pass the actor's own state so state_administrator is scoped to their state only.
    require_aggregate_access(actor, purpose=purpose, state=actor.state, district=actor.district)
    if export_kind != "aggregate":
        raise AccessDenied("Individual case, transcript, and audio exports are disabled by this application boundary.")
    return True


def validate_production_transport():
    """Fail closed if production has not configured TLS-backed managed storage."""
    if DEPLOYMENT_ENVIRONMENT not in {"production", "staging"}:
        return
    if STORAGE_BACKEND != PRODUCTION_STORAGE_BACKEND:
        raise SecurityConfigurationError(
            "Production/staging requires the managed encrypted PostgreSQL storage backend; local SQLite is development-only."
        )
    if not DATABASE_URL or not DATABASE_URL.startswith("postgresql") or "sslmode=verify-full" not in DATABASE_URL:
        raise SecurityConfigurationError("Production database connections require PostgreSQL TLS with sslmode=verify-full.")
    _root_key()


def _audit_connection():
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_audit_store():
    conn = _audit_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS security_audit_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                case_id TEXT,
                purpose TEXT,
                result TEXT NOT NULL CHECK (result IN ('ALLOWED', 'DENIED', 'SYSTEM')),
                details_ciphertext TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TRIGGER IF NOT EXISTS prevent_security_audit_update
            BEFORE UPDATE ON security_audit_events BEGIN
                SELECT RAISE(ABORT, 'security audit events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS prevent_security_audit_delete
            BEFORE DELETE ON security_audit_events BEGIN
                SELECT RAISE(ABORT, 'security audit events are immutable');
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def _audit_hmac(payload: str) -> str:
    key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=b"nhaa-audit-chain-v1", info=b"security-audit"
    ).derive(_root_key())
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def append_security_audit(
    *, actor_id: str, action: str, resource_type: str, resource_id: str,
    case_id=None, purpose=None, result="SYSTEM", details=None,
):
    """Append a hash-chained, encrypted-detail security audit event."""
    init_audit_store()
    occurred_at = datetime.now().isoformat()
    conn = _audit_connection()
    try:
        previous = conn.execute(
            "SELECT event_hash FROM security_audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "GENESIS"
        details_ciphertext = encrypt_json(details or {}, context="security-audit-details")
        payload = "|".join(
            [occurred_at, actor_id or "system", action, resource_type, str(resource_id), str(case_id or ""),
             str(purpose or ""), result, details_ciphertext, previous_hash]
        )
        event_hash = _audit_hmac(payload)
        cursor = conn.execute(
            """INSERT INTO security_audit_events
               (occurred_at, actor_id, action, resource_type, resource_id, case_id, purpose, result,
                details_ciphertext, previous_hash, event_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (occurred_at, actor_id or "system", action, resource_type, str(resource_id), case_id,
             purpose, result, details_ciphertext, previous_hash, event_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def verify_audit_chain() -> bool:
    """Validate every retained audit record and its predecessor hash link."""
    init_audit_store()
    conn = _audit_connection()
    try:
        rows = conn.execute("SELECT * FROM security_audit_events ORDER BY sequence ASC").fetchall()
    finally:
        conn.close()
    previous_hash = "GENESIS"
    for row in rows:
        payload = "|".join(
            [row["occurred_at"], row["actor_id"], row["action"], row["resource_type"], row["resource_id"],
             str(row["case_id"] or ""), str(row["purpose"] or ""), row["result"], row["details_ciphertext"], previous_hash]
        )
        if not hmac.compare_digest(row["event_hash"], _audit_hmac(payload)):
            return False
        previous_hash = row["event_hash"]
    return True


def get_security_audit_events(actor: AccessContext, *, purpose: str, limit=200):
    require_audit_access(actor, purpose=purpose)
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_AUDIT_LOG", resource_type="security_audit", resource_id="query",
        purpose=purpose, result="ALLOWED", details={"limit": int(limit)},
    )
    conn = _audit_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM security_audit_events ORDER BY sequence DESC LIMIT ?", (max(1, min(1000, int(limit))),)
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "sequence": row["sequence"], "occurred_at": row["occurred_at"], "actor_id": row["actor_id"],
            "action": row["action"], "resource_type": row["resource_type"], "resource_id": row["resource_id"],
            "case_id": row["case_id"], "purpose": row["purpose"], "result": row["result"],
            "details": decrypt_json(row["details_ciphertext"], context="security-audit-details", fallback={}),
            "event_hash": row["event_hash"],
        }
        for row in rows
    ]


def _identity_connection():
    conn = sqlite3.connect(IDENTITY_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_identity_store():
    conn = _identity_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS identity_contact_vault (
                internal_subject_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL UNIQUE,
                encrypted_name TEXT,
                encrypted_phone TEXT,
                encrypted_alternate_contact TEXT,
                encrypted_contact_preferences TEXT,
                key_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def store_identity_contact(case_id: str, *, full_name=None, phone=None, alternate_contact=None, contact_preferences=None):
    """Store identity/contact data only in the dedicated encrypted vault."""
    init_identity_store()
    now = datetime.now().isoformat()
    conn = _identity_connection()
    try:
        existing = conn.execute(
            "SELECT internal_subject_id FROM identity_contact_vault WHERE case_id = ?", (case_id,)
        ).fetchone()
        subject_id = existing["internal_subject_id"] if existing else make_opaque_id("SUBJECT")
        conn.execute(
            """INSERT INTO identity_contact_vault (
                internal_subject_id, case_id, encrypted_name, encrypted_phone, encrypted_alternate_contact,
                encrypted_contact_preferences, key_version, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(case_id) DO UPDATE SET
                encrypted_name=excluded.encrypted_name, encrypted_phone=excluded.encrypted_phone,
                encrypted_alternate_contact=excluded.encrypted_alternate_contact,
                encrypted_contact_preferences=excluded.encrypted_contact_preferences,
                key_version=excluded.key_version, updated_at=excluded.updated_at, deleted_at=NULL""",
            (
                subject_id, case_id,
                encrypt_text(full_name, context=f"identity:{case_id}:name"),
                encrypt_text(phone, context=f"identity:{case_id}:phone"),
                encrypt_text(alternate_contact, context=f"identity:{case_id}:alternate"),
                encrypt_json(contact_preferences or {}, context=f"identity:{case_id}:preferences"),
                FIELD_ENCRYPTION_KEY_VERSION, now, now,
            ),
        )
        conn.commit()
        return subject_id
    finally:
        conn.close()


def read_identity_contact(actor: AccessContext, case: dict, *, purpose: str):
    """Decrypt identity fields only for an in-scope counsellor/district officer."""
    try:
        require_case_access(actor, case, purpose=purpose, raw_content=True)
    except AccessDenied:
        append_security_audit(
            actor_id=actor.user_id, action="VIEW_IDENTITY_CONTACT", resource_type="identity_contact",
            resource_id=case.get("case_id", "unknown"), case_id=case.get("case_id"), purpose=purpose,
            result="DENIED", details={},
        )
        raise
    init_identity_store()
    conn = _identity_connection()
    try:
        row = conn.execute("SELECT * FROM identity_contact_vault WHERE case_id = ? AND deleted_at IS NULL", (case["case_id"],)).fetchone()
    finally:
        conn.close()
    append_security_audit(
        actor_id=actor.user_id, action="VIEW_IDENTITY_CONTACT", resource_type="identity_contact",
        resource_id=case["case_id"], case_id=case["case_id"], purpose=purpose, result="ALLOWED", details={},
    )
    if not row:
        return None
    return {
        "internal_subject_id": row["internal_subject_id"],
        "full_name": decrypt_text(row["encrypted_name"], context=f"identity:{case['case_id']}:name"),
        "phone": decrypt_text(row["encrypted_phone"], context=f"identity:{case['case_id']}:phone"),
        "alternate_contact": decrypt_text(row["encrypted_alternate_contact"], context=f"identity:{case['case_id']}:alternate"),
        "contact_preferences": decrypt_json(row["encrypted_contact_preferences"], context=f"identity:{case['case_id']}:preferences", fallback={}),
    }


def redact_identity_contact(case_id: str):
    """Cryptographically erase the encrypted identity/contact fields for deletion workflows."""
    init_identity_store()
    conn = _identity_connection()
    try:
        conn.execute(
            """UPDATE identity_contact_vault SET encrypted_name=NULL, encrypted_phone=NULL,
               encrypted_alternate_contact=NULL, encrypted_contact_preferences=NULL, deleted_at=?, updated_at=?
               WHERE case_id=?""",
            (datetime.now().isoformat(), datetime.now().isoformat(), case_id),
        )
        conn.commit()
    finally:
        conn.close()
