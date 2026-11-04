"""Create and verify a protected PostgreSQL backup for the production Compose stack."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
BACKUP_PATTERN = re.compile(r"^medusa-postgres-\d{8}T\d{12}Z\.dump$")
DOCKER_DATA_ROOTS = (
    Path("/var/lib/docker"),
    Path("/var/lib/containers"),
    Path("/var/lib/postgresql"),
)


def _require_private_file(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("The production environment file must be a regular file.")
    if resolved.stat().st_mode & 0o077:
        raise ValueError("The production environment file must not be accessible by group or others.")
    return resolved


def _require_backup_directory(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("The backup directory must be an absolute path.")
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("The backup destination must be an existing directory.")
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("The backup destination must be outside the repository.")
    if any(resolved == root or root in resolved.parents for root in DOCKER_DATA_ROOTS):
        raise ValueError("The backup destination must be outside Docker and database data directories.")
    if resolved.stat().st_mode & 0o077:
        raise ValueError("The backup directory must have private permissions (for example, chmod 700).")
    if not os.access(resolved, os.W_OK):
        raise ValueError("The backup directory is not writable by the current user.")
    return resolved


def _remove_expired_backups(directory: Path, retention_days: int, now: datetime) -> int:
    cutoff = (now - timedelta(days=retention_days)).timestamp()
    removed = 0
    for candidate in directory.iterdir():
        if not BACKUP_PATTERN.fullmatch(candidate.name) or candidate.is_symlink():
            continue
        try:
            if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                candidate.unlink()
                removed += 1
        except FileNotFoundError:
            continue
    return removed


def create_backup(
    env_file: Path,
    backup_dir: Path,
    retention_days: int = 30,
    *,
    now: datetime | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Path:
    """Create an atomic, verified dump and then prune expired matching backups."""
    if retention_days < 1:
        raise ValueError("Retention days must be at least 1.")
    env_path = _require_private_file(env_file)
    destination = _require_backup_directory(backup_dir)
    observed_at = now or datetime.now(timezone.utc)
    timestamp = observed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    final_path = destination / f"medusa-postgres-{timestamp}.dump"
    if final_path.exists():
        raise ValueError("A backup already exists for this timestamp; retry in the next second.")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".medusa-postgres-", suffix=".tmp", dir=destination
    )
    temporary_path = Path(temporary_name)
    os.fchmod(descriptor, 0o600)

    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env_path),
        "-f",
        str(ROOT / "compose.production.yaml"),
        "exec",
        "-T",
        "postgres",
    ]
    try:
        with os.fdopen(descriptor, "wb") as dump_file:
            runner(
                [*compose, "pg_dump", "-U", "medusa", "-d", "medusa", "-Fc"],
                cwd=ROOT,
                stdout=dump_file,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            dump_file.flush()
            os.fsync(dump_file.fileno())
            dump_file.seek(0)
            runner(
                [*compose, "pg_restore", "--list"],
                cwd=ROOT,
                stdin=dump_file,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        os.link(temporary_path, final_path)
        temporary_path.unlink()
    except (OSError, subprocess.SubprocessError):
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(
            "PostgreSQL backup or verification failed; no completed backup was retained."
        ) from None
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    _remove_expired_backups(destination, retention_days, observed_at)
    return final_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.production")
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()
    try:
        backup = create_backup(args.env_file, args.backup_dir, args.retention_days)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified PostgreSQL backup created: {backup.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
