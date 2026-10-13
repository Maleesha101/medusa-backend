# MEDUSA Backend

The backend platform for **MEDUSA** — a modular, security-first CTF and competition management system.

## Project status

The repository is being bootstrapped. The first implementation phase establishes the application foundation, local development environment, configuration conventions, and API contracts before competition features are added.

## Architecture direction

MEDUSA uses a **modular monolith** initially. Domain boundaries are explicit, but the system is deployed as one API application until operational evidence justifies extracting services.

- **API:** FastAPI, Python, versioned REST API under `/api/v1`
- **Persistence:** PostgreSQL with SQLAlchemy and Alembic migrations
- **Cache and async jobs:** Redis and a worker process
- **Realtime:** WebSockets for live competition and scoreboard updates
- **Object storage:** S3-compatible storage for uploaded assets and challenge artifacts
- **Deployment:** Docker-based local development, with production hardening added in later phases

## Planned domain modules

- Platform settings and branding
- Identity, authentication, authorization, and audit events
- Organizations, universities, users, teams, and memberships
- Competitions, rounds, challenges, submissions, and scoring
- Challenge instances and sandbox lifecycle
- Scoreboard and realtime events
- Security operations / SOC capabilities
- Background jobs, notifications, and integrations

Each module should own its routes, schemas, services, persistence models, and tests where appropriate. Cross-module communication should use explicit service interfaces rather than importing another module's internals.

## Delivery phases

1. **Foundation:** repository conventions, configuration, health endpoints, local dependencies, CI, and architecture documentation.
2. **Identity and competition core:** users, roles, organizations, teams, competitions, rounds, and audit logging.
3. **CTF engine:** challenges, submissions, flag validation, scoring, and scoreboard.
4. **Infrastructure integration:** ephemeral challenge instances, sandbox controller, resource limits, and isolation.
5. **Realtime and SOC:** WebSocket events, alerts, operational visibility, and integrations.
6. **Hardening and scale:** threat modeling, rate limits, load testing, observability, backups, and deployment security.

## Security principles

- Deny access by default and enforce authorization on the server.
- Validate inputs at trust boundaries.
- Keep secrets out of source control and logs.
- Record security-sensitive administrative actions in an audit trail.
- Treat challenge containers and uploaded files as untrusted.
- Apply least privilege, network isolation, resource quotas, and explicit lifecycle controls.
- Never expose internal infrastructure controls directly to participant-facing clients.

## Local development

The exact setup commands and environment variables will be documented as the foundation scaffold is added. Never commit real credentials; use `.env.example` as the safe template.

## Engineering workflow

- Use feature branches and focused pull requests.
- Keep changes small enough to review and test.
- Add tests alongside behavior.
- Update API and architecture documentation when contracts or module boundaries change.
- Do not claim production readiness until security, reliability, and deployment checks have been completed.
