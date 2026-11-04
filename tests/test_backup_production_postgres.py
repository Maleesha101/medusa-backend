"""Tests for the production PostgreSQL backup helper."""

import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import backup_production_postgres as backup


def private_inputs(tmp_path: Path) -> tuple[Path, Path]:
    env_file = tmp_path / ".env.production"
    env_file.write_text("POSTGRES_PASSWORD=not-a-real-secret\n", encoding="utf-8")
    env_file.chmod(0o600)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    backup_dir.chmod(0o700)
    return env_file, backup_dir


def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    if "pg_dump" in command:
        kwargs["stdout"].write(b"custom-format-dump")
    elif "pg_restore" in command:
        assert kwargs["stdin"].read() == b"custom-format-dump"
    else:
        raise AssertionError(f"Unexpected command: {command}")
    return subprocess.CompletedProcess(command, 0)


def test_creates_private_verified_backup(tmp_path: Path) -> None:
    env_file, backup_dir = private_inputs(tmp_path)
    observed_at = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)

    result = backup.create_backup(
        env_file, backup_dir, now=observed_at, runner=fake_runner
    )

    assert result.name == "medusa-postgres-20261104T030000Z.dump"
    assert result.read_bytes() == b"custom-format-dump"
    assert result.stat().st_mode & 0o777 == 0o600
    assert not list(backup_dir.glob("*.tmp"))


def test_rejects_environment_file_with_permissive_mode(tmp_path: Path) -> None:
    env_file, backup_dir = private_inputs(tmp_path)
    env_file.chmod(0o644)

    with pytest.raises(ValueError, match="group or others"):
        backup.create_backup(env_file, backup_dir, runner=fake_runner)


def test_rejects_backup_directory_inside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file, backup_dir = private_inputs(tmp_path)
    repository = tmp_path / "repository"
    nested = repository / "backups"
    nested.mkdir(parents=True, mode=0o700)
    nested.chmod(0o700)
    monkeypatch.setattr(backup, "ROOT", repository)

    with pytest.raises(ValueError, match="outside the repository"):
        backup.create_backup(env_file, nested, runner=fake_runner)


def test_rejects_backup_directory_with_permissive_mode(tmp_path: Path) -> None:
    env_file, backup_dir = private_inputs(tmp_path)
    backup_dir.chmod(0o755)

    with pytest.raises(ValueError, match="private permissions"):
        backup.create_backup(env_file, backup_dir, runner=fake_runner)


@pytest.mark.parametrize("failed_command", ["pg_dump", "pg_restore"])
def test_failed_dump_or_verification_leaves_no_completed_backup(
    tmp_path: Path, failed_command: str
) -> None:
    env_file, backup_dir = private_inputs(tmp_path)

    def failing_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        if failed_command in command:
            if "pg_dump" in command:
                kwargs["stdout"].write(b"partial-dump")
            raise subprocess.CalledProcessError(1, command)
        return fake_runner(command, **kwargs)

    with pytest.raises(RuntimeError, match="no completed backup"):
        backup.create_backup(env_file, backup_dir, runner=failing_runner)

    assert not list(backup_dir.glob("medusa-postgres-*.dump"))
    assert not list(backup_dir.glob(".medusa-postgres-*.tmp"))


def test_retention_removes_only_expired_matching_regular_files(tmp_path: Path) -> None:
    _, backup_dir = private_inputs(tmp_path)
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    expired = backup_dir / "medusa-postgres-20261001T000000Z.dump"
    recent = backup_dir / "medusa-postgres-20261103T000000Z.dump"
    unrelated = backup_dir / "customer-export.dump"
    expired.write_bytes(b"old")
    recent.write_bytes(b"new")
    unrelated.write_bytes(b"keep")
    old_timestamp = (now - timedelta(days=40)).timestamp()
    os.utime(expired, (old_timestamp, old_timestamp))
    os.utime(unrelated, (old_timestamp, old_timestamp))

    removed = backup._remove_expired_backups(backup_dir, 30, now)

    assert removed == 1
    assert not expired.exists()
    assert recent.exists()
    assert unrelated.exists()


def test_rejects_nonpositive_retention(tmp_path: Path) -> None:
    env_file, backup_dir = private_inputs(tmp_path)

    with pytest.raises(ValueError, match="at least 1"):
        backup.create_backup(env_file, backup_dir, retention_days=0, runner=fake_runner)
