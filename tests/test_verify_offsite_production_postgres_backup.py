"""Tests for encrypted off-site PostgreSQL restore drills."""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_offsite_production_postgres_backup as drill


def private_config(tmp_path: Path) -> Path:
    config = tmp_path / "rclone.conf"
    config.write_text(
        "[vault]\ntype = crypt\nremote = s3remote:medusa\n"
        "password = test-password\npassword2 = test-salt\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    return config


def test_selects_newest_valid_timestamp_and_ignores_other_entries() -> None:
    listing = "\n".join(
        [
            "medusa-postgres-20261104T030000000000Z.dump",
            "notes.txt",
            "medusa-postgres-20261105T021500000000Z.dump",
            "../medusa-postgres-20271105T021500000000Z.dump",
            "medusa-postgres-invalid.dump",
        ]
    )

    assert drill.select_latest_backup(listing) == ("medusa-postgres-20261105T021500000000Z.dump")


def test_empty_or_invalid_listing_fails() -> None:
    with pytest.raises(RuntimeError, match="no valid MEDUSA"):
        drill.select_latest_backup("notes.txt\n../backup.dump\n")


def test_downloads_newest_backup_verifies_and_cleans_temp_file(tmp_path: Path) -> None:
    config = private_config(tmp_path)
    temp_parent = tmp_path / "tmp"
    temp_parent.mkdir(mode=0o700)
    commands: list[list[str]] = []
    verified: list[Path] = []
    selected = "medusa-postgres-20261105T021500000000Z.dump"

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if "lsf" in command:
            return SimpleNamespace(
                stdout=(f"medusa-postgres-20261104T030000000000Z.dump\n{selected}\n")
            )
        Path(command[-1]).write_bytes(b"restorable-dump")
        return SimpleNamespace(returncode=0)

    def verifier(path: Path) -> None:
        verified.append(path)
        assert path.read_bytes() == b"restorable-dump"

    result = drill.run_restore_drill(
        config,
        "vault",
        runner=runner,
        verifier=verifier,
        temp_parent=temp_parent,
    )

    assert result == selected
    assert len(commands) == 2
    assert commands[0][3] == "lsf"
    assert commands[1][3] == "copyto"
    assert commands[1][-2] == f"vault:medusa-postgres-backups/{selected}"
    assert len(verified) == 1
    assert not verified[0].exists()
    assert list(temp_parent.iterdir()) == []


def test_download_failure_cleans_temp_directory(tmp_path: Path) -> None:
    config = private_config(tmp_path)
    temp_parent = tmp_path / "tmp"
    temp_parent.mkdir(mode=0o700)

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        if "lsf" in command:
            return SimpleNamespace(stdout="medusa-postgres-20261105T021500000000Z.dump\n")
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(RuntimeError, match="remote listing or download"):
        drill.run_restore_drill(config, "vault", runner=runner, temp_parent=temp_parent)

    assert list(temp_parent.iterdir()) == []


def test_restore_failure_cleans_temp_download(tmp_path: Path) -> None:
    config = private_config(tmp_path)
    temp_parent = tmp_path / "tmp"
    temp_parent.mkdir(mode=0o700)

    def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
        if "lsf" in command:
            return SimpleNamespace(
                stdout="medusa-postgres-20261105T021500000000Z.dump\n"
            )
        Path(command[-1]).write_bytes(b"downloaded")
        return SimpleNamespace(returncode=0)

    def fail_verifier(path: Path) -> None:
        raise RuntimeError("restore check failed")

    with pytest.raises(RuntimeError, match="restore check failed"):
        drill.run_restore_drill(
            config,
            "vault",
            runner=runner,
            verifier=fail_verifier,
            temp_parent=temp_parent,
        )

    assert list(temp_parent.iterdir()) == []


def test_rejects_plain_remote_before_running_rclone(tmp_path: Path) -> None:
    config = tmp_path / "rclone.conf"
    config.write_text("[vault]\ntype = s3\n", encoding="utf-8")
    config.chmod(0o600)

    def unexpected_runner(*args: object, **kwargs: object) -> SimpleNamespace:
        pytest.fail("rclone must not run for an unencrypted remote")

    with pytest.raises(ValueError, match="crypt remote"):
        drill.run_restore_drill(config, "vault", runner=unexpected_runner)
