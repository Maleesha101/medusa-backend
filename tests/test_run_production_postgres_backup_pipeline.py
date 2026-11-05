"""Tests for the scheduled PostgreSQL backup pipeline orchestration."""

from pathlib import Path

import pytest

from scripts import run_production_postgres_backup_pipeline as pipeline


def test_pipeline_replicates_exact_new_backup(monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = Path("/etc/medusa/.env.production")
    backup_dir = Path("/mnt/medusa-backups")
    config_file = Path("/etc/medusa/rclone.conf")
    backup = backup_dir / "medusa-postgres-20261105T021500000000Z.dump"
    calls: list[tuple[object, ...]] = []

    def fake_create(env: Path, directory: Path, retention: int) -> Path:
        calls.append(("backup", env, directory, retention))
        return backup

    def fake_replicate(selected: Path, config: Path, remote: str, remote_dir: str) -> str:
        calls.append(("replicate", selected, config, remote, remote_dir))
        return f"{remote}:{remote_dir}/{selected.name}"

    monkeypatch.setattr(pipeline, "create_backup", fake_create)
    monkeypatch.setattr(pipeline, "replicate_backup", fake_replicate)

    result = pipeline.run_backup_pipeline(
        env_file, backup_dir, config_file, "vault", "medusa-dumps", 14
    )

    assert result == f"vault:medusa-dumps/{backup.name}"
    assert calls == [
        ("backup", env_file, backup_dir, 14),
        ("replicate", backup, config_file, "vault", "medusa-dumps"),
    ]


def test_replication_is_not_attempted_when_backup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_backup(*args: object, **kwargs: object) -> Path:
        raise RuntimeError("backup failed")

    def unexpected_replicate(*args: object, **kwargs: object) -> str:
        pytest.fail("replication must not run after backup failure")

    monkeypatch.setattr(pipeline, "create_backup", fail_backup)
    monkeypatch.setattr(pipeline, "replicate_backup", unexpected_replicate)

    with pytest.raises(RuntimeError, match="backup failed"):
        pipeline.run_backup_pipeline(Path("env"), Path("backups"), Path("rclone.conf"), "vault")


def test_replication_failure_propagates_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_backup = Path("/mnt/backups/medusa-postgres-20261105T021500000000Z.dump")
    calls: list[Path] = []

    def fake_create(*args: object, **kwargs: object) -> Path:
        return new_backup

    def fail_replicate(selected: Path, *args: object, **kwargs: object) -> str:
        calls.append(selected)
        raise RuntimeError("replication failed")

    monkeypatch.setattr(pipeline, "create_backup", fake_create)
    monkeypatch.setattr(pipeline, "replicate_backup", fail_replicate)

    with pytest.raises(RuntimeError, match="replication failed"):
        pipeline.run_backup_pipeline(Path("env"), Path("backups"), Path("rclone.conf"), "vault")

    assert calls == [new_backup]
