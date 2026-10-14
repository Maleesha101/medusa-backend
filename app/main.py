from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="MEDUSA CTF and competition management API",
    )
    application.include_router(health_router, prefix=settings.api_v1_prefix)
    application.include_router(auth_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
