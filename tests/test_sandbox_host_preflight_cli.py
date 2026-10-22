import json

from app.services.sandbox_host_preflight import REQUIRED_HOST_CAPABILITIES
from app.services.sandbox_host_preflight_cli import main


def write_manifest(tmp_path, content: str):
    path = tmp_path / "capabilities.json"
    path.write_text(content, encoding="utf-8")
    return path


def test_cli_reports_ready_manifest(tmp_path, capsys) -> None:
    manifest = {name: True for name in REQUIRED_HOST_CAPABILITIES}
    path = write_manifest(tmp_path, json.dumps(manifest))

    assert main([str(path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"ready": True, "blocked": False, "missing": [], "unknown": []}


def test_cli_reports_blocked_manifest_and_nonzero_exit(tmp_path, capsys) -> None:
    path = write_manifest(tmp_path, json.dumps({"seccomp": False}))

    assert main([str(path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["ready"] is False
    assert output["blocked"] is True
    assert output["missing"] == ["seccomp"]
    assert len(output["unknown"]) == len(REQUIRED_HOST_CAPABILITIES) - 1


def test_cli_rejects_malformed_json_without_traceback(tmp_path, capsys) -> None:
    path = write_manifest(tmp_path, '{"seccomp":')

    assert main([str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unable to read a valid JSON manifest" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_unknown_capability_key_without_echoing_input(tmp_path, capsys) -> None:
    path = write_manifest(tmp_path, json.dumps({"secret_value": "do-not-print"}))

    assert main([str(path)]) == 2
    captured = capsys.readouterr()
    assert "unknown capability identifier" in captured.err
    assert "do-not-print" not in captured.err
    assert "secret_value" not in captured.err


def test_cli_rejects_non_boolean_capability_values(tmp_path, capsys) -> None:
    path = write_manifest(tmp_path, json.dumps({"seccomp": "yes"}))

    assert main([str(path)]) == 2
    assert "capability values must be true, false, or null" in capsys.readouterr().err


def test_cli_rejects_non_object_manifest(tmp_path, capsys) -> None:
    path = write_manifest(tmp_path, json.dumps([True, False]))

    assert main([str(path)]) == 2
    assert "manifest must be a JSON object" in capsys.readouterr().err
