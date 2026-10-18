import pytest

from app.services.sandbox_controller import (
    SandboxLaunchRequest,
    SandboxProviderUnavailable,
    UnavailableSandboxController,
)


def test_unconfigured_controller_fails_closed_on_launch() -> None:
    controller = UnavailableSandboxController()
    request = SandboxLaunchRequest(
        sandbox_id=1,
        challenge_id=2,
        image_reference="registry.example.invalid/challenge@sha256:" + "a" * 64,
        cpu_limit=1.0,
        memory_limit_mb=256,
        timeout_seconds=300,
    )

    with pytest.raises(SandboxProviderUnavailable):
        controller.launch(request)


def test_unconfigured_controller_fails_closed_on_stop() -> None:
    controller = UnavailableSandboxController()

    with pytest.raises(SandboxProviderUnavailable):
        controller.stop("provider-instance-id")
