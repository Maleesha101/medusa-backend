from datetime import UTC, datetime, timedelta

import pytest

from app.models.sandbox_instance import SandboxInstance
from app.models.user import User
from app.services.sandbox_cleanup import reconcile_provider_cleanup
from app.services.sandbox_controller import (
    SandboxLaunchRequest,
    SandboxLaunchResult,
    SandboxProviderUnavailable,
)


class RecordingController:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.stopped: list[str] = []

    def launch(self, request: SandboxLaunchRequest) -> SandboxLaunchResult:
        raise NotImplementedError

    def stop(self, provider_instance_id: str) -> None:
        self.stopped.append(provider_instance_id)
        if self.fail:
            raise SandboxProviderUnavailable("provider unavailable")


def _make_terminal_sandbox(db, owner: User, provider_id: str) -> int:
    sandbox = SandboxInstance(
        challenge_id=1,
        owner_user_id=owner.id,
        state="expired",
        provider_instance_id=provider_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        cleanup_status="pending",
        cleanup_attempts=0,
    )
    db.add(sandbox)
    db.commit()
    return sandbox.id


def test_cleanup_marks_provider_instance_cleaned(session_factory) -> None:
    controller = RecordingController()
    with session_factory() as db:
        owner = User(
            email="cleanup-owner@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        db.add(owner)
        db.flush()
        sandbox_id = _make_terminal_sandbox(db, owner, "provider-cleanup-1")

    with session_factory() as db:
        result = reconcile_provider_cleanup(db, controller=controller)
        assert result == {"processed": 1, "cleaned": 1, "failed": 0}

    with session_factory() as db:
        sandbox = db.get(SandboxInstance, sandbox_id)
        assert sandbox.cleanup_status == "cleaned"
        assert sandbox.cleanup_attempts == 1
        assert sandbox.cleanup_error_code is None
    assert controller.stopped == ["provider-cleanup-1"]


def test_cleanup_failure_remains_retryable(session_factory) -> None:
    controller = RecordingController(fail=True)
    with session_factory() as db:
        owner = User(
            email="cleanup-retry-owner@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        db.add(owner)
        db.flush()
        sandbox_id = _make_terminal_sandbox(db, owner, "provider-cleanup-2")

    with session_factory() as db:
        result = reconcile_provider_cleanup(db, controller=controller)
        assert result == {"processed": 1, "cleaned": 0, "failed": 1}

    with session_factory() as db:
        sandbox = db.get(SandboxInstance, sandbox_id)
        assert sandbox.cleanup_status == "failed"
        assert sandbox.cleanup_attempts == 1
        assert sandbox.cleanup_error_code == "provider_cleanup_failed"


def test_cleanup_validates_batch_size(session_factory) -> None:
    with session_factory() as db, pytest.raises(ValueError):
        reconcile_provider_cleanup(db, batch_size=0)


def test_cleanup_failure_sets_backoff_and_is_not_retried_early(session_factory) -> None:
    controller = RecordingController(fail=True)
    now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    with session_factory() as db:
        owner = User(
            email="cleanup-backoff-owner@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        db.add(owner)
        db.flush()
        sandbox_id = _make_terminal_sandbox(db, owner, "provider-cleanup-backoff")

    with session_factory() as db:
        result = reconcile_provider_cleanup(db, controller=controller, now=now)
        assert result == {"processed": 1, "cleaned": 0, "failed": 1}

    with session_factory() as db:
        sandbox = db.get(SandboxInstance, sandbox_id)
        retry_at = sandbox.cleanup_next_attempt_at
        assert retry_at is not None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        else:
            retry_at = retry_at.astimezone(UTC)
        assert retry_at == now + timedelta(seconds=30)

    with session_factory() as db:
        result = reconcile_provider_cleanup(
            db,
            controller=controller,
            now=now + timedelta(seconds=29),
        )
        assert result == {"processed": 0, "cleaned": 0, "failed": 0}

    with session_factory() as db:
        result = reconcile_provider_cleanup(
            db,
            controller=controller,
            now=now + timedelta(seconds=30),
        )
        assert result == {"processed": 1, "cleaned": 0, "failed": 1}

    assert controller.stopped == [
        "provider-cleanup-backoff",
        "provider-cleanup-backoff",
    ]


def test_cleanup_rejects_invalid_backoff_bounds(session_factory) -> None:
    with session_factory() as db, pytest.raises(ValueError):
        reconcile_provider_cleanup(
            db,
            base_backoff_seconds=60,
            max_backoff_seconds=30,
        )
