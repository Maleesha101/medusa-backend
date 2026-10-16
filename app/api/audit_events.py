"""Administrative audit event query endpoint."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models.audit_event import AuditEvent
from app.models.user import User
from app.schemas.audit_events import AuditEventPublic

router = APIRouter(prefix="/audit-events", tags=["audit"])


@router.get("", response_model=list[AuditEventPublic])
def list_audit_events(
    action: str | None = Query(default=None, min_length=1, max_length=100),
    resource_type: str | None = Query(default=None, min_length=1, max_length=50),
    actor_user_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> list[AuditEvent]:
    """List newest audit events; only platform administrators may access this endpoint."""
    query = select(AuditEvent)
    if action is not None:
        query = query.where(AuditEvent.action == action)
    if resource_type is not None:
        query = query.where(AuditEvent.resource_type == resource_type)
    if actor_user_id is not None:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)
    query = query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    query = query.offset(offset).limit(limit)
    return list(db.scalars(query).all())
