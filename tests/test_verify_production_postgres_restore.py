"""Tests for isolated production PostgreSQL restore verification."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_production_postgres_restore as restore


def successful_runner(command: list[str], **kwargs: object) -> SimpleNamespace:
    if command[:2] == ["docker", "run"]:
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    if "pg_isready" in command:
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    if "pg_restore" in command:
        assert kwargs["stdin"].read() == b"postgres-custom-dump"
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    if "psql" in command:
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(sorted(restore.EXPECTED_TABLES)),
            stderr="",
        )
    if command[:3] == ["docker", "rm", "--force"]:
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    raise AssertionError(f"Unexpected command: {command}")


def test_restores_backup_and_cleans_up(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"postgres-custom-dump")
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return successful_runner(command, **kwargs)

    restore.verify_backup(backup, runner=runner)

    docker_run = commands[0]
    assert "--network" in docker_run
    assert docker_run[docker_run.index("--network") + 1] == "none"
    assert "--publish" not in docker_run
    assert any("POSTGRES_PASSWORD=" in value for value in docker_run)
    assert commands[-1][:3] == ["docker", "rm", "--force"]


@pytest.mark.parametrize("contents", [None, b""])
def test_rejects_missing_or_empty_backup(tmp_path: Path, contents: bytes | None) -> None:
    backup = tmp_path / "missing.dump"
    if contents is not None:
        backup.write_bytes(contents)

    with pytest.raises((FileNotFoundError, ValueError)):
        restore.verify_backup(backup, runner=successful_runner)


def test_rejects_symlink_backup(tmp_path: Path) -> None:
    target = tmp_path / "real.dump"
    target.write_bytes(b"dump")
    link = tmp_path / "backup.dump"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symbolic link"):
        restore.verify_backup(link, runner=successful_runner)


def test_readiness_timeout_still_cleans_up(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"dump")
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "pg_isready" in command:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if command[:3] == ["docker", "rm", "--force"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    with pytest.raises(RuntimeError, match="did not become ready"):
        restore.verify_backup(backup, runner=runner, readiness_attempts=2)

    assert commands[-1][:3] == ["docker", "rm", "--force"]


def test_restore_failure_still_cleans_up(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"dump")
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["docker", "run"] or "pg_isready" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "pg_restore" in command:
            raise subprocess.CalledProcessError(1, command)
        if command[:3] == ["docker", "rm", "--force"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    with pytest.raises(subprocess.CalledProcessError):
        restore.verify_backup(backup, runner=runner)

    assert commands[-1][:3] == ["docker", "rm", "--force"]


def test_missing_schema_table_fails_and_cleans_up(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"dump")
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["docker", "run"] or "pg_isready" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "pg_restore" in command:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "psql" in command:
            tables = sorted(restore.EXPECTED_TABLES - {"users"})
            return SimpleNamespace(returncode=0, stdout="\n".join(tables), stderr="")
        if command[:3] == ["docker", "rm", "--force"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    with pytest.raises(RuntimeError, match="users"):
        restore.verify_backup(backup, runner=runner)

    assert commands[-1][:3] == ["docker", "rm", "--force"]


def test_cleanup_failure_is_reported(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"dump")

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        result = successful_runner(command, **kwargs)
        if command[:3] == ["docker", "rm", "--force"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="cleanup failed")
        return result

    with pytest.raises(RuntimeError, match="cleanup failed"):
        restore.verify_backup(backup, runner=runner)


def test_rejects_invalid_readiness_attempts(tmp_path: Path) -> None:
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"dump")

    with pytest.raises(ValueError, match="at least 1"):
        restore.verify_backup(backup, runner=successful_runner, readiness_attempts=0)
