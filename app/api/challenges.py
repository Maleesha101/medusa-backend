"""Challenge authoring and public catalog endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.session import get_db
from app.models.challenge import Challenge
from app.models.competition import Competition
from app.models.competition_round import CompetitionRound
from app.models.user import User
from app.schemas.challenges import (
    ChallengeCreate,
    ChallengePublic,
    ChallengeStatusUpdate,
    ChallengeUpdate,
)

router = APIRouter(tags=["challenges"])

PUBLIC_COMPETITION_STATUSES = {"published", "active", "completed"}
ALLOWED_CHALLENGE_TRANSITIONS = {
    "draft": {"published"},
    "published": {"archived"},
    "archived": set(),
}


def _challenge_or_404(db: Session, challenge_id: int) -> Challenge:
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def _public_parent_or_404(db: Session, round_id: int) -> CompetitionRound:
    round_item = db.get(CompetitionRound, round_id)
    if round_item is None:
        raise HTTPException(status_code=404, detail="Round not found")
    competition = db.get(Competition, round_item.competition_id)
    if (
        competition is None
        or not competition.is_public
        or competition.status not in PUBLIC_COMPETITION_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Round not found")
    return round_item


@router.get(
    "/rounds/{round_id}/challenges",
    response_model=list[ChallengePublic],
)
def list_published_challenges(
    round_id: int,
    db: Session = Depends(get_db),
) -> list[Challenge]:
    """List published challenges only when the parent competition is public."""
    _public_parent_or_404(db, round_id)
    query = (
        select(Challenge)
        .where(Challenge.round_id == round_id, Challenge.status == "published")
        .order_by(Challenge.points, Challenge.name)
    )
    return list(db.scalars(query).all())


@router.get("/challenges/{challenge_id}", response_model=ChallengePublic)
def get_published_challenge(
    challenge_id: int,
    db: Session = Depends(get_db),
) -> Challenge:
    """Get a published challenge without exposing drafts or archived content."""
    challenge = _challenge_or_404(db, challenge_id)
    if challenge.status != "published":
        raise HTTPException(status_code=404, detail="Challenge not found")
    _public_parent_or_404(db, challenge.round_id)
    return challenge


@router.post(
    "/rounds/{round_id}/challenges",
    response_model=ChallengePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_challenge(
    round_id: int,
    payload: ChallengeCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> Challenge:
    """Create a draft challenge in an existing non-finished round."""
    round_item = db.get(CompetitionRound, round_id)
    if round_item is None:
        raise HTTPException(status_code=404, detail="Round not found")
    competition = db.get(Competition, round_item.competition_id)
    if competition is None:
        raise HTTPException(status_code=404, detail="Competition not found")
    if competition.status in {"completed", "archived"}:
        raise HTTPException(
            status_code=409,
            detail="Cannot add challenges to a finished competition",
        )

    challenge = Challenge(
        round_id=round_id,
        name=payload.name.strip(),
        slug=payload.slug,
        description=payload.description,
        category=payload.category.strip(),
        points=payload.points,
        difficulty=payload.difficulty,
        status="draft",
    )
    db.add(challenge)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Challenge slug already exists in this round",
        ) from None
    db.refresh(challenge)
    return challenge


@router.patch("/challenges/{challenge_id}", response_model=ChallengePublic)
def update_challenge(
    challenge_id: int,
    payload: ChallengeUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> Challenge:
    """Update challenge metadata without accepting client-controlled status."""
    challenge = _challenge_or_404(db, challenge_id)
    if challenge.status == "archived":
        raise HTTPException(status_code=409, detail="Archived challenges cannot be edited")
    changes = payload.model_dump(exclude_unset=True)
    if not changes or any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Provide non-null fields to update")
    for field, value in changes.items():
        setattr(challenge, field, value.strip() if field in {"name", "category"} else value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Challenge slug already exists in this round",
        ) from None
    db.refresh(challenge)
    return challenge


@router.patch("/challenges/{challenge_id}/status", response_model=ChallengePublic)
def update_challenge_status(
    challenge_id: int,
    payload: ChallengeStatusUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> Challenge:
    """Publish or archive a challenge using the server-defined lifecycle."""
    challenge = _challenge_or_404(db, challenge_id)
    if payload.status not in ALLOWED_CHALLENGE_TRANSITIONS[challenge.status]:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid challenge status transition: {challenge.status} -> {payload.status}",
        )
    challenge.status = payload.status
    db.commit()
    db.refresh(challenge)
    return challenge
