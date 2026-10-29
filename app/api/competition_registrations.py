"""Competition team registration endpoints."""

import csv
from datetime import UTC, datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_organization_access,
    require_roles,
)
from app.db.session import get_db
from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.membership import Membership
from app.models.team import Team
from app.models.user import User
from app.schemas.competition_registrations import (
    CompetitionRegistrationCreate,
    CompetitionRegistrationMineItem,
    CompetitionRegistrationPublic,
    CompetitionRegistrationRosterItem,
)
from app.services.audit import record_audit_event

router = APIRouter(prefix="/competitions", tags=["competition registrations"])

PUBLIC_REGISTRATION_STATUSES = {"published", "active"}


def _utc(value: datetime) -> datetime:
    """Normalize a database timestamp to UTC, including naive SQLite timestamps."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.post(
    "/{competition_id}/registrations",
    response_model=CompetitionRegistrationPublic,
    status_code=status.HTTP_201_CREATED,
)
def register_team_for_competition(
    competition_id: int,
    payload: CompetitionRegistrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompetitionRegistration:
    """Register a team if its member is eligible and the window is open."""
    competition = db.scalar(
        select(Competition).where(Competition.id == competition_id).with_for_update()
    )
    if (
        competition is None
        or not competition.is_public
        or competition.status not in PUBLIC_REGISTRATION_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Public competition not found")

    now = datetime.now(UTC)
    if competition.registration_opens_at is not None and now < _utc(
        competition.registration_opens_at
    ):
        raise HTTPException(status_code=409, detail="Competition registration has not opened")
    if competition.registration_closes_at is not None and now >= _utc(
        competition.registration_closes_at
    ):
        raise HTTPException(status_code=409, detail="Competition registration is closed")

    team = db.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.organization_id != competition.organization_id:
        raise HTTPException(status_code=403, detail="Team is not eligible for this competition")

    membership = db.scalar(
        select(Membership).where(
            Membership.team_id == team.id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this team")

    team_size = db.scalar(
        select(func.count(Membership.user_id)).where(Membership.team_id == team.id)
    )
    if (
        competition.min_team_size is not None
        and team_size is not None
        and team_size < competition.min_team_size
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Team must have at least {competition.min_team_size} members",
        )
    if (
        competition.max_team_size is not None
        and team_size is not None
        and team_size > competition.max_team_size
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Team cannot have more than {competition.max_team_size} members",
        )

    if competition.max_teams is not None:
        registered_count = db.scalar(
            select(func.count(CompetitionRegistration.id)).where(
                CompetitionRegistration.competition_id == competition.id
            )
        )
        if registered_count is not None and registered_count >= competition.max_teams:
            raise HTTPException(status_code=409, detail="Competition has reached team capacity")

    registration = CompetitionRegistration(
        competition_id=competition.id,
        team_id=team.id,
        registered_by_user_id=user.id,
    )
    db.add(registration)
    try:
        db.flush()
        record_audit_event(
            db,
            actor=user,
            action="competition.registration_created",
            resource_type="competition_registration",
            resource_id=registration.id,
            details={
                "competition_id": competition.id,
                "team_id": team.id,
                "registration_id": registration.id,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Team is already registered for this competition",
        ) from None
    db.refresh(registration)
    return registration


@router.get(
    "/{competition_id}/registrations/mine",
    response_model=list[CompetitionRegistrationMineItem],
)
def list_my_competition_registrations(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CompetitionRegistrationMineItem]:
    """List registrations only for teams the authenticated user currently belongs to."""
    competition = db.get(Competition, competition_id)
    if (
        competition is None
        or not competition.is_public
        or competition.status not in {"published", "active", "completed"}
    ):
        raise HTTPException(status_code=404, detail="Competition not found")

    rows = db.execute(
        select(
            CompetitionRegistration.id,
            CompetitionRegistration.competition_id,
            CompetitionRegistration.team_id,
            Team.name.label("team_name"),
            CompetitionRegistration.registered_at,
        )
        .join(Team, Team.id == CompetitionRegistration.team_id)
        .join(Membership, Membership.team_id == Team.id)
        .where(
            CompetitionRegistration.competition_id == competition_id,
            Membership.user_id == user.id,
        )
        .order_by(CompetitionRegistration.registered_at, CompetitionRegistration.id)
    ).all()
    return [CompetitionRegistrationMineItem(**row._mapping) for row in rows]


def _csv_safe_cell(value: str) -> str:
    """Prefix spreadsheet formula-leading text so CSV exports remain inert."""
    if value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


@router.get(
    "/{competition_id}/registrations/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_competition_registrations(
    competition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("organizer", "admin")),
) -> Response:
    """Download a CSV roster for an organization the caller is authorized to manage."""
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    require_organization_access(db, user, competition.organization_id)

    rows = db.execute(
        select(
            CompetitionRegistration.id,
            CompetitionRegistration.competition_id,
            CompetitionRegistration.team_id,
            Team.name.label("team_name"),
            CompetitionRegistration.registered_by_user_id,
            CompetitionRegistration.registered_at,
        )
        .join(Team, Team.id == CompetitionRegistration.team_id)
        .where(CompetitionRegistration.competition_id == competition_id)
        .order_by(CompetitionRegistration.registered_at, CompetitionRegistration.id)
    ).all()

    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(
        [
            "registration_id",
            "competition_id",
            "team_id",
            "team_name",
            "registered_by_user_id",
            "registered_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.competition_id,
                row.team_id,
                _csv_safe_cell(row.team_name),
                row.registered_by_user_id,
                row.registered_at.isoformat(),
            ]
        )

    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="competition-{competition_id}-registrations.csv"'
            )
        },
    )


@router.get(
    "/{competition_id}/registrations",
    response_model=list[CompetitionRegistrationRosterItem],
)
def list_competition_registrations(
    competition_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("organizer", "admin")),
) -> list[CompetitionRegistrationRosterItem]:
    """List a competition's registrations for an authorized organization manager."""
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    require_organization_access(db, user, competition.organization_id)

    rows = db.execute(
        select(CompetitionRegistration, Team.name)
        .join(Team, Team.id == CompetitionRegistration.team_id)
        .where(CompetitionRegistration.competition_id == competition_id)
        .order_by(CompetitionRegistration.registered_at, CompetitionRegistration.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        CompetitionRegistrationRosterItem(
            id=registration.id,
            competition_id=registration.competition_id,
            team_id=registration.team_id,
            team_name=team_name,
            registered_by_user_id=registration.registered_by_user_id,
            registered_at=registration.registered_at,
        )
        for registration, team_name in rows
    ]


@router.delete(
    "/{competition_id}/registrations/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def withdraw_team_registration(
    competition_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Allow a team captain to withdraw before the competition becomes active."""
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    if competition.status != "published":
        raise HTTPException(
            status_code=409,
            detail="Team registration cannot be withdrawn after the competition starts",
        )
    now = datetime.now(UTC)
    if competition.registration_closes_at is not None and now >= _utc(
        competition.registration_closes_at
    ):
        raise HTTPException(status_code=409, detail="Competition registration is closed")

    team = db.get(Team, team_id)
    if team is None or team.organization_id != competition.organization_id:
        raise HTTPException(status_code=404, detail="Team registration not found")
    if team.captain_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the team captain can withdraw registration",
        )

    registration = db.scalar(
        select(CompetitionRegistration).where(
            CompetitionRegistration.competition_id == competition_id,
            CompetitionRegistration.team_id == team_id,
        )
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="Team registration not found")
    registration_id = registration.id
    db.delete(registration)
    record_audit_event(
        db,
        actor=user,
        action="competition.registration_withdrawn",
        resource_type="competition_registration",
        resource_id=registration_id,
        details={
            "competition_id": competition.id,
            "team_id": team.id,
            "registration_id": registration_id,
        },
    )
    db.commit()
