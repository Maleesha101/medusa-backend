# Production Compose deployment profile

This profile is for the MEDUSA application/control plane on a dedicated application host. It is separate from the local-development `compose.yaml`; do not replace the local workflow with it.

The profile does not provision a VPS, configure a host firewall or TLS reverse proxy, provide a backup service, or isolate hostile challenge code. Keep `SANDBOX_PROVIDER=unavailable`. The API is bound to host loopback so a separately managed reverse proxy can terminate HTTPS. PostgreSQL and Redis have no published host ports.

## Prerequisites

- A supported Linux host with Docker Engine and the Docker Compose plugin.
- A reviewed host firewall policy and an independently managed TLS reverse proxy.
- A production SMTP service.
- A protected backup destination and a tested restore procedure.

Do not deploy the API and future hostile-code execution workloads into the same trust boundary. This Compose profile is only for trusted MEDUSA application services.

## Configure secrets

Create a private environment file from the template:

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Edit `.env.production` on the host. Do not commit it or paste its contents into issues, logs, or support requests.

Generate independent URL-safe secrets (hex avoids URL-encoding ambiguity in the PostgreSQL and Redis URLs):

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Use separate values for `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `AUTH_SECRET_KEY`. Configure `PASSWORD_RESET_URL` with the real public HTTPS frontend URL and set valid `SMTP_HOST` and `SMTP_FROM_EMAIL` values. SMTP username/password may be left empty only if the SMTP relay does not require authentication.

The Compose file intentionally uses required-value interpolation for production secrets and SMTP settings. It does not fall back to local-development passwords. The PostgreSQL and Redis connection URLs are assembled from the generated hex passwords.

## Validate and start

Run from the repository root:

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
python scripts/validate_production_compose.py
docker compose --env-file .env.production -f compose.production.yaml up --build -d
```

Apply database migrations as a controlled release step:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec api alembic upgrade head
```

Verify service state and readiness:

```bash
docker compose --env-file .env.production -f compose.production.yaml ps
curl -i http://127.0.0.1:8000/api/v1/ready
docker compose --env-file .env.production -f compose.production.yaml logs --tail=100 api
```

The API should return HTTP 200 with `{"status":"ready"}`. The host port is loopback-only; configure the reverse proxy to reach `127.0.0.1:8000`. Do not expose port 8000 directly to the public internet. PostgreSQL and Redis are reachable only on the Compose network.

## Runtime controls

- The API runs using the non-root identity baked into the image, drops Linux capabilities, enables `no-new-privileges`, uses a read-only root filesystem, and has a bounded temporary filesystem.
- PostgreSQL and Redis use persistent named volumes. Redis persistence is enabled with append-only files.
- Services restart unless explicitly stopped and use Docker's local log driver with bounded size and file count.
- PostgreSQL and Redis have health checks; API startup waits for both dependencies to become healthy.
- The profile intentionally does not set fixed CPU/memory quotas. Select limits from measured host capacity and load testing before production rollout.
- Docker Compose hardening does not replace host patching, SSH restrictions, Cloud Firewall/host firewall rules, TLS, monitoring, backups, or a reviewed hostile-workload isolation design.

## Backup and restore

Take and verify a database backup before every migration or release. For example, write a custom-format dump to a protected location on the host:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec -T postgres pg_dump -U medusa -d medusa -Fc > medusa-$(date +%F-%H%M%S).dump
```

Encrypt and copy backups off-host, restrict access, define retention, and periodically test restoration into a disposable PostgreSQL instance. Named volumes are persistence across container recreation, not backups. Redis contains cache/rate-limit state and append-only persistence; decide separately whether its data needs backup for the deployment's recovery objectives.

To restore a database dump, stop application writes, take a fresh safety backup, and restore into the intended database using `pg_restore`. Confirm the target database and dump before running destructive restore commands.

## Release and rollback

1. Take and verify a database backup.
2. Record the deployed image identifier and current application revision.
3. Review migration compatibility with both the current and rollback application versions.
4. Deploy the reviewed revision and run `alembic upgrade head` as a deliberate release step.
5. Verify API readiness, logs, authentication, and critical application workflows.
6. If rollback is required, redeploy the previously recorded image/revision only when its schema compatibility is known. Restore the database only under an approved recovery decision; do not automatically roll back migrations or delete volumes.

Do not use `docker compose down -v` during routine deployment or rollback. It deletes named volume data.
