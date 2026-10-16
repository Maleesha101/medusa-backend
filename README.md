# MEDUSA Backend

The backend platform for **MEDUSA** — a modular, security-first CTF and competition management system.

## Project status

The repository contains the application foundation, identity/authentication, organization/team membership APIs, competition/round management, challenge authoring/catalog, challenge submission and flag validation, and initial scoring and public scoreboard endpoints. It is not yet production-ready. Persistent audit events, sandbox APIs, distributed submission rate limiting, and production hardening remain future work.

## Architecture direction

MEDUSA uses a **modular monolith** initially. Domain boundaries are explicit, but the application is deployed as one API until operational evidence justifies extracting services.

- **API:** FastAPI, Python, versioned REST API under /api/v1
- **Persistence:** PostgreSQL with SQLAlchemy and Alembic migrations
- **Cache and async jobs:** Redis and a worker process
- **Realtime:** WebSockets for live competition and scoreboard updates
- **Object storage:** S3-compatible storage for uploaded assets and challenge artifacts
- **Deployment:** Docker-based local development, with production hardening added in later phases

## Implemented endpoints

- GET /api/v1/live and GET /api/v1/ready — health probes
- POST /api/v1/auth/register, POST /api/v1/auth/token, GET /api/v1/auth/me — identity and authentication
- GET/POST /api/v1/organizations — list and create organizations
- GET /api/v1/organizations/{organization_id} — get an organization
- GET/POST /api/v1/organizations/{organization_id}/teams — list and create teams
- GET /api/v1/teams/{team_id} — team details and members
- POST /api/v1/teams/{team_id}/join and DELETE /api/v1/teams/{team_id}/leave — membership operations
- GET/POST /api/v1/competitions — list public competitions and create a draft competition
- GET /api/v1/competitions/{competition_id} — retrieve a public competition
- PATCH /api/v1/competitions/{competition_id}/status — advance competition lifecycle
- GET/POST /api/v1/competitions/{competition_id}/rounds — list and create ordered rounds
- POST /api/v1/rounds/{round_id}/challenges — create a draft challenge
- GET /api/v1/rounds/{round_id}/challenges — list published challenges in a public competition
- GET /api/v1/challenges/{challenge_id} — retrieve a published challenge
- PATCH /api/v1/challenges/{challenge_id} — update challenge metadata
- PATCH /api/v1/challenges/{challenge_id}/status — publish or archive a challenge
- PUT /api/v1/challenges/{challenge_id}/flag — configure a draft challenge's private flag (organizer/admin)
- POST /api/v1/challenges/{challenge_id}/submissions — submit a flag for a team

Organization and competition creation and lifecycle changes require an organizer or admin role. Public registration always creates a participant; assign organizer/admin roles through a controlled administrative process. Team creators become captains. Submission requests use Redis-backed fixed-window limits: 60 requests per user and 10 incorrect attempts per team/challenge per 60 seconds by default. Configure these with SUBMISSION_REQUEST_LIMIT, INCORRECT_SUBMISSION_LIMIT, and SUBMISSION_RATE_WINDOW_SECONDS. Exceeding a limit returns HTTP 429 with Retry-After; if Redis is unavailable, submission protection fails closed with HTTP 503. Challenge flags are stored as keyed digests using the configured authentication secret; changing that secret requires reconfiguring challenge flags. Submission records store the user, team, challenge, correctness, and timestamp, but not the submitted flag. A team may solve each challenge only once. A team must belong to the competition's organization, and the submitting user must be a member of that team. Submissions are accepted only while the competition is active. See docs/api-contract.md and docs/security-baseline.md for access rules and limitations.

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
5. Use requests/medusa-submissions.http for a local end-to-end flag submission walkthrough. Run its named requests in order and replace example credentials/IDs as needed.

The Compose database password and signing key are development-only values. Replace both through deployment secrets before any non-local deployment. Do not commit .env or real credentials.

## Running tests

The production Docker image intentionally installs runtime dependencies only. Install the optional development dependencies in a local virtual environment to run pytest and Ruff:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -v
ruff check .
ruff format --check .
```

## Delivery phases

1. **Foundation:** repository conventions, configuration, health endpoints, local dependencies, CI, and architecture documentation.
2. **Identity foundation:** users, password hashing, access tokens, role checks, and schema migrations.
3. **Organization/team foundation:** organizations, teams, membership, and access control.
4. **Competition/round foundation:** competition metadata, lifecycle transitions, schedules, and ordered rounds.
5. **CTF engine:** challenge authoring/catalog, flag submission/validation, immutable solve-time point awards, and public scoreboards are implemented; persistent audit event logging remains future work.
6. **Infrastructure integration:** ephemeral challenge instances, sandbox controller, resource limits, and isolation.
7. **Realtime and SOC:** WebSocket events, alerts, operational visibility, and integrations.
8. **Hardening and scale:** threat modeling, rate limits, load testing, observability, backups, and deployment security.

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
