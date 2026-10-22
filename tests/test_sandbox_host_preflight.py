import pytest

from app.services.sandbox_host_preflight import (
    REQUIRED_HOST_CAPABILITIES,
    evaluate_sandbox_host_capabilities,
)


def fully_capable_host() -> dict[str, bool | None]:
    return {name: True for name in REQUIRED_HOST_CAPABILITIES}


def test_all_verified_capabilities_allow_preflight_readiness() -> None:
    report = evaluate_sandbox_host_capabilities(fully_capable_host())

    assert report.ready is True
    assert report.blocked is False
    assert report.missing == ()
    assert report.unknown == ()


@pytest.mark.parametrize("capability", REQUIRED_HOST_CAPABILITIES)
def test_missing_required_capability_blocks_readiness(capability: str) -> None:
    capabilities = fully_capable_host()
    capabilities[capability] = False

    report = evaluate_sandbox_host_capabilities(capabilities)

    assert report.ready is False
    assert report.blocked is True
    assert capability in report.missing


@pytest.mark.parametrize("capability", REQUIRED_HOST_CAPABILITIES)
def test_unknown_required_capability_blocks_readiness(capability: str) -> None:
    capabilities = fully_capable_host()
    capabilities.pop(capability)

    report = evaluate_sandbox_host_capabilities(capabilities)

    assert report.ready is False
    assert report.blocked is True
    assert capability in report.unknown


def test_explicit_none_is_unknown_not_missing() -> None:
    capabilities = fully_capable_host()
    capabilities["seccomp"] = None

    report = evaluate_sandbox_host_capabilities(capabilities)

    assert report.ready is False
    assert "seccomp" in report.unknown
    assert "seccomp" not in report.missing


def test_extra_inventory_keys_are_ignored() -> None:
    capabilities = fully_capable_host()
    capabilities["operator_note"] = True

    report = evaluate_sandbox_host_capabilities(capabilities)

    assert report.ready is True
