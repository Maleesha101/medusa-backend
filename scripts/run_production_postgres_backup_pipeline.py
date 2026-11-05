"""Create a fresh verified PostgreSQL backup, then replicate that exact dump off-site."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.backup_production_postgres import create_backup
from scripts.replicate_production_postgres_backup import replicate_backup


def run_backup_pipeline(
    env_file: Path,
    backup_dir: Path,
    config_file: Path,
    remote_name: str,
    remote_dir: str = "medusa-postgres-backups",
    retention_days: int = 30,
) -> str:
    """Create a new local dump and replicate only that newly completed dump."""
    backup = create_backup(env_file, backup_dir, retention_days)
    return replicate_backup(backup, config_file, remote_name, remote_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--rclone-config", type=Path, required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--remote-dir", default="medusa-postgres-backups")
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()

    try:
        destination = run_backup_pipeline(
            args.env_file,
            args.backup_dir,
            args.rclone_config,
            args.remote,
            args.remote_dir,
            args.retention_days,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Scheduled backup pipeline failed: {exc}", file=sys.stderr)
        return 1

    print(f"Scheduled backup pipeline completed: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
