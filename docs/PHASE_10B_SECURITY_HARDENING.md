# Phase 10B — Authentication and Security Hardening

## Implemented

### Refresh authentication
- Added a dedicated signed refresh token.
- Refresh token has an explicit `typ=refresh` claim.
- Access tokens and refresh tokens cannot be substituted for one another.
- Refresh tokens use the same account `auth_version` as access tokens.
- Password reset/account revocation can invalidate outstanding refresh tokens by incrementing `auth_version`.
- Refresh cookie is HTTP-only, Secure outside demo mode, SameSite=Strict, and path-scoped to authentication routes.
- Logout clears both access and refresh cookies.

### Rate limiting
- Login attempts are rate limited.
- Refresh requests are independently rate limited.
- Limits are configurable through environment variables.
- Current limiter is process-local.
- Multi-worker/multi-instance deployments require shared state or an API gateway.

### Production configuration
Non-demo configuration now requires:
- non-SQLite database;
- HTTPS frontend origin;
- `AUTH_SECRET` supplied explicitly;
- `AUTH_SECRET` at least 32 characters;
- secure authentication cookie;
- bounded access/refresh cookie lifetimes;
- positive rate-limit settings.

### PII/security review
- Authentication tokens are kept in HTTP-only cookies rather than browser-accessible storage.
- Audit logs no longer record free-text handoff reasons or counsellor notes.
- Raw interview answers are not included in AI observability metrics.
- Raw prompts/reasoning are not persisted by the observability layer.
- Knowledge-document originals may contain source material and therefore remain staff/admin controlled.
- Beneficiary session UUIDs are not equivalent to a production identity/authentication system.

## Verification

Phase 10B adds tests for:
- login issuing access + refresh cookies;
- successful refresh;
- missing refresh cookie;
- access-token-as-refresh-token rejection;
- logout refresh-cookie clearing;
- auth-version refresh-token revocation;
- refresh rate limiting;
- production configuration guardrails.

## Remaining security limitations

- Rate limiting is process-local.
- There is no beneficiary authentication/identity system.
- No SSO/MFA integration.
- No distributed session/token store.
- No independent penetration test.
- No formal production privacy impact assessment.
- No automated retention-policy enforcement.

Passing automated tests does not certify production readiness.
