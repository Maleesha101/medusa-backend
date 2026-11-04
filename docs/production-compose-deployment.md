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

The repository includes a host-invoked backup script. It streams a PostgreSQL custom-format dump from the Compose database, verifies the archive with `pg_restore --list` inside the PostgreSQL container, and only then atomically publishes the completed file. Failed dumps or verification do not leave a file with the completed-backup name.

Prepare a dedicated, protected backup destination outside the repository and Docker/database data directories. Prefer a separately mounted encrypted disk or backup volume. The directory must already exist and be private:

```bash
sudo install -d -m 700 -o "$USER" -g "$(id -gn)" /mnt/medusa-backups
```

Run from the repository root (the backup destination must be an absolute path):

```bash
python scripts/backup_production_postgres.py \
  --env-file .env.production \
  --backup-dir /mnt/medusa-backups \
  --retention-days 30
```

The environment file must be a regular file with permissions that exclude group and other users (for example, `chmod 600 .env.production`). The destination directory must exclude group and other users (for example, `chmod 700 /mnt/medusa-backups`). The script writes files named `medusa-postgres-YYYYMMDDTHHMMSSZ.dump` with mode 0600. It prunes only expired regular files matching that exact naming pattern, and only after a new backup has been verified. Retention is local cleanup, not an off-host backup policy.

Schedule the command using the host's cron or systemd timer under an account that can access Docker and the protected destination. For example, a daily 02:15 cron entry (adjust absolute paths and schedule for the host):

```cron
15 2 * * * /usr/bin/python3 /opt/medusa/scripts/backup_production_postgres.py --env-file /opt/medusa/.env.production --backup-dir /mnt/medusa-backups --retention-days 30
```

Monitor the scheduler's exit status and alert on failed or missing daily backups. Copy verified dumps to an independent off-host destination, encrypt them in transit and at rest, restrict access, and define retention according to the recovery objectives. The script does not perform encryption or off-host transfer. Named volumes are persistence across container recreation, not backups. Redis contains cache/rate-limit state and append-only persistence; decide separately whether its data needs backup for the deployment's recovery objectives.

### Restore verification drill

Periodically test a backup against a disposable PostgreSQL container. This example does not publish a database port or connect to the production database:

```bash
BACKUP_FILE=/mnt/medusa-backups/medusa-postgres-YYYYMMDDTHHMMSSZ.dump
RESTORE_PASSWORD="$(openssl rand -hex 32)"
docker run -d --rm --name medusa-restore-drill \
  -e POSTGRES_PASSWORD="$RESTORE_PASSWORD" postgres:16-alpine
trap 'docker rm -f medusa-restore-drill >/dev/null 2>&1 || true' EXIT
until docker exec medusa-restore-drill pg_isready -U postgres; do sleep 2; done
docker exec medusa-restore-drill createdb -U postgres restore_drill
docker exec -i medusa-restore-drill pg_restore -U postgres -d restore_drill \
  --no-owner --no-privileges < "$BACKUP_FILE"
docker exec medusa-restore-drill psql -U postgres -d restore_drill -c '\\dt'
```

Confirm the expected application tables and perform application-level checks against the disposable database. Remove the disposable container after the drill. Do not point this procedure at the production database. Any production restore requires an approved recovery plan, a fresh safety backup, a confirmed target, and a deliberate maintenance window; never automatically overwrite production data.

Do not use `docker compose down -v` as part of backup or restore. It deletes named volume data.

## Release and rollback

1. Take and verify a database backup.
2. Record the deployed image identifier and current application revision.
3. Review migration compatibility with both the current and rollback application versions.
4. Deploy the reviewed revision and run `alembic upgrade head` as a deliberate release step.
5. Verify API readiness, logs, authentication, and critical application workflows.
6. If rollback is required, redeploy the previously recorded image/revision only when its schema compatibility is known. Restore the database only under an approved recovery decision; do not automatically roll back migrations or delete volumes.

Do not use `docker compose down -v` during routine deployment or rollback. It deletes named volume data.
