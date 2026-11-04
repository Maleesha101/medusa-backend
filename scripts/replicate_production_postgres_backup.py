"""Replicate one verified PostgreSQL dump to an rclone-encrypted off-site remote."""

from __future__ import annotations

import argparse
import configparser
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

BACKUP_PATTERN = re.compile(r"^medusa-postgres-\d{8}T\d{12}Z\.dump$")
REMOTE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_backup(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError("The backup file must not be a symbolic link.")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not BACKUP_PATTERN.fullmatch(resolved.name):
        raise ValueError("Select one regular MEDUSA PostgreSQL backup file.")
    if resolved.stat().st_size == 0:
        raise ValueError("The backup file must not be empty.")
    return resolved


def _validate_config(path: Path, remote_name: str) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise ValueError("The rclone config must not be a symbolic link.")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("The rclone config must be a regular file.")
    if resolved.stat().st_mode & 0o077:
        raise ValueError("The rclone config must be private (for example, chmod 600).")
    if not REMOTE_NAME_PATTERN.fullmatch(remote_name):
        raise ValueError("The rclone remote name contains unsupported characters.")

    config = configparser.ConfigParser(interpolation=None)
    try:
        with resolved.open(encoding="utf-8") as stream:
            config.read_file(stream)
    except (OSError, configparser.Error, UnicodeError):
        raise ValueError("The rclone config could not be read.") from None

    if not config.has_section(remote_name):
        raise ValueError("The requested rclone remote is not configured.")
    section = config[remote_name]
    if section.get("type") != "crypt":
        raise ValueError("The selected rclone remote must be an encrypted crypt remote.")
    if not section.get("remote") or not section.get("password"):
        raise ValueError("The encrypted rclone remote is missing required configuration.")
    return resolved


def _validate_remote_dir(remote_dir: str) -> str:
    if remote_dir.startswith("/"):
        raise ValueError("The remote directory must be a safe relative path.")
    normalized = remote_dir.strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("The remote directory must be a safe relative path.")
    if any("\\" in part or ":" in part for part in normalized.split("/")):
        raise ValueError("The remote directory contains unsupported characters.")
    return normalized


def replicate_backup(
    backup_file: Path,
    config_file: Path,
    remote_name: str,
    remote_dir: str = "medusa-postgres-backups",
    *,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    """Copy one dump to a configured crypt remote and verify the copied bytes."""
    backup = _validate_backup(backup_file)
    config = _validate_config(config_file, remote_name)
    directory = _validate_remote_dir(remote_dir)
    destination = f"{remote_name}:{directory}/{backup.name}"
    common = ["rclone", "--config", str(config)]

    try:
        runner(
            [
                *common,
                "copyto",
                "--immutable",
                str(backup),
                destination,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1800,
        )
        runner(
            [
                *common,
                "check",
                "--download",
                str(backup),
                destination,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1800,
        )
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError(
            "Off-site backup replication or verification failed; local backup was retained."
        ) from None
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup_file", type=Path)
    parser.add_argument("--config", type=Path, required=True, help="Private rclone config file")
    parser.add_argument("--remote", required=True, help="Name of an rclone crypt remote")
    parser.add_argument("--remote-dir", default="medusa-postgres-backups")
    args = parser.parse_args()
    try:
        destination = replicate_backup(
            args.backup_file, args.config, args.remote, args.remote_dir
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Off-site backup replication failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified encrypted off-site backup: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
