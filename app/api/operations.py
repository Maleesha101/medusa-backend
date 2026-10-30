"""Administrator-only infrastructure and sandbox operational metrics."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import get_settings
from app.db.session import get_db
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
