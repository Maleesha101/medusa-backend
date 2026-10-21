import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_sandbox_provider_defaults_to_unavailable() -> None:
    settings = Settings(database_url="sqlite://")

    assert settings.sandbox_provider == "unavailable"


def test_sandbox_provider_normalizes_unavailable_value() -> None:
    settings = Settings(database_url="sqlite://", sandbox_provider=" UNAVAILABLE ")

    assert settings.sandbox_provider == "unavailable"


@pytest.mark.parametrize("provider", ["docker", "podman", "kubernetes", "unknown", ""])
def test_unsupported_sandbox_provider_fails_validation(provider: str) -> None:
    with pytest.raises(ValidationError, match="SANDBOX_PROVIDER"):
        Settings(database_url="sqlite://", sandbox_provider=provider)
