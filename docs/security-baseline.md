# Security Baseline

This is the minimum baseline for implementation; it is not a security certification or a production-readiness claim.

## Configuration and secrets
- Commit only safe placeholders in .env.example; never commit real credentials.
- Validate required settings at startup and fail clearly if missing.
- Set a unique AUTH_SECRET_KEY of at least 32 characters using a secret manager or deployment secret facility in production.
- Never use the development signing-key placeholder in production.
- Challenge flags are keyed with AUTH_SECRET_KEY; rotating this key requires resetting configured challenge flags.
- Do not log passwords, access tokens, session cookies, submitted flags, flag digests, or secret configuration.

## Identity and authorization
- Passwords are hashed with Argon2; plaintext passwords are never persisted.
- Public registration assigns the participant role on the server and does not accept client-controlled roles or active status.
- Access tokens are short-lived, signed, issuer-checked, and contain no role claims. Current role and active status are resolved from the database for every authenticated request.
- Use generic login errors and deny inactive accounts.
- Enforce authorization on every protected endpoint server-side; hiding UI controls is not authorization.
- Use deny-by-default permissions and least-privilege service credentials.
- Challenge submissions use shared Redis fixed-window limits: a general per-user request budget and a separate incorrect-attempt budget per team/challenge. Limits are configurable; over-limit responses include Retry-After. Redis failures fail closed with HTTP 503. Registration is limited per direct client IP; token issuance is limited both per direct client IP and per normalized account identifier (hashed before being used in Redis keys). These limits are configurable and include Retry-After. Forwarded IP headers must only be trusted when configured by a trusted reverse proxy. Access-token revocation is implemented for explicit logout using a Redis denylist keyed by a unique token identifier and expiring at the token's natural expiry. Password reset uses hashed, short-lived, single-use tokens; reset requests return a generic response and are rate-limited by IP and normalized email. Successful reset increments the account auth version, invalidating all previously issued access tokens. SMTP must be configured to deliver reset links. Email verification, MFA, and refresh-token rotation are not yet implemented.

## API and input handling
- Validate request bodies, query parameters, uploaded files, and identifiers at trust boundaries.
- Never persist submitted flag values. Persist the attempt result and its actor/team/challenge metadata only.
- Compare flag digests using constant-time comparison and do not expose the expected flag or its digest through API schemas.
- Enforce a database uniqueness invariant for a team's accepted solve of a challenge.
- Return generic error responses without stack traces or internal details in production.

## Uploads and object storage
- Allowlist image formats and verify file signatures rather than trusting extensions or MIME headers.
- Enforce a small explicit size limit for branding images.
- Generate object keys on the server; never use user filenames as storage paths.
- Keep storage private by default and publish only intended assets.
- Prevent SVG or other active-content uploads unless there is a deliberate sanitization and serving policy.

## Auditability
- Audit security-sensitive changes to platform settings, roles, competition configuration, challenge lifecycle, and flag updates.
- Record actor, action, target, timestamp, and request correlation ID where available.
- Never include uploaded file contents or secrets in audit records. Persistent audit events are implemented for challenge submissions, flag configuration, challenge lifecycle changes, and competition status changes.

## CTF sandbox safety
- Treat challenge images, files, and runtime behavior as untrusted.
- Keep challenge execution outside the API process and isolate it with network policies, resource limits, and lifecycle cleanup.
- Never mount host Docker sockets into participant-controlled workloads.
- Do not expose management APIs or internal metadata services to challenge containers.
- The current sandbox-controller implementation is an interface plus a provider-unavailable default that fails closed. It intentionally does not start containers or expose participant-facing lifecycle endpoints. Do not enable arbitrary images or execution until an isolated provider enforces immutable image references, CPU/memory/process limits, network egress policy, timeouts, and cleanup.

## Delivery requirements
- Add tests for authorization boundaries and malformed inputs as features are implemented.
- Add dependency scanning, linting, formatting, and tests to CI.
- Threat-model public-facing features and review deployment-specific controls before public launch.
