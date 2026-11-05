"""Restore-test the newest encrypted off-site MEDUSA PostgreSQL backup."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from scripts.replicate_production_postgres_backup import (
    _validate_config,
    _validate_remote_dir,
)
from scripts.verify_production_postgres_restore import verify_backup

BACKUP_PATTERN = re.compile(r"^medusa-postgres-(\d{8}T\d{12}Z)\.dump$")


def select_latest_backup(listing: str) -> str:
    """Select the newest valid backup filename from an rclone files-only listing."""
    candidates: list[tuple[str, str]] = []
    for line in listing.splitlines():
        name = line.strip()
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            continue
        match = BACKUP_PATTERN.fullmatch(name)
        if match:
            candidates.append((match.group(1), name))
    if not candidates:
        raise RuntimeError("The encrypted remote contains no valid MEDUSA PostgreSQL backups.")
    return max(candidates)[1]


def run_restore_drill(
    config_file: Path,
    remote_name: str,
    remote_dir: str = "medusa-postgres-backups",
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    verifier: Callable[[Path], None] = verify_backup,
    temp_parent: Path | None = None,
) -> str:
    """Download the newest encrypted remote dump privately and restore-test it."""
    config = _validate_config(config_file, remote_name)
    directory = _validate_remote_dir(remote_dir)
    remote_root = f"{remote_name}:{directory}"
    common = ["rclone", "--config", str(config)]

    try:
        listing = runner(
            [*common, "lsf", "--files-only", "--format", "p", remote_root],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        backup_name = select_latest_backup(listing.stdout or "")
        with tempfile.TemporaryDirectory(
            prefix="medusa-offsite-restore-", dir=temp_parent
        ) as temporary_directory:
            local_backup = Path(temporary_directory) / backup_name
            runner(
                [
                    *common,
                    "copyto",
                    f"{remote_root}/{backup_name}",
                    str(local_backup),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1800,
            )
            if not local_backup.is_file() or local_backup.is_symlink():
                raise RuntimeError("The off-site backup download did not produce a regular file.")
            if local_backup.stat().st_size == 0:
                raise RuntimeError("The downloaded off-site backup is empty.")
            verifier(local_backup)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(
            "Off-site restore drill failed during remote listing or download."
        ) from None
    return backup_name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Private rclone config file")
    parser.add_argument("--remote", required=True, help="Name of an rclone crypt remote")
    parser.add_argument("--remote-dir", default="medusa-postgres-backups")
    parser.add_argument("--temp-dir", type=Path, help="Optional private filesystem for downloads")
    args = parser.parse_args()
    try:
        backup_name = run_restore_drill(
            args.config, args.remote, args.remote_dir, temp_parent=args.temp_dir
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Off-site restore drill failed: {exc}", file=sys.stderr)
        return 1
    print(f"Encrypted off-site backup restored successfully: {backup_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
