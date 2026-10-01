# Privacy and safety

- Consent is requested before interview slots are collected.
- No Aadhaar or caste/category is requested or stored.
- Audio is processed in memory and is not persisted by this application. Browser speech recognition remains browser/provider-dependent.
- Session UUIDs are random pseudonymous identifiers; profile data is retained in the local demo database until withdrawal or manual deletion.
- Withdrawal deletes the session, raw interview answers, case, recommendation, handoff and follow-up rows through the API (the audit log keeps a deletion event without retaining the profile).
- Admin aggregates suppress values below five. These small-cell protections are demo-level and require review before deployment.
- Counsellor/admin routes now require role-specific accounts and signed HTTP-only cookies. Staff passwords are stored as salted PBKDF2 hashes; production accounts are managed individually through the CLI. SSO/MFA and a beneficiary identity model are still absent. Do not enter real personal information.
- Local microphone permissions and browser speech services are governed by the browser/OS.

Before any real pilot, perform a privacy impact review, define purpose and retention, secure access and encryption, establish breach response, validate DPDP obligations with counsel, and test consent comprehension in each language.
