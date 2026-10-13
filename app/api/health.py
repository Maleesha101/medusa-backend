"""Liveness and dependency readiness probes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/live", summary="Liveness probe")
def liveness() -> dict[str, str]:
    """Return success when the API process can respond to requests."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    """Report ready only when the database accepts a lightweight query."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required dependency unavailable",
        ) from None
    return {"status": "ready"}
