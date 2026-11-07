# MEDUSA Backend

The backend platform for **MEDUSA** — a modular, security-first CTF and competition management system.

## Project status

The repository contains the application foundation, identity/authentication, organization/team membership APIs, competition/round management, challenge authoring/catalog, challenge submission and flag validation, and initial scoring and public scoreboard endpoints. It is not yet production-ready. Persistent audit events, distributed submission rate limiting, and Redis-backed scoreboard update notifications are implemented. Sandbox infrastructure work is in progress: this phase introduces lifecycle metadata and a fail-closed provider boundary, not participant-facing sandbox APIs or a runnable container provider.

## Architecture direction

MEDUSA uses a **modular monolith** initially. Domain boundaries are explicit, but the application is deployed as one API until operational evidence justifies extracting services.

- **API:** FastAPI, Python, versioned REST API under /api/v1
- **Persistence:** PostgreSQL with SQLAlchemy and Alembic migrations
- **Cache and async jobs:** Redis and a worker process
- **Realtime:** WebSockets for live competition and scoreboard updates
- **Object storage:** S3-compatible storage for uploaded assets and challenge artifacts
- **Deployment:** Docker-based local development; DigitalOcean VPS selected as the planned hosting provider (see [DigitalOcean deployment readiness](docs/digitalocean-vps-deployment.md))

## Implemented endpoints

- GET /api/v1/live and GET /api/v1/ready — health probes
- GET /api/v1/admin/operations/metrics and GET /api/v1/admin/operations/alerts — administrator operational metrics and persisted alert state
- POST /api/v1/auth/register, POST /api/v1/auth/token, GET /api/v1/auth/me, POST /api/v1/auth/logout, POST /api/v1/auth/password-reset/request, POST /api/v1/auth/password-reset/confirm — identity, authentication, logout, and password recovery
- GET/POST /api/v1/organizations — list and create organizations
- GET /api/v1/organizations/{organization_id} — get an organization
- GET/POST /api/v1/organizations/{organization_id}/teams — list and create teams
- GET /api/v1/teams/{team_id} — team details and members
- POST /api/v1/teams/{team_id}/join and DELETE /api/v1/teams/{team_id}/leave — membership operations
- GET/POST /api/v1/competitions — list public competitions and create a draft competition
- POST /api/v1/competitions/{competition_id}/registrations — register an eligible team during the registration window (optional competition `max_teams` capacity)
- GET /api/v1/competitions/{competition_id}/registrations — private paginated registration roster (authorized organizer/admin)
- DELETE /api/v1/competitions/{competition_id}/registrations/{team_id} — withdraw a team's registration (captain, before activation)
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
- WS /api/v1/competitions/{competition_id}/scoreboard/ws — receive public scoreboard invalidation events over WebSocket

Organization and competition creation and lifecycle changes require an organizer or admin role. Public registration always creates a participant; assign organizer/admin roles through a controlled administrative process. Team creators become captains. Authentication endpoints use Redis-backed fixed-window limits: registration defaults to 5 requests per IP per 10 minutes, while token issuance defaults to 20 requests per IP and 5 per normalized account per 60 seconds. Configure these with REGISTRATION_REQUEST_LIMIT, REGISTRATION_RATE_WINDOW_SECONDS, TOKEN_REQUEST_LIMIT_PER_IP, TOKEN_REQUEST_LIMIT_PER_ACCOUNT, and TOKEN_RATE_WINDOW_SECONDS. Over-limit requests return HTTP 429 with Retry-After; Redis failures fail closed with HTTP 503. Submission requests use Redis-backed fixed-window limits: 60 requests per user and 10 incorrect attempts per team/challenge per 60 seconds by default. Configure these with SUBMISSION_REQUEST_LIMIT, INCORRECT_SUBMISSION_LIMIT, and SUBMISSION_RATE_WINDOW_SECONDS. Exceeding a limit returns HTTP 429 with Retry-After; if Redis is unavailable, submission protection fails closed with HTTP 503. Challenge flags are stored as keyed digests using the configured authentication secret; changing that secret requires reconfiguring challenge flags. Submission records store the user, team, challenge, correctness, and timestamp, but not the submitted flag. A team may solve each challenge only once. A team must belong to the competition's organization, and the submitting user must be a member of that team. Submissions are accepted only while the competition is active. See docs/api-contract.md and docs/security-baseline.md for access rules and limitations.

## Local development

1. Copy .env.example to .env and keep the values local.
2. Start services and build the API:

   ```bash
   docker compose up --build -d
   ```

   The local stack includes Mailpit for password-reset email testing. Open its inbox at http://localhost:8025. The API sends mail to the `mailpit` Compose service on port `1025`; no SMTP account or credentials are needed. Mailpit's SMTP and web ports are bound to `127.0.0.1` only and must not be exposed publicly.

3. Apply database migrations:

   ```bash
   docker compose exec api alembic upgrade head
   ```

4. Open the interactive API documentation at http://localhost:8000/docs.

The local Compose API allows the Vite development origin `http://localhost:8080` by default. For another frontend origin, set `CORS_ORIGINS` to a JSON array of exact origins (scheme, host, and port; no path or trailing slash), for example `CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080"]`. Restart the API after changing it. Wildcard origins are rejected by configuration.

If `GET /api/v1/live` succeeds but `GET /api/v1/ready` returns HTTP 503, the API process is running but its database readiness query failed. Check `docker compose ps` and `docker compose logs --tail=100 postgres api`, confirm the API's `DATABASE_URL` points to the reachable PostgreSQL service (use hostname `postgres` from inside Compose, not `localhost`), and verify PostgreSQL is healthy. Readiness uses `SELECT 1`; database migrations are not the cause of this particular probe failure.
5. Use requests/medusa-submissions.http for a local end-to-end flag submission walkthrough. Run its named requests in order and replace example credentials/IDs as needed.

Local Docker Compose configures the API to use Mailpit automatically (`SMTP_HOST=mailpit`, `SMTP_PORT=1025`, no TLS or credentials). After starting the stack, request a password reset from the frontend and inspect the captured message at http://localhost:8025; the email's link should point to the frontend's `/reset-password` route. For deployments outside local development, configure a real SMTP provider with `SMTP_HOST`, `SMTP_FROM_EMAIL`, and, when required, `SMTP_USERNAME` and `SMTP_PASSWORD`. Production startup requires `SMTP_HOST` and `SMTP_FROM_EMAIL`. If SMTP is absent or delivery fails, the reset API keeps its generic response and does not expose account existence, reset tokens, or internal delivery details. Reset tokens are never returned by the API. The Compose database password and signing key are development-only values. Replace both through deployment secrets before any non-local deployment. Do not commit .env or real credentials.

## Building and checking the API container

Build the runtime image locally:

```bash
docker build -t medusa-backend:local .
```

The image runs Uvicorn as the unprivileged `medusa` user and includes a Docker health check against `/api/v1/ready`. The readiness endpoint requires the database to accept a lightweight query, so run the image with a reachable configured database and Redis service.

For a local Compose smoke test:

```bash
docker compose up --build -d
docker compose ps
docker inspect --format='{{json .State.Health}}' medusa-api
docker compose logs --tail=100 api
```

The health state becomes healthy only after the API can reach its database. Stop the local stack with `docker compose down`; add `-v` only when intentionally deleting local database data.

## Production Compose deployment

The separate `compose.production.yaml` profile keeps PostgreSQL and Redis off published host ports and binds the API to loopback for a separately managed TLS reverse proxy. It requires production secrets and SMTP settings and applies additional hardening to the API container. It does not configure TLS, host firewall rules, off-host backup storage, or sandbox isolation.

Follow [the production Compose deployment guide](docs/production-compose-deployment.md). Validate the rendered profile before starting it:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
# Edit .env.production with unique production secrets and real SMTP/frontend settings.
docker compose --env-file .env.production -f compose.production.yaml config --quiet
python scripts/validate_production_compose.py
docker compose --env-file .env.production -f compose.production.yaml up --build -d
```

Never commit `.env.production`. Keep `SANDBOX_PROVIDER=unavailable`; this profile is for the trusted application/control plane only.

Create a verified PostgreSQL backup to a private destination outside the repository and Docker data directories with `python scripts/backup_production_postgres.py --env-file .env.production --backup-dir /absolute/private/backup/path --retention-days 30`. See the [backup and restore guide](docs/production-compose-deployment.md#backup-and-restore) before scheduling backups or performing a restore drill.

GitHub Actions builds the Docker image for pull requests and pushes to main without publishing it or requiring registry credentials. CI also validates the production Compose security-sensitive defaults. This validates configuration and image construction, not a production deployment or sandbox isolation.

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
5. **CTF engine:** challenge authoring/catalog, flag submission/validation, immutable solve-time point awards, public scoreboards, persistent audit events, and Redis-backed submission rate limits are implemented.
6. **Infrastructure integration:** in progress. Sandbox lifecycle metadata and a fail-closed controller contract are being introduced before any runtime provider or participant-facing API is enabled.
7. **Realtime and SOC:** public scoreboard WebSocket notifications and persisted operational alert notifications are implemented; broader integrations remain future work.
8. **Hardening and scale:** threat modeling, registration/token rate limits, load testing, observability, backups, and deployment security.

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
