"""Verify a PostgreSQL backup by restoring it into an isolated disposable container."""

from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

POSTGRES_IMAGE = "postgres:16-alpine"
EXPECTED_TABLES = frozenset(
    {
        "alembic_version",
        "users",
        "organizations",
        "teams",
        "team_memberships",
        "competitions",
        "competition_rounds",
        "competition_registrations",
        "challenges",
        "challenge_flags",
        "challenge_submissions",
    }
)


def _validate_backup(path: Path) -> Path:
    """Return a resolved regular backup file without following a symlink."""
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError("The backup file must not be a symbolic link.")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("The backup path must be a regular file.")
    if resolved.stat().st_size == 0:
        raise ValueError("The backup file must not be empty.")
    return resolved


def _run(
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess],
    **kwargs: object,
) -> subprocess.CompletedProcess:
    return runner(command, check=True, **kwargs)


def verify_backup(
    backup_file: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    readiness_attempts: int = 30,
) -> None:
    """Restore and inspect a backup in a network-isolated temporary container."""
    if readiness_attempts < 1:
        raise ValueError("Readiness attempts must be at least 1.")
    backup = _validate_backup(backup_file)
    container = f"medusa-restore-check-{uuid.uuid4().hex[:12]}"
    created = False

    try:
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container,
                "--network",
                "none",
                "--label",
                "com.medusa.purpose=backup-restore-verification",
                "--env",
                "POSTGRES_USER=restore_check",
                "--env",
                "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32),
                "--env",
                "POSTGRES_DB=restore_check",
                POSTGRES_IMAGE,
            ],
            runner=runner,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        created = True

        ready = False
        for _ in range(readiness_attempts):
            result = runner(
                ["docker", "exec", container, "pg_isready", "-U", "restore_check"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                ready = True
                break
        if not ready:
            raise RuntimeError("Disposable PostgreSQL did not become ready in time.")

        with backup.open("rb") as archive:
            _run(
                [
                    "docker",
                    "exec",
                    "--interactive",
                    container,
                    "pg_restore",
                    "-U",
                    "restore_check",
                    "-d",
                    "restore_check",
                    "--no-owner",
                    "--no-privileges",
                    "--exit-on-error",
                ],
                runner=runner,
                stdin=archive,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=900,
            )

        query = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
        result = _run(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "restore_check",
                "-d",
                "restore_check",
                "-X",
                "-A",
                "-t",
                "-c",
                query,
            ],
            runner=runner,
            capture_output=True,
            text=True,
            timeout=30,
        )
        actual_tables = {
            line.strip() for line in (result.stdout or "").splitlines() if line.strip()
        }
        missing = sorted(EXPECTED_TABLES - actual_tables)
        if missing:
            raise RuntimeError(
                "Restored database is missing expected MEDUSA tables: " + ", ".join(missing)
            )
    finally:
        if created:
            cleanup = runner(
                ["docker", "rm", "--force", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
            if cleanup.returncode != 0:
                raise RuntimeError(
                    "Restore verification finished, but disposable container cleanup failed."
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_file", type=Path, help="Path to a verified PostgreSQL dump")
    parser.add_argument("--readiness-attempts", type=int, default=30)
    args = parser.parse_args()
    try:
        verify_backup(args.backup_file, readiness_attempts=args.readiness_attempts)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Restore verification failed: {exc}", file=sys.stderr)
        return 1
    print("PostgreSQL backup restored and MEDUSA schema verified in a disposable container.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
