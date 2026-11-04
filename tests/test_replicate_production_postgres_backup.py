"""Tests for encrypted off-site PostgreSQL backup replication."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import replicate_production_postgres_backup as replicate


def private_inputs(tmp_path: Path) -> tuple[Path, Path]:
    backup = tmp_path / "medusa-postgres-20261104T030000000000Z.dump"
    backup.write_bytes(b"verified-custom-format-dump")
    config = tmp_path / "rclone.conf"
    config.write_text(
        "[vault]\n"
        "type = crypt\n"
        "remote = s3remote:medusa-backups\n"
        "password = obscured-password\n"
        "password2 = obscured-salt\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    return backup, config


def test_replicates_and_verifies_only_selected_file(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        assert kwargs["check"] is True
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        return SimpleNamespace(returncode=0)

    destination = replicate.replicate_backup(backup, config, "vault", runner=runner)

    assert destination == (
        "vault:medusa-postgres-backups/medusa-postgres-20261104T030000000000Z.dump"
    )
    assert len(commands) == 2
    assert commands[0][2] == "copyto"
    assert "--immutable" in commands[0]
    assert commands[1][2] == "check"
    assert "--download" in commands[1]
    assert str(backup) in commands[0]
    assert str(backup) in commands[1]


def test_rejects_symlink_backup(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)
    link = tmp_path / "backup.dump"
    link.symlink_to(backup)

    with pytest.raises(ValueError, match="symbolic link"):
        replicate.replicate_backup(link, config, "vault")


def test_rejects_unrecognized_backup_name(tmp_path: Path) -> None:
    _, config = private_inputs(tmp_path)
    backup = tmp_path / "other.dump"
    backup.write_bytes(b"dump")

    with pytest.raises(ValueError, match="MEDUSA PostgreSQL backup"):
        replicate.replicate_backup(backup, config, "vault")


def test_rejects_empty_backup(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)
    backup.write_bytes(b"")

    with pytest.raises(ValueError, match="must not be empty"):
        replicate.replicate_backup(backup, config, "vault")


def test_rejects_non_private_config(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)
    config.chmod(0o644)

    with pytest.raises(ValueError, match="must be private"):
        replicate.replicate_backup(backup, config, "vault")


def test_rejects_plain_remote(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)
    config.write_text("[vault]\ntype = s3\n", encoding="utf-8")
    config.chmod(0o600)

    with pytest.raises(ValueError, match="crypt remote"):
        replicate.replicate_backup(backup, config, "vault")


def test_rejects_missing_encryption_password(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)
    config.write_text(
        "[vault]\ntype = crypt\nremote = s3remote:bucket\n",
        encoding="utf-8",
    )
    config.chmod(0o600)

    with pytest.raises(ValueError, match="missing required configuration"):
        replicate.replicate_backup(backup, config, "vault")


@pytest.mark.parametrize("remote_dir", ["", "../escape", "safe/../escape", "/absolute"])
def test_rejects_unsafe_remote_directory(tmp_path: Path, remote_dir: str) -> None:
    backup, config = private_inputs(tmp_path)

    with pytest.raises(ValueError, match="safe relative path"):
        replicate.replicate_backup(backup, config, "vault", remote_dir)


def test_transfer_failure_does_not_print_subprocess_error(tmp_path: Path) -> None:
    backup, config = private_inputs(tmp_path)

    def failing_runner(command: list[str], **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, command, stderr="secret-bearing output")

    with pytest.raises(RuntimeError, match="local backup was retained") as error:
        replicate.replicate_backup(backup, config, "vault", runner=failing_runner)

    assert "secret-bearing output" not in str(error.value)
    assert backup.exists()


def test_verification_failure_is_reported_without_deleting_local_backup(
    tmp_path: Path,
) -> None:
    backup, config = private_inputs(tmp_path)
    calls = 0

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(returncode=0)

    with pytest.raises(RuntimeError, match="verification failed"):
        replicate.replicate_backup(backup, config, "vault", runner=runner)

    assert calls == 2
    assert backup.exists()
