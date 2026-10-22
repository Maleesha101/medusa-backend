import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.sandbox_host_preflight import REQUIRED_HOST_CAPABILITIES

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CLI_MODULE = "app.services.sandbox_host_preflight_cli"


def write_manifest(tmp_path: Path, content: str | bytes) -> Path:
    path = tmp_path / "capabilities.json"
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def run_cli(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", CLI_MODULE, str(path)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def versioned_manifest(capabilities: dict[str, object]) -> str:
    return json.dumps({"schema_version": 1, "capabilities": capabilities})


def test_cli_reports_ready_manifest_in_subprocess(tmp_path: Path) -> None:
    capabilities = {name: True for name in REQUIRED_HOST_CAPABILITIES}
    path = write_manifest(tmp_path, versioned_manifest(capabilities))

    result = run_cli(path)

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ready": True,
        "blocked": False,
        "missing": [],
        "unknown": [],
    }


def test_cli_reports_incomplete_manifest_as_blocked(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, versioned_manifest({"seccomp": False}))

    result = run_cli(path)

    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["ready"] is False
    assert output["blocked"] is True
    assert output["missing"] == ["seccomp"]
    assert len(output["unknown"]) == len(REQUIRED_HOST_CAPABILITIES) - 1
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ('{"schema_version":', "unable to read a valid JSON manifest"),
        (json.dumps([True, False]), "manifest must be a JSON object"),
        (
            json.dumps({"schema_version": 2, "capabilities": {}}),
            "unsupported manifest schema version",
        ),
        (
            json.dumps({"schema_version": 1, "capabilities": {}, "secret": "never-echo"}),
            "must contain only schema_version and capabilities",
        ),
        (
            json.dumps({"schema_version": 1, "capabilities": {"unknown_secret": "never-echo"}}),
            "unknown capability identifier",
        ),
        (
            json.dumps({"schema_version": 1, "capabilities": {"seccomp": "yes"}}),
            "capability values must be true, false, or null",
        ),
        (
            json.dumps({"schema_version": 1, "capabilities": []}),
            "capabilities must be a JSON object",
        ),
    ],
)
def test_cli_rejects_invalid_manifest_safely(
    tmp_path: Path, content: str, error: str
) -> None:
    path = write_manifest(tmp_path, content)

    result = run_cli(path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert error in result.stderr
    assert "Traceback" not in result.stderr
    assert "never-echo" not in result.stderr
    assert "unknown_secret" not in result.stderr


def test_cli_rejects_invalid_utf8_without_traceback(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, b"\xff\xfe")

    result = run_cli(path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "unable to read a valid JSON manifest" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_handles_missing_file_without_echoing_path_contents(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"

    result = run_cli(path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "unable to read a valid JSON manifest" in result.stderr
    assert "Traceback" not in result.stderr
