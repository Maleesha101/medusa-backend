"""Retryable provider cleanup for terminal sandbox records."""

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
) -> dict[str, int]:
    """Attempt cleanup for a bounded batch of terminal instances.

    Failed attempts are retained for later scheduled retries. The default
    controller is deliberately unavailable, so deployments cannot accidentally
    enable provider calls without explicitly wiring a reviewed implementation.
    """
    if not 1 <= batch_size <= 500:
        raise ValueError("batch_size must be between 1 and 500")

    provider = controller or UnavailableSandboxController()
    sandboxes = list(
        db.scalars(
            select(SandboxInstance)
            .where(
                SandboxInstance.state.in_(CLEANUP_ELIGIBLE_STATES),
                SandboxInstance.provider_instance_id.is_not(None),
                SandboxInstance.cleanup_status.in_(("pending", "failed")),
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
            failed += 1
            outcome = "failure"
        else:
            sandbox.cleanup_status = "cleaned"
            sandbox.cleanup_error_code = None
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
            },
        )

    if sandboxes:
        db.commit()
    return {"processed": len(sandboxes), "cleaned": cleaned, "failed": failed}
