"""Retryable provider cleanup for terminal sandbox records."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.sandbox_instance import SandboxInstance
from app.services.audit import record_audit_event
from app.services.sandbox_controller import (
    SandboxController,
    SandboxControllerError,
    UnavailableSandboxController,
)

CLEANUP_ELIGIBLE_STATES = ("stopped", "failed", "expired")


def reconcile_provider_cleanup(
    db: Session,
    *,
    controller: SandboxController | None = None,
    batch_size: int = 50,
    now: datetime | None = None,
    base_backoff_seconds: int = 30,
    max_backoff_seconds: int = 3600,
) -> dict[str, int]:
    """Attempt cleanup for a bounded batch of terminal instances.

    Failed attempts are retained for later scheduled retries. The default
    controller is deliberately unavailable, so deployments cannot accidentally
    enable provider calls without explicitly wiring a reviewed implementation.
    """
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be between 1 and 500")

    if base_backoff_seconds < 1 or max_backoff_seconds < base_backoff_seconds:
        raise ValueError("Invalid cleanup backoff bounds")

    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    provider = controller or UnavailableSandboxController()
    sandboxes = list(
        db.scalars(
            select(SandboxInstance)
            .where(
                SandboxInstance.state.in_(CLEANUP_ELIGIBLE_STATES),
                SandboxInstance.provider_instance_id.is_not(None),
                SandboxInstance.cleanup_status.in_(("pending", "failed")),
                (SandboxInstance.cleanup_next_attempt_at.is_(None))
                | (SandboxInstance.cleanup_next_attempt_at <= current_time),
            )
            .order_by(SandboxInstance.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
    )

    cleaned = 0
    failed = 0
    for sandbox in sandboxes:
        sandbox.cleanup_attempts += 1
        try:
            provider.stop(sandbox.provider_instance_id)
        except SandboxControllerError:
            sandbox.cleanup_status = "failed"
            sandbox.cleanup_error_code = "provider_cleanup_failed"
            delay = min(
                base_backoff_seconds * (2 ** min(sandbox.cleanup_attempts - 1, 20)),
                max_backoff_seconds,
            )
            sandbox.cleanup_next_attempt_at = current_time + timedelta(seconds=delay)
            failed += 1
            outcome = "failure"
        else:
            sandbox.cleanup_status = "cleaned"
            sandbox.cleanup_error_code = None
            sandbox.cleanup_next_attempt_at = None
            cleaned += 1
            outcome = "success"

        record_audit_event(
            db,
            actor=None,
            action="sandbox.provider_cleanup",
            outcome=outcome,
            resource_type="sandbox_instance",
            resource_id=sandbox.id,
            details={
                "state": sandbox.state,
                "cleanup_status": sandbox.cleanup_status,
                "attempt": sandbox.cleanup_attempts,
                "next_attempt_at": (
                    sandbox.cleanup_next_attempt_at.isoformat()
                    if sandbox.cleanup_next_attempt_at is not None
                    else None
                ),
            },
        )

    if sandboxes:
        db.commit()
    return {"processed": len(sandboxes), "cleaned": cleaned, "failed": failed}
