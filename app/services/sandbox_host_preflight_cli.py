"""CLI for evaluating an operator-supplied sandbox capability manifest.

This command does not inspect the host or activate a sandbox provider.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from app.services.sandbox_host_preflight import (
    REQUIRED_HOST_CAPABILITIES,
    evaluate_sandbox_host_capabilities,
)

MANIFEST_SCHEMA_VERSION = 1


def _load_manifest(path: Path) -> Mapping[str, bool | None]:
    """Load and validate a versioned JSON capability manifest safely."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("unable to read a valid JSON manifest") from exc

    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object")
    if set(raw) != {"schema_version", "capabilities"}:
        raise ValueError("manifest must contain only schema_version and capabilities")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema version")

    capabilities = raw["capabilities"]
    if not isinstance(capabilities, dict):
        raise ValueError("capabilities must be a JSON object")

    allowed = set(REQUIRED_HOST_CAPABILITIES)
    if any(not isinstance(key, str) or key not in allowed for key in capabilities):
        raise ValueError("manifest contains an unknown capability identifier")
    if any(value is not None and not isinstance(value, bool) for value in capabilities.values()):
        raise ValueError("capability values must be true, false, or null")
    return capabilities


def main(argv: Sequence[str] | None = None) -> int:
    """Run the preflight CLI and return a stable process exit code."""
    parser = argparse.ArgumentParser(
        description="Evaluate an operator-supplied sandbox host capability manifest."
    )
    parser.add_argument(
        "manifest",
        type=Path,
        help="path to a version 1 JSON capability manifest",
    )
    args = parser.parse_args(argv)

    try:
        capabilities = _load_manifest(args.manifest)
    except ValueError as exc:
        print(f"Invalid sandbox host preflight manifest: {exc}.", file=sys.stderr)
        return 2

    report = evaluate_sandbox_host_capabilities(capabilities)
    print(
        json.dumps(
            {
                "ready": report.ready,
                "blocked": report.blocked,
                "missing": list(report.missing),
                "unknown": list(report.unknown),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
