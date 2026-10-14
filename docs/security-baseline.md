# Security Baseline

This is the minimum baseline for implementation; it is not a security certification or a production-readiness claim.

## Configuration and secrets
- Commit only safe placeholders in `.env.example`; never commit real credentials.
- Validate required settings at startup and fail clearly if missing.
- Set a unique `AUTH_SECRET_KEY` of at least 32 characters using a secret manager or deployment secret facility in production.
- Never use the development signing-key placeholder in production.
- Do not log passwords, access tokens, session cookies, flag values, or secret configuration.

## Identity and authorization
- Passwords are hashed with Argon2; plaintext passwords are never persisted.
- Public registration assigns the `participant` role on the server and does not accept client-controlled roles or active status.
- Access tokens are short-lived, signed, issuer-checked, and contain no role claims. Current role and active status are resolved from the database for every authenticated request.
- Use generic login errors and deny inactive accounts.
- Enforce authorization on every protected endpoint server-side; hiding UI controls is not authorization.
- Use deny-by-default permissions and least-privilege service credentials.
- Rate-limit registration and token issuance before public launch. Rate limiting is not yet implemented.
- Email verification, password reset, MFA, refresh-token rotation/revocation, and account recovery are not yet implemented.

## API and input handling
- Validate request bodies, query parameters, uploaded files, and identifiers at trust boundaries.
- Return generic error responses without stack traces or internal details in production.

## Uploads and object storage
- Allowlist image formats and verify file signatures rather than trusting extensions or MIME headers.
- Enforce a small explicit size limit for branding images.
- Generate object keys on the server; never use user filenames as storage paths.
- Keep storage private by default and publish only intended assets.
- Prevent SVG or other active-content uploads unless there is a deliberate sanitization and serving policy.

## Auditability
- Audit security-sensitive changes to platform settings, roles, competition configuration, and challenge lifecycle.
- Record actor, action, target, timestamp, and request correlation ID where available.
- Never include uploaded file contents or secrets in audit records. Persistent audit events are not implemented yet.

## CTF sandbox safety
- Treat challenge images, files, and runtime behavior as untrusted.
- Keep challenge execution outside the API process and isolate it with network policies, resource limits, and lifecycle cleanup.
- Never mount host Docker sockets into participant-controlled workloads.
- Do not expose management APIs or internal metadata services to challenge containers.

## Delivery requirements
- Add tests for authorization boundaries and malformed inputs as features are implemented.
- Add dependency scanning, linting, formatting, and tests to CI.
- Threat-model public-facing features and review deployment-specific controls before public launch.
