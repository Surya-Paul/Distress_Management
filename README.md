# NHAA Survivor Support Triage Prototype

This is a trauma-informed, **non-diagnostic** decision-support prototype for
organising consented interaction information for trained human review. It is not
a mental-health diagnosis tool, clinical instrument, credibility assessment,
crisis-response service, or automated case-management system.

## Privacy architecture and deployment boundary

The application now separates three storage domains:

- **Case/wellbeing store:** opaque internal case IDs, workflow records,
  consented assessments, and de-identified aggregate data.
- **Identity/contact vault:** a separate database holding encrypted names,
  phone numbers, alternate contacts, and contact preferences. These fields are
  not columns in the case/wellbeing store and never appear in dashboards.
- **Security-audit store:** immutable, hash-chained audit records with encrypted
  details, separate from the operational data store.

Restricted transcripts are field-encrypted and excluded from ordinary query
results. Only an in-scope counsellor or district officer with an allowed,
audited purpose can request decryption. Raw audio is not retained by this
prototype. Identity/contact fields are separately field-encrypted in the vault.

Local SQLite is now an isolated **development/test** mode, not a production
database deployment. Production or staging starts fail closed unless configured
with a managed backend, PostgreSQL TLS (`sslmode=verify-full`), a KMS/secret
manager supplied `NHAA_FIELD_ENCRYPTION_KEY`, and verified server-side user
claims. The local development fallback key is generated with owner-only file
permissions and is ignored by version control; it is not appropriate for a
production host.

For production/staging, set `NHAA_STORAGE_BACKEND=managed_encrypted_postgres`
and point `NHAA_DATABASE_URL` at a managed service configured for encryption at
rest and certificate-verified TLS. The current repository intentionally fails
closed rather than silently using SQLite in those environments; connecting this
application boundary to the managed PostgreSQL service is an infrastructure
deployment task.

### Roles and access scope

| Role | Access |
| --- | --- |
| Counsellor | In-district individual cases and restricted content only for an authorised purpose. |
| District officer | In-district individual cases and restricted content only for an authorised purpose. |
| State administrator | State-scoped, de-identified aggregate coordination data and authorised configuration. |
| National administrator | National de-identified aggregate data and authorised governance operations. |
| Auditor | Security-audit records and hash-chain verification only. |

Dashboards are restricted to State/national roles, return no direct identifiers
or source content, and suppress aggregate cells below the configured minimum.
Individual case, transcript, and audio exports are blocked. Viewing, exporting,
creating, assigning, acknowledging, changing, closing, consent changes, and
deletion operations are security-audited.

### Consent, retention, and deletion

The consent ledger records purpose, channel, language, timestamp, version,
withdrawal, and encrypted contact preferences. Retention policies are versioned
and auditable. Deletion uses a two-person workflow: an in-scope caseworker
requests it, an authorised State/national administrator other than the requester
approves it, and a separately audited execution cryptographically erases
identity/contact and restricted source-content fields while preserving minimal
audit facts.

## What it does

- Records consented, minimally necessary interaction notes against an opaque case ID.
- Organises reported information into three independent dimensions: physical
  safety, emotional wellbeing, and service access.
- Produces a **Support Priority Indicator (SPI), 0–100** to help sort the
  timeliness of human review.
- Shows short evidence excerpts, extraction confidence, and data-quality limits.
- Creates review tasks for trained staff. A task never contacts a survivor,
  changes a record, or starts a referral automatically.
- Requires a named human reviewer and review notes before a task is completed.

## Two separate score types

The prototype keeps validated questionnaire response totals separate from the
non-diagnostic SPI. Neither is a diagnosis or an authority for an automatic
action.

- **Optional PHQ-9 or GAD-7 administration:** The **Validated Questionnaire**
  page uses only the application's exact, versioned question set. It requires
  recorded questionnaire-specific consent, permits every item to be skipped,
  and calculates a PHQ-9 `0–27` or GAD-7 `0–21` total only when every item is
  answered. A skipped item stores an incomplete record with no imputation or
  total. A direct response to PHQ-9 item nine creates only a human-review task;
  it does not establish intent or trigger outreach.
- **Support Priority Indicator:** SPI uses only explicit, evidence-linked
  support signals, reported threats, unmet service needs, a quality-checked
  recent change, and unanswered *agreed planned* follow-ups. Questionnaire
  totals are never SPI features.

SPI thresholds, floors, feature weights, and material-change rules are
configurable as named versions in **Crisis Configuration → SPI threshold
versions**. A new version preserves the old version and is audited. Each SPI
record stores its score version, threshold version, model/extraction version,
feature set, confidence, evidence references, trend-quality flags, and any
documented human reviewer override. An override never changes the calculated
SPI.

## Trend interpretation

The timeline will describe a change as worsening, improving, or stable only if
the two scores are comparable. It instead reports **not comparable** when a
score is missing, extraction confidence is low, collection channel changes,
analysis language changes, or the score version changes. This avoids presenting
missingness or a collection-method change as a change in the person's state.

## Optional experimental audio metadata

Audio transcription requires specific consent. Experimental descriptive voice
analysis is **disabled by default** and needs a separate, explicit opt-in and
consent. It may be inaccurate because recording quality, language, device,
transcription, and model limitations can materially affect results.

- The app makes no claim that pitch, jitter, shimmer, pauses, speech rate, or
  any other descriptor establishes anxiety, deception, instability,
  depression, intent, or danger.
- Audio metadata is non-diagnostic and cannot be a sole input to an alert,
  crisis event, or SPI calculation.
- Each audio-derived interaction stores the opt-in and consent state, recording
  quality, language, device limitations, model uncertainty, experimental
  status, and raw-audio retention status.
- This prototype does **not** retain raw audio. It uses the upload for
  transcription (and, if opted in, temporary experimental processing) then
  discards its temporary raw-audio copy. Any retention must occur in a separate
  authorised records system under its approved retention policy.

## Crisis workflow

Explicit reported self-harm/suicide statements and explicit external safety
threats create separate crisis-event records. Each event snapshots the evidence,
confidence, limitations, case context, and stated contact preferences; then it
creates an append-only audit record and an internal queue escalation.

- The acknowledgement SLA and default accountable counsellor or district safety
  officer are configurable in **Crisis Configuration**.
- The only automatic channel is an internal, access-controlled case queue. The
  prototype does not send SMS, initiate calls, contact third parties, or make
  referrals automatically.
- A safe-contact attempt can be logged only after acknowledgement, under a
  recorded consent protocol, through an approved secure channel, with a maximum
  of one to three attempts and configured retry spacing.
- Closing an event requires the assigned reviewer to record action taken,
  outcome, follow-up date, and closure rationale.
- The local service directory keeps emergency, counselling, protection, medical,
  and legal-aid entries unverified until an authorised staff member verifies
  them. No emergency number is hard-coded.

## Strict extraction contract

`src/groq_client.py` defines `SUPPORT_SIGNAL_SCHEMA` and validates every model
response before it reaches the application. The contract separates explicit
self-harm/suicide statements, physical-safety concerns, strongly expressed
wellbeing concerns, service-access barriers, and stated contact preferences.

- Evidence must be an exact source span of 20 words or fewer.
- Each signal carries low, medium, or high confidence.
- Absent or ambiguous information must be `insufficient_information`.
- Unsupported fields, string booleans, missing or mismatched evidence,
  unsupported levels, and unjustified high-confidence signals are rejected.
- Rejected or unavailable model output fails closed to an
  `insufficient_information` record for human source-note review.

## Known Limitations

This table clarifies what is scoped out of this hackathon prototype (shortcuts) versus what reflects genuine safety/architecture claims (design decisions). Judges evaluating the demo should note these bounds.

| Feature / Area | Status in this Prototype | Shortcut or Design Decision? |
| :--- | :--- | :--- |
| **Telephony/IVRS** | **Scoped out.** Uses text/audio file uploads instead of real phone integration. | **Shortcut.** A real deployment requires secure telephony/IVRS integration. |
| **Authentication** | **Mocked.** UI dropdowns simulate roles, districts, and identities. | **Shortcut.** A real deployment requires verified OIDC/SAML authentication. |
| **Language Support** | **Limited.** Only Hindi and English extraction are verified in the demo. | **Shortcut.** Full deployment needs clinically reviewed prompts for all regional languages. |
| **Database** | **SQLite.** Runs as an isolated local file database. | **Shortcut.** Production must use `managed_encrypted_postgres` with KMS. |
| **Automatic Action** | **None.** The system cannot send SMS, call police, or refer cases on its own. | **Design Decision.** Coercive or irreversible automated actions are unsafe. |
| **Audio Storage** | **Discarded.** Audio is transcribed and then the local copy is deleted. | **Design Decision.** Raw audio creates extreme privacy risks and should not be stored here. |
| **Signal Extraction** | **Constrained Schema.** Only explicit statements are extracted and mapped to SPI. | **Design Decision.** Prevents LLM hallucinations and prevents the system from making clinical diagnoses. |

## Important limits

- An SPI is not a diagnosis, a measure of symptom severity, a prediction of
  harm, or evidence that a report is true or false.
- The app does not infer depression, PTSD, suicidality, intent, or truthfulness.
  It can only flag explicit reported statements for human review.
- Voice characteristics are not used for prioritisation. If retained for future
  research, they need separate consent, validation, and governance.
- “No review task” does not mean a person is safe or does not need support.
- This SQLite prototype does not provide production authentication, encryption,
  access controls, retention management, or legal compliance by itself.

## Human-review rule

Before any outreach, referral, protection measure, medical support, change to a
legal or compensation record, or other action affecting a person, an authorised
human must review the evidence, limitations, consent, and safe-contact
preferences, then record the outcome.

No single SPI or questionnaire total may independently trigger a coercive or
irreversible action. Automated workflow events are reserved for strict,
evidence-linked explicit statements and remain internal review records until a
trained person reviews them.

## Tests

Run the safety-focused unit suite with:

```bash
venv/bin/python -m unittest discover -s tests -v
```

The suite covers questionnaire boundaries and skipping, consent and exact-item
validation, conflicting/unsupported signals, trend comparability, provenance
storage, prevention of a crisis pathway from SPI alone, and prevention of an
alert or crisis event from acoustic metadata alone.

## Run locally

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Set `GROQ_API_KEY` only in a local environment variable or `.env` file. Use
synthetic data until clinical, legal, privacy, security, and survivor-advocate
governance approvals are in place.
