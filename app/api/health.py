from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/live", summary="Liveness probe")
def liveness() -> dict[str, str]:
    """Return success when the API process can respond to requests."""
    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
def readiness() -> dict[str, str]:
    """Placeholder readiness probe; dependency checks will be added with DB integration."""
    return {"status": "ready"}
