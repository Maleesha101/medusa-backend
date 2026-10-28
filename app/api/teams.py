"""Team and membership endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User
from app.schemas.teams import CaptainTransfer, MemberPublic, TeamCreate, TeamDetail, TeamPublic

router = APIRouter(tags=["teams"])


def _active_organization(db: Session, organization_id: int) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def _has_live_competition_registration(db: Session, team_id: int) -> bool:
    """Return whether a team is registered for a published or active competition."""
    registration_id = db.scalar(
        select(CompetitionRegistration.id)
        .join(Competition, Competition.id == CompetitionRegistration.competition_id)
        .where(
            CompetitionRegistration.team_id == team_id,
            Competition.status.in_(("published", "active")),
        )
        .limit(1)
    )
    return registration_id is not None


def _team_detail(db: Session, team: Team) -> TeamDetail:
    memberships = db.scalars(
        select(Membership)
        .where(Membership.team_id == team.id)
        .order_by(Membership.joined_at, Membership.id)
    ).all()
    members = [
        MemberPublic(
            user_id=membership.user_id,
            role=membership.role,
            joined_at=membership.joined_at,
        )
        for membership in memberships
    ]
    return TeamDetail(
        id=team.id,
        organization_id=team.organization_id,
        name=team.name,
        captain_user_id=team.captain_user_id,
        created_at=team.created_at,
        members=members,
    )


@router.get("/organizations/{organization_id}/teams", response_model=list[TeamPublic])
def list_teams(
    organization_id: int,
    db: Session = Depends(get_db),
) -> list[Team]:
    """List teams in an active organization."""
    _active_organization(db, organization_id)
    return list(
        db.scalars(
            select(Team).where(Team.organization_id == organization_id).order_by(Team.name)
        ).all()
    )


@router.post(
    "/organizations/{organization_id}/teams",
    response_model=TeamDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_team(
    organization_id: int,
    payload: TeamCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamDetail:
    """Create a team and make the authenticated creator its captain."""
    _active_organization(db, organization_id)
    team = Team(
        organization_id=organization_id,
        name=payload.name.strip(),
        captain_user_id=user.id,
    )
    db.add(team)
    try:
        db.flush()
        db.add(Membership(team_id=team.id, user_id=user.id, role="captain"))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A team with this name already exists in the organization",
        ) from None
    db.refresh(team)
    return _team_detail(db, team)


@router.get("/teams/{team_id}", response_model=TeamDetail)
def get_team(team_id: int, db: Session = Depends(get_db)) -> TeamDetail:
    """Get a team's details and public membership list."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    organization = db.get(Organization, team.organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=404, detail="Team not found")
    return _team_detail(db, team)


@router.post("/teams/{team_id}/join", response_model=TeamDetail)
def join_team(
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamDetail:
    """Join a team as the authenticated user."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    _active_organization(db, team.organization_id)
    if _has_live_competition_registration(db, team_id):
        raise HTTPException(
            status_code=409,
            detail=(
                "Team membership is locked while registered for a published or active competition"
            ),
        )
    existing = db.scalar(
        select(Membership).where(
            Membership.team_id == team_id,
            Membership.user_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="You are already a member of this team")
    db.add(Membership(team_id=team_id, user_id=user.id, role="member"))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="You are already a member of this team",
        ) from None
    return _team_detail(db, team)


@router.put("/teams/{team_id}/captain", response_model=TeamDetail)
def transfer_captaincy(
    team_id: int,
    payload: CaptainTransfer,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamDetail:
    """Transfer captaincy to an existing member of the team."""
    team = db.scalar(select(Team).where(Team.id == team_id).with_for_update())
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    _active_organization(db, team.organization_id)
    if team.captain_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the current captain can transfer captaincy",
        )

    current_membership = db.scalar(
        select(Membership).where(
            Membership.team_id == team_id,
            Membership.user_id == user.id,
        )
    )
    if current_membership is None or current_membership.role != "captain":
        raise HTTPException(status_code=409, detail="Team captain membership is inconsistent")
    if payload.user_id == user.id:
        raise HTTPException(status_code=409, detail="Cannot transfer captaincy to yourself")

    target_membership = db.scalar(
        select(Membership).where(
            Membership.team_id == team_id,
            Membership.user_id == payload.user_id,
        )
    )
    if target_membership is None:
        raise HTTPException(status_code=404, detail="Target user is not a member of this team")

    current_membership.role = "member"
    target_membership.role = "captain"
    team.captain_user_id = target_membership.user_id
    db.commit()
    db.refresh(team)
    return _team_detail(db, team)


@router.delete("/teams/{team_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_team(
    team_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Leave a team; the captain must transfer captaincy before leaving."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    membership = db.scalar(
        select(Membership).where(
            Membership.team_id == team_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Team membership not found")
    if _has_live_competition_registration(db, team_id):
        raise HTTPException(
            status_code=409,
            detail=(
                "Team membership is locked while registered for a published or active competition"
            ),
        )
    if membership.role == "captain":
        raise HTTPException(
            status_code=409,
            detail="Team captain cannot leave until captaincy transfer is supported",
        )
    db.delete(membership)
    db.commit()
