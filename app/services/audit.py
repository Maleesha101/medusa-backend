"""Helpers for recording security-sensitive actions in the current transaction."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.user import User


def record_audit_event(
    db: Session,
    *,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    """Queue an audit event without committing; caller commits it with the business action.

    Callers must only provide allowlisted, non-sensitive metadata. Never pass credentials,
    tokens, submitted flags, flag digests, or arbitrary request bodies.
    """
    event = AuditEvent(
        actor_user_id=actor.id if actor is not None else None,
        actor_role=actor.role if actor is not None else None,
        action=action,
        outcome=outcome,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(event)
    return event
