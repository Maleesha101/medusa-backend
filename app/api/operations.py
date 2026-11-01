"""Administrator-only infrastructure and sandbox operational metrics."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models.operational_alert import OperationalAlert
from app.models.user import User
from app.services.operational_metrics import collect_operational_metrics

router = APIRouter(prefix="/admin/operations", tags=["operations"])


@router.get("/metrics")
def get_operational_metrics(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> dict:
    """Return current process/host metrics, sandbox load, and threshold alerts."""
    return collect_operational_metrics(db, get_settings())


@router.get("/alerts")
def list_operational_alerts(
    active_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> list[dict]:
    """List persisted operational alert state; notification recipients are never exposed."""
    query = select(OperationalAlert)
    if active_only:
        query = query.where(OperationalAlert.is_active.is_(True))
    rows = db.scalars(
        query.order_by(OperationalAlert.last_observed_at.desc(), OperationalAlert.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "alert_key": row.alert_key,
            "metric": row.metric,
            "severity": row.severity,
            "value": row.value,
            "threshold": row.threshold,
            "unit": row.unit,
            "is_active": row.is_active,
            "first_observed_at": row.first_observed_at,
            "last_observed_at": row.last_observed_at,
            "resolved_at": row.resolved_at,
        }
        for row in rows
    ]
