"""Validate the production Compose profile's rendered security-sensitive settings."""

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".env.production.example"),
        "-f",
        str(ROOT / "compose.production.yaml"),
        "config",
        "--format",
        "json",
    ]
    rendered = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(rendered.stdout)
    services = config["services"]

    for name in ("postgres", "redis"):
        if services[name].get("ports"):
            raise SystemExit(f"{name} must not publish host ports")

    api_ports = services["api"].get("ports", [])
    if len(api_ports) != 1 or api_ports[0].get("host_ip") != "127.0.0.1":
        raise SystemExit("API must publish exactly one loopback-bound host port")

    api = services["api"]
    environment = api.get("environment", {})
    if environment.get("SANDBOX_PROVIDER") != "unavailable":
        raise SystemExit("Production Compose must keep SANDBOX_PROVIDER=unavailable")
    if "no-new-privileges:true" not in api.get("security_opt", []):
        raise SystemExit("API must enable no-new-privileges")
    if "ALL" not in api.get("cap_drop", []):
        raise SystemExit("API must drop all Linux capabilities")
    if api.get("read_only") is not True:
        raise SystemExit("API root filesystem must be read-only")

    forbidden = ("medusa_dev_only", "development-only-change-this-key-before-deployment")
    rendered_text = rendered.stdout
    if any(value in rendered_text for value in forbidden):
        raise SystemExit("Production Compose contains a development credential")

    print("Production Compose configuration passed security checks.")


if __name__ == "__main__":
    main()
