"""Competition and round management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models.competition import Competition
from app.models.competition_round import CompetitionRound
from app.models.organization import Organization
from app.models.user import User
from app.schemas.competitions import (
    CompetitionCreate,
    CompetitionPublic,
    CompetitionStatusUpdate,
    RoundCreate,
    RoundPublic,
)
from app.services.audit import record_audit_event

router = APIRouter(prefix="/competitions", tags=["competitions"])

ALLOWED_TRANSITIONS = {
    "draft": {"published"},
    "published": {"active"},
    "active": {"completed"},
    "completed": {"archived"},
    "archived": set(),
}


def _competition_or_404(db: Session, competition_id: int) -> Competition:
    competition = db.get(Competition, competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


@router.get("", response_model=list[CompetitionPublic])
def list_competitions(db: Session = Depends(get_db)) -> list[Competition]:
    """List public published or running competitions."""
    query = (
        select(Competition)
        .where(
            Competition.is_public.is_(True),
            Competition.status.in_(("published", "active", "completed")),
        )
        .order_by(Competition.starts_at, Competition.name)
    )
    return list(db.scalars(query).all())


@router.post(
    "",
    response_model=CompetitionPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_competition(
    payload: CompetitionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("organizer", "admin")),
) -> Competition:
    """Create a draft competition under an existing active organization."""
    organization = db.get(Organization, payload.organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=404, detail="Active organization not found")
    competition = Competition(
        organization_id=payload.organization_id,
        created_by_user_id=user.id,
        name=payload.name.strip(),
        slug=payload.slug,
        description=payload.description,
        is_public=payload.is_public,
        status="draft",
        registration_opens_at=payload.registration_opens_at,
        registration_closes_at=payload.registration_closes_at,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(competition)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Competition slug already exists") from None
    db.refresh(competition)
    return competition


@router.get("/{competition_id}", response_model=CompetitionPublic)
def get_competition(
    competition_id: int,
    db: Session = Depends(get_db),
) -> Competition:
    """Get a published, active, or completed public competition."""
    competition = _competition_or_404(db, competition_id)
    if not competition.is_public or competition.status not in {
        "published",
        "active",
        "completed",
    }:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


@router.patch("/{competition_id}/status", response_model=CompetitionPublic)
def update_competition_status(
    competition_id: int,
    payload: CompetitionStatusUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> Competition:
    """Move a competition through the allowed lifecycle transitions."""
    competition = _competition_or_404(db, competition_id)
    if payload.status not in ALLOWED_TRANSITIONS[competition.status]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invalid competition status transition: {competition.status} -> {payload.status}"
            ),
        )
    previous_status = competition.status
    competition.status = payload.status
    record_audit_event(
        db,
        actor=_user,
        action="competition.status_changed",
        resource_type="competition",
        resource_id=competition.id,
        details={"from": previous_status, "to": competition.status},
    )
    db.commit()
    db.refresh(competition)
    return competition


@router.get("/{competition_id}/rounds", response_model=list[RoundPublic])
def list_rounds(
    competition_id: int,
    db: Session = Depends(get_db),
) -> list[CompetitionRound]:
    """List rounds only when their competition is publicly visible."""
    competition = _competition_or_404(db, competition_id)
    if not competition.is_public or competition.status not in {
        "published",
        "active",
        "completed",
    }:
        raise HTTPException(status_code=404, detail="Competition not found")
    query = (
        select(CompetitionRound)
        .where(CompetitionRound.competition_id == competition_id)
        .order_by(CompetitionRound.position)
    )
    return list(db.scalars(query).all())


@router.post(
    "/{competition_id}/rounds",
    response_model=RoundPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_round(
    competition_id: int,
    payload: RoundCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> CompetitionRound:
    """Create a round with a unique position and slug within the competition."""
    competition = _competition_or_404(db, competition_id)
    if competition.status in {"completed", "archived"}:
        raise HTTPException(
            status_code=409,
            detail="Cannot add rounds to a finished competition",
        )
    round_item = CompetitionRound(
        competition_id=competition_id,
        name=payload.name.strip(),
        slug=payload.slug,
        position=payload.position,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(round_item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Round position or slug already exists in this competition",
        ) from None
    db.refresh(round_item)
    return round_item
