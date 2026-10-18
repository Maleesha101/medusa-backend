"""Sandbox provider boundary.

No Docker/container runtime is controlled by the API in this phase. A concrete
provider must enforce isolation and resource limits before it can be enabled.
"""

from dataclasses import dataclass
from typing import Protocol


class SandboxControllerError(RuntimeError):
    """Base error for sandbox provider failures."""


class SandboxProviderUnavailable(SandboxControllerError):
    """Raised when no safe isolated execution provider is configured."""


@dataclass(frozen=True, slots=True)
class SandboxLaunchRequest:
    """Validated inputs required by a trusted sandbox provider."""

    sandbox_id: int
    challenge_id: int
    image_reference: str
    cpu_limit: float
    memory_limit_mb: int
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class SandboxLaunchResult:
    """Opaque provider result; never populated from participant-controlled IDs."""

    provider_instance_id: str


class SandboxController(Protocol):
    """Operations implemented by a trusted, isolated sandbox provider."""

    def launch(self, request: SandboxLaunchRequest) -> SandboxLaunchResult:
        """Launch a challenge within strict resource and network isolation."""

    def stop(self, provider_instance_id: str) -> None:
        """Stop a previously launched provider instance."""


class UnavailableSandboxController:
    """Safe default until an isolated provider is explicitly configured."""

    def launch(self, request: SandboxLaunchRequest) -> SandboxLaunchResult:
        del request
        raise SandboxProviderUnavailable("No isolated sandbox provider is configured")

    def stop(self, provider_instance_id: str) -> None:
        del provider_instance_id
        raise SandboxProviderUnavailable("No isolated sandbox provider is configured")
