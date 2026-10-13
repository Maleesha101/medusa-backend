# MEDUSA Backend

The backend platform for **MEDUSA** — a modular, security-first CTF and competition management system.

## Project status

The repository contains the application foundation and the first identity/authentication slice. It is not yet production-ready. Competition, team, challenge, submission, scoring, audit persistence, and sandbox APIs remain future work.

## Architecture direction

MEDUSA uses a **modular monolith** initially. Domain boundaries are explicit, but the application is deployed as one API until operational evidence justifies extracting services.

- **API:** FastAPI, Python, versioned REST API under /api/v1
- **Persistence:** PostgreSQL with SQLAlchemy and Alembic migrations
- **Cache and async jobs:** Redis and a worker process
- **Realtime:** WebSockets for live competition and scoreboard updates
- **Object storage:** S3-compatible storage for uploaded assets and challenge artifacts
- **Deployment:** Docker-based local development, with production hardening added in later phases

## Implemented endpoints

- GET /api/v1/live — liveness probe
- GET /api/v1/ready — database readiness probe
- POST /api/v1/auth/register — participant registration
- POST /api/v1/auth/token — OAuth2 form-based email/password token issuance (username field contains the email)
- GET /api/v1/auth/me — authenticated user's safe profile

Authentication uses Argon2 password hashing and short-lived signed bearer tokens. Roles are resolved from the database rather than trusted from token claims. See docs/api-contract.md and docs/security-baseline.md.

## Local development

1. Copy .env.example to .env and keep the values local.
2. Start services and build the API:

   ```bash
   docker compose up --build -d
   ```

3. Apply database migrations:

   ```bash
   docker compose exec api alembic upgrade head
   ```

4. Open the interactive API documentation at http://localhost:8000/docs.

The Compose database password and signing key are development-only values. Replace both through deployment secrets before any non-local deployment. Do not commit .env or real credentials.

## Delivery phases

1. **Foundation:** repository conventions, configuration, health endpoints, local dependencies, CI, and architecture documentation.
2. **Identity foundation:** users, password hashing, access tokens, role checks, and schema migrations.
3. **Competition core:** organizations, teams, memberships, competitions, rounds, and audit logging.
4. **CTF engine:** challenges, submissions, flag validation, scoring, and scoreboard.
5. **Infrastructure integration:** ephemeral challenge instances, sandbox controller, resource limits, and isolation.
6. **Realtime and SOC:** WebSocket events, alerts, operational visibility, and integrations.
7. **Hardening and scale:** threat modeling, rate limits, load testing, observability, backups, and deployment security.

## Security principles

- Deny access by default and enforce authorization on the server.
- Validate inputs at trust boundaries.
- Keep secrets out of source control and logs.
- Record security-sensitive administrative actions in an audit trail.
- Treat challenge containers and uploaded files as untrusted.
- Apply least privilege, network isolation, resource quotas, and explicit lifecycle controls.
- Never expose internal infrastructure controls directly to participant-facing clients.
- Do not claim production readiness until security, reliability, and deployment checks have been completed.

## Engineering workflow

- Use feature branches and focused pull requests.
- Keep changes small enough to review and test.
- Add tests alongside behavior.
- Update API and architecture documentation when contracts or module boundaries change.
