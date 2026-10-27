"""Competition team registration endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
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
    CompetitionRegistrationPublic,
    CompetitionRegistrationRosterItem,
)

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
    competition = db.get(Competition, competition_id)
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

    registration = CompetitionRegistration(
        competition_id=competition.id,
        team_id=team.id,
        registered_by_user_id=user.id,
    )
    db.add(registration)
    try:
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
    db.delete(registration)
    db.commit()
