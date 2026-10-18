"""Application service for sandbox lifecycle metadata.

This service never starts workloads. Runtime operations remain behind the trusted
SandboxController boundary and must not be enabled without an isolated provider.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.challenge import Challenge
from app.models.competition import Competition
from app.models.competition_round import CompetitionRound
from app.models.sandbox_instance import SandboxInstance
from app.models.user import User
from app.services.audit import record_audit_event


class SandboxLifecycleError(Exception):
    """Base class for safe, expected lifecycle errors."""


class SandboxNotFound(SandboxLifecycleError):
    """The sandbox does not exist or is not visible to the actor."""


class SandboxConflict(SandboxLifecycleError):
    """The requested lifecycle operation is not valid in the current state."""


class SandboxQuotaExceeded(SandboxLifecycleError):
    """The owner or competition has reached its active sandbox limit."""


class SandboxChallengeUnavailable(SandboxLifecycleError):
    """The challenge is not eligible for sandboxing."""


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Conservative quotas to be wired to validated deployment settings later."""

    max_active_per_owner: int = 2
    max_active_per_competition: int = 20
    max_lifetime: timedelta = timedelta(hours=2)


ACTIVE_STATES = ("pending", "running")
ALLOWED_TRANSITIONS = {
    "pending": frozenset({"running", "stopped", "failed", "expired"}),
    "running": frozenset({"stopped", "failed", "expired"}),
    "stopped": frozenset(),
    "failed": frozenset(),
    "expired": frozenset(),
}


def request_sandbox(
    db: Session,
    *,
    actor: User,
    challenge_id: int,
    expires_at: datetime,
    policy: SandboxPolicy = SandboxPolicy(),
    now: datetime | None = None,
) -> SandboxInstance:
    """Create a pending record after challenge eligibility and quota checks."""
    current_time = now or datetime.now(UTC)
    if expires_at.tzinfo is None or current_time.tzinfo is None:
        raise SandboxConflict("Sandbox timestamps must include a timezone")
    if expires_at <= current_time or expires_at > current_time + policy.max_lifetime:
        raise SandboxConflict("Sandbox expiry is outside the permitted lifetime")

    challenge_context = db.execute(
        select(Challenge.id, Competition.id.label("competition_id"))
        .join(CompetitionRound, Challenge.round_id == CompetitionRound.id)
        .join(Competition, CompetitionRound.competition_id == Competition.id)
        .where(
            Challenge.id == challenge_id,
            Challenge.status == "published",
            Competition.status == "active",
            Competition.is_public.is_(True),
        )
    ).one_or_none()
    if challenge_context is None:
        raise SandboxChallengeUnavailable("Challenge is not eligible for a sandbox")

    owner_active_count = (
        db.scalar(
            select(func.count(SandboxInstance.id)).where(
                SandboxInstance.owner_user_id == actor.id,
                SandboxInstance.state.in_(ACTIVE_STATES),
                SandboxInstance.expires_at > current_time,
            )
        )
        or 0
    )
    if owner_active_count >= policy.max_active_per_owner:
        raise SandboxQuotaExceeded("Owner sandbox limit reached")

    competition_active_count = (
        db.scalar(
            select(func.count(SandboxInstance.id))
            .join(Challenge, SandboxInstance.challenge_id == Challenge.id)
            .join(CompetitionRound, Challenge.round_id == CompetitionRound.id)
            .where(
                CompetitionRound.competition_id == challenge_context.competition_id,
                SandboxInstance.state.in_(ACTIVE_STATES),
                SandboxInstance.expires_at > current_time,
            )
        )
        or 0
    )
    if competition_active_count >= policy.max_active_per_competition:
        raise SandboxQuotaExceeded("Competition sandbox limit reached")

    sandbox = SandboxInstance(
        challenge_id=challenge_id,
        owner_user_id=actor.id,
        state="pending",
        expires_at=expires_at,
    )
    db.add(sandbox)
    db.flush()
    record_audit_event(
        db,
        actor=actor,
        action="sandbox.requested",
        resource_type="sandbox_instance",
        resource_id=sandbox.id,
        details={"challenge_id": challenge_id, "state": "pending"},
    )
    db.commit()
    db.refresh(sandbox)
    return sandbox


def transition_sandbox(
    db: Session,
    *,
    actor: User,
    sandbox_id: int,
    target_state: str,
    provider_instance_id: str | None = None,
    failure_code: str | None = None,
    now: datetime | None = None,
) -> SandboxInstance:
    """Apply an allowed transition; only the owner or an admin may request it.

    Provider identifiers and failure codes are trusted internal values and must
    never be populated directly from public request bodies.
    """
    sandbox = db.scalar(
        select(SandboxInstance).where(SandboxInstance.id == sandbox_id).with_for_update()
    )
    if sandbox is None or (sandbox.owner_user_id != actor.id and actor.role != "admin"):
        raise SandboxNotFound("Sandbox not found")

    previous_state = sandbox.state
    if target_state not in ALLOWED_TRANSITIONS.get(previous_state, frozenset()):
        raise SandboxConflict(f"Cannot transition sandbox from {previous_state} to {target_state}")

    current_time = now or datetime.now(UTC)
    if target_state == "running":
        if sandbox.expires_at <= current_time:
            raise SandboxConflict("Expired sandbox cannot be started")
        if not provider_instance_id:
            raise SandboxConflict("A provider instance ID is required when starting")
        sandbox.provider_instance_id = provider_instance_id
        sandbox.started_at = current_time
    elif target_state in {"stopped", "failed", "expired"}:
        sandbox.stopped_at = current_time
        if target_state == "failed":
            # Store only a short, trusted error code; never exception messages or secrets.
            sandbox.failure_code = failure_code[:64] if failure_code else "provider_failure"
    sandbox.state = target_state
    record_audit_event(
        db,
        actor=actor,
        action=f"sandbox.{target_state}",
        resource_type="sandbox_instance",
        resource_id=sandbox.id,
        details={"previous_state": previous_state, "state": target_state},
    )
    db.commit()
    db.refresh(sandbox)
    return sandbox
