"""Fail-closed capability evaluation for a future Linux sandbox host.

This module evaluates operator-verified capabilities only. It does not inspect
or modify the host, launch containers, or execute challenge code.
"""

from collections.abc import Mapping
from dataclasses import dataclass

# These identifiers represent controls that must be verified for the actual
# deployment. A boolean True is evidence supplied by a trusted operator/check;
# False means explicitly unavailable, and None/missing means not verified.
REQUIRED_HOST_CAPABILITIES: tuple[str, ...] = (
    "linux_namespaces",
    "cgroups_v2",
    "cpu_memory_pid_limits",
    "strong_workload_isolation",
    "seccomp",
    "apparmor_or_selinux",
    "network_namespaces",
    "host_firewall_default_deny",
    "block_metadata_and_internal_egress",
    "bounded_ephemeral_storage",
    "provider_enforced_hard_deadline",
    "idempotent_cleanup_and_reconciliation",
    "immutable_image_allowlist",
    "dedicated_least_privilege_worker_identity",
    "no_runtime_socket_or_host_secret_mounts",
)


@dataclass(frozen=True, slots=True)
class SandboxHostPreflightReport:
    """Sanitized result of evaluating the declared host capabilities."""

    ready: bool
    missing: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        """Return whether provider activation must remain blocked."""
        return not self.ready


def evaluate_sandbox_host_capabilities(
    capabilities: Mapping[str, bool | None],
) -> SandboxHostPreflightReport:
    """Evaluate declared capabilities; missing or unknown controls block readiness.

    Extra capability keys are ignored so callers can supply richer host
    inventories without changing this release gate.
    """
    missing = tuple(name for name in REQUIRED_HOST_CAPABILITIES if capabilities.get(name) is False)
    unknown = tuple(name for name in REQUIRED_HOST_CAPABILITIES if capabilities.get(name) is None)
    return SandboxHostPreflightReport(
        ready=not missing and not unknown,
        missing=missing,
        unknown=unknown,
    )
