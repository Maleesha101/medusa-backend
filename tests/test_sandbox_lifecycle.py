from datetime import UTC, datetime, timedelta

import pytest

from app.models.sandbox_instance import SandboxInstance
from app.models.user import User
from app.services.sandbox_lifecycle import (
    SandboxConflict,
    SandboxNotFound,
    SandboxPolicy,
    transition_sandbox,
)


def test_pending_sandbox_can_transition_to_running(session_factory) -> None:
    with session_factory() as db:
        owner = User(
            email="sandbox-owner@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        db.add(owner)
        db.flush()
        sandbox = SandboxInstance(
            challenge_id=1,
            owner_user_id=owner.id,
            state="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(sandbox)
        db.commit()
        sandbox_id = sandbox.id
        owner_id = owner.id

    with session_factory() as db:
        owner = db.get(User, owner_id)
        sandbox = transition_sandbox(
            db,
            actor=owner,
            sandbox_id=sandbox_id,
            target_state="running",
            provider_instance_id="trusted-provider-123",
        )
        assert sandbox.state == "running"
        assert sandbox.provider_instance_id == "trusted-provider-123"
        assert sandbox.started_at is not None


def test_non_owner_cannot_transition_sandbox(session_factory) -> None:
    with session_factory() as db:
        owner = User(
            email="sandbox-owner2@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        other = User(
            email="sandbox-other@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        db.add_all([owner, other])
        db.flush()
        sandbox = SandboxInstance(
            challenge_id=1,
            owner_user_id=owner.id,
            state="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(sandbox)
        db.commit()
        sandbox_id = sandbox.id
        other_id = other.id

    with session_factory() as db:
        other = db.get(User, other_id)
        with pytest.raises(SandboxNotFound):
            transition_sandbox(
                db,
                actor=other,
                sandbox_id=sandbox_id,
                target_state="stopped",
            )


def test_terminal_sandbox_cannot_transition_again(session_factory) -> None:
    with session_factory() as db:
        owner = User(
            email="sandbox-owner3@example.test",
            password_hash="not-a-real-hash",
            role="participant",
        )
        db.add(owner)
        db.flush()
        sandbox = SandboxInstance(
            challenge_id=1,
            owner_user_id=owner.id,
            state="stopped",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        db.add(sandbox)
        db.commit()
        sandbox_id = sandbox.id
        owner_id = owner.id

    with session_factory() as db:
        owner = db.get(User, owner_id)
        with pytest.raises(SandboxConflict):
            transition_sandbox(
                db,
                actor=owner,
                sandbox_id=sandbox_id,
                target_state="running",
                provider_instance_id="trusted-provider-456",
            )


def test_sandbox_policy_defaults_are_conservative() -> None:
    policy = SandboxPolicy()
    assert policy.max_active_per_owner == 2
    assert policy.max_active_per_competition == 20
    assert policy.max_lifetime == timedelta(hours=2)
