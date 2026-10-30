from fastapi import FastAPI

from app.api.audit_events import router as audit_events_router
from app.api.auth import router as auth_router
from app.api.challenges import router as challenges_router
from app.api.competition_registrations import router as competition_registrations_router
from app.api.competitions import router as competitions_router
from app.api.health import router as health_router
from app.api.operations import router as operations_router
from app.api.organizations import router as organizations_router
from app.api.scoreboard import router as scoreboard_router
from app.api.scoreboard_realtime import router as scoreboard_realtime_router
from app.api.submissions import router as submissions_router
from app.api.teams import router as teams_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.6.0",
        description="MEDUSA CTF and competition management API",
    )
    application.include_router(health_router, prefix=settings.api_v1_prefix)
    application.include_router(auth_router, prefix=settings.api_v1_prefix)
    application.include_router(audit_events_router, prefix=settings.api_v1_prefix)
    application.include_router(operations_router, prefix=settings.api_v1_prefix)
    application.include_router(organizations_router, prefix=settings.api_v1_prefix)
    application.include_router(teams_router, prefix=settings.api_v1_prefix)
    application.include_router(competitions_router, prefix=settings.api_v1_prefix)
    application.include_router(competition_registrations_router, prefix=settings.api_v1_prefix)
    application.include_router(challenges_router, prefix=settings.api_v1_prefix)
    application.include_router(submissions_router, prefix=settings.api_v1_prefix)
    application.include_router(scoreboard_router, prefix=settings.api_v1_prefix)
    application.include_router(scoreboard_realtime_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
