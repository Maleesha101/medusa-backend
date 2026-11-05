# Production Compose deployment profile

This profile is for the MEDUSA application/control plane on a dedicated application host. It is separate from the local-development `compose.yaml`; do not replace the local workflow with it.

The profile does not provision a VPS, configure a host firewall or TLS reverse proxy, provide off-host backup storage, or isolate hostile challenge code. Keep `SANDBOX_PROVIDER=unavailable`. The API is bound to host loopback so a separately managed reverse proxy can terminate HTTPS. PostgreSQL and Redis have no published host ports.

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

The environment file must be a regular file with permissions that exclude group and other users (for example, `chmod 600 .env.production`). The destination directory must exclude group and other users (for example, `chmod 700 /mnt/medusa-backups`). The script writes files named `medusa-postgres-YYYYMMDDTHHMMSSffffffZ.dump` with mode 0600. It prunes only expired regular files matching that exact naming pattern, and only after a new backup has been verified. Retention is local cleanup, not an off-host backup policy.

For a scheduled deployment, use the repository's systemd oneshot service and persistent timer described in [Scheduled backup pipeline](#scheduled-backup-pipeline) below. The standalone backup command remains useful for manual runs. Monitor the service's exit status and alert on failed or missing daily backups. Named volumes are persistence across container recreation, not backups. Redis contains cache/rate-limit state and append-only persistence; decide separately whether its data needs backup for the deployment's recovery objectives.

### Restore verification drill

The backup script's `pg_restore --list` check confirms that PostgreSQL can read the archive directory; it does not prove that the archive can be restored. Use the dedicated verification script periodically to perform a real restore into a disposable PostgreSQL 16 container:

```bash
python scripts/verify_production_postgres_restore.py \
  /mnt/medusa-backups/medusa-postgres-YYYYMMDDTHHMMSSffffffZ.dump
```

The script validates the input file, starts a uniquely named container on Docker's `none` network (no published ports, production Compose network, or persistent volumes), waits for readiness with a bounded retry count, restores the archive, and checks that the expected MEDUSA core tables are present. It always attempts to remove the disposable container. Docker must be available to the invoking host account, and the PostgreSQL 16 image must be available locally or pullable.

A successful run proves that the archive can be restored and that the core schema exists; it is not a complete application-level recovery certification. For higher assurance, periodically restore into an isolated staging environment and run application integration checks against that restored database.

This command is verification-only. It does not read `.env.production`, use production database credentials, mount production volumes, or connect to the production database. Never modify it to target production as a shortcut. Any production restore requires a separately approved recovery plan, a fresh safety backup, a confirmed target, and a deliberate maintenance window; never automatically overwrite production data.


### Encrypted off-site backup replication

Local backup retention is not an independent backup. Configure an rclone `crypt` remote that wraps a separately managed remote (for example, an S3-compatible bucket), then copy each completed dump individually:

```bash
# Install rclone using its official installation instructions.
# Configure a remote named "medusa-vault" with type "crypt".
# Its underlying remote should point to a private bucket/prefix.
# Protect the rclone configuration and encryption recovery material.
chmod 600 /etc/medusa/rclone.conf

python scripts/replicate_production_postgres_backup.py \
  /mnt/medusa-backups/medusa-postgres-YYYYMMDDTHHMMSSffffffZ.dump \
  --config /etc/medusa/rclone.conf \
  --remote medusa-vault \
  --remote-dir medusa-postgres-backups
```

The command accepts only one correctly named MEDUSA dump and requires the selected rclone remote to be configured as type `crypt`. It uses rclone's immutable copy mode and then verifies the remote file by downloading and comparing its contents. It never deletes remote objects or the local source. Schedule it after the local backup command succeeds, and monitor both exit statuses. Use a separate host scheduler/alert for missing or failed off-site copies.

The rclone crypt password and optional salt are required to recover the backup. Store them in an approved secrets manager and maintain a separately protected recovery procedure; losing them makes encrypted backups unrecoverable. Do not commit rclone configuration, cloud credentials, crypt passwords, or salts. Restrict the underlying storage account and bucket permissions, enable provider-side versioning/object lock or equivalent retention controls where appropriate, and test account-level recovery independently. The script does not configure bucket policy, encryption-key escrow, object lock, or retention.

To recover a file for a restore drill, copy the selected object back through the same crypt remote to a private local directory, then pass the downloaded dump to `scripts/verify_production_postgres_restore.py`. Do not restore directly to production.


### Scheduled backup pipeline

Use the combined runner so off-site replication always follows a newly created, verified local dump and receives that exact file path. A failure in either stage returns a non-zero exit code; the local dump is retained if replication fails.

The example units live in `deploy/systemd/`. Adjust the repository, virtual-environment, environment-file, backup-directory, rclone-config, and remote paths/names in `medusa-backup.service` before installing. The service runs as the dedicated `medusa-backup` account and uses the `docker` group to access Docker. Membership in the Docker group is effectively root-equivalent on typical Linux hosts: grant it only to a trusted operator account, never to the API service or challenge workloads.

Prepare the account and private files. The backup directory must be writable only by the service account; the production environment and rclone configuration must be readable by that account and inaccessible to group/others:

```bash
sudo useradd --system --create-home --home-dir /var/lib/medusa-backup --shell /usr/sbin/nologin medusa-backup
sudo usermod -aG docker medusa-backup
sudo install -d -o medusa-backup -g medusa-backup -m 700 /mnt/medusa-backups
sudo install -d -o root -g root -m 755 /etc/medusa
sudo install -o medusa-backup -g medusa-backup -m 600 /path/to/.env.production /etc/medusa/.env.production
sudo install -o medusa-backup -g medusa-backup -m 600 /path/to/rclone.conf /etc/medusa/rclone.conf
```

Install the reviewed application checkout and its virtual environment at the paths configured in the service unit (the example expects `/opt/medusa` and `/opt/medusa/venv`). Install the unit files, review the service command and schedule, then enable the timer:

```bash
sudo install -m 644 deploy/systemd/medusa-backup.service /etc/systemd/system/medusa-backup.service
sudo install -m 644 deploy/systemd/medusa-backup.timer /etc/systemd/system/medusa-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now medusa-backup.timer
systemctl list-timers medusa-backup.timer
```

The timer runs daily at 02:15 host-local time, adds up to ten minutes of randomized delay, and has `Persistent=true` so a missed run is started after the host returns. Test the pipeline deliberately before relying on the timer:

```bash
sudo systemctl start medusa-backup.service
sudo systemctl status medusa-backup.service
sudo journalctl -u medusa-backup.service --since today
```

A successful service run means both a fresh local backup and its encrypted off-site copy were verified. A failed service is visible through systemd state and the journal. The unit includes an optional `OnFailure` hook. To use it, install `deploy/systemd/medusa-backup-alert@.service.example` as `/etc/systemd/system/medusa-backup-alert@.service`, replace its example `ExecStart` with an alert command supplied by your monitoring system, then reload systemd. The repository does not ship an alert receiver or send messages itself. Also configure external monitoring to alert if the timer has not completed successfully within your recovery objective; a timer being active does not prove a backup succeeded.

The service unit intentionally contains paths and a remote name, not passwords or cloud credentials. Protect the production env file and rclone crypt configuration separately. Keep the crypt password/salt recovery material in an approved secrets manager. Review the unit's hardening and filesystem paths for the target host before enabling it.
Do not use `docker compose down -v` as part of backup or restore. It deletes named volume data.

## Release and rollback

1. Take and verify a database backup.
2. Record the deployed image identifier and current application revision.
3. Review migration compatibility with both the current and rollback application versions.
4. Deploy the reviewed revision and run `alembic upgrade head` as a deliberate release step.
5. Verify API readiness, logs, authentication, and critical application workflows.
6. If rollback is required, redeploy the previously recorded image/revision only when its schema compatibility is known. Restore the database only under an approved recovery decision; do not automatically roll back migrations or delete volumes.

Do not use `docker compose down -v` during routine deployment or rollback. It deletes named volume data.
