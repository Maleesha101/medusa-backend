"""Private challenge flag management and participant submission endpoints."""

import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_organization_access, require_roles
from app.core.config import get_settings
from app.core.rate_limit import consume_rate_limit
from app.db.session import get_db
from app.models.challenge import Challenge
from app.models.challenge_flag import ChallengeFlag
from app.models.challenge_submission import ChallengeSubmission
from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.competition_round import CompetitionRound
from app.models.membership import Membership
from app.models.team import Team
from app.models.user import User
from app.schemas.submissions import (
    ChallengeFlagSet,
    ChallengeSubmissionCreate,
    ChallengeSubmissionResult,
)
from app.services.audit import record_audit_event
from app.services.scoreboard_events import publish_scoreboard_update

router = APIRouter(tags=["submissions"])


def _flag_digest(flag: str) -> str:
    """Create a keyed digest so a database-only leak does not enable offline guessing."""
    key = get_settings().auth_secret_key.encode("utf-8")
    return hmac.new(key, flag.encode("utf-8"), hashlib.sha256).hexdigest()


@router.put("/challenges/{challenge_id}/flag", status_code=status.HTTP_204_NO_CONTENT)
def set_challenge_flag(
    challenge_id: int,
    payload: ChallengeFlagSet,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("organizer", "admin")),
) -> None:
    """Set or replace a flag while its challenge remains a draft."""
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    round_item = db.get(CompetitionRound, challenge.round_id)
    competition = db.get(Competition, round_item.competition_id) if round_item else None
    if competition is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    require_organization_access(db, _user, competition.organization_id)
    if challenge.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Challenge flags can only be configured while the challenge is a draft",
        )

    stored_flag = db.get(ChallengeFlag, challenge_id)
    if stored_flag is None:
        stored_flag = ChallengeFlag(
            challenge_id=challenge_id,
            flag_hash=_flag_digest(payload.flag),
        )
        db.add(stored_flag)
    else:
        stored_flag.flag_hash = _flag_digest(payload.flag)

    record_audit_event(
        db,
        actor=_user,
        action="challenge.flag_configured",
        resource_type="challenge",
        resource_id=challenge_id,
    )
    db.commit()
    return None


@router.post(
    "/challenges/{challenge_id}/submissions",
    response_model=ChallengeSubmissionResult,
    status_code=status.HTTP_200_OK,
)
def submit_challenge_flag(
    challenge_id: int,
    payload: ChallengeSubmissionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChallengeSubmissionResult:
    """Check a flag for a team the caller belongs to and record only the result."""
    settings = get_settings()
    consume_rate_limit(
        key=f"medusa:submission:request:user:{user.id}",
        limit=settings.submission_request_limit,
        window_seconds=settings.submission_rate_window_seconds,
    )

    challenge = db.get(Challenge, challenge_id)
    if challenge is None or challenge.status != "published":
        raise HTTPException(status_code=404, detail="Challenge not found")

    round_item = db.get(CompetitionRound, challenge.round_id)
    competition = db.get(Competition, round_item.competition_id) if round_item is not None else None
    if competition is None:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if competition.status != "active":
        raise HTTPException(
            status_code=409,
            detail="Submissions are accepted only while the competition is active",
        )

    stored_flag = db.get(ChallengeFlag, challenge_id)
    if stored_flag is None:
        raise HTTPException(status_code=409, detail="Challenge flag is not configured")

    team = db.get(Team, payload.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if team.organization_id != competition.organization_id:
        raise HTTPException(status_code=403, detail="Team is not registered with this competition")

    membership = db.scalar(
        select(Membership).where(
            Membership.team_id == payload.team_id,
            Membership.user_id == user.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="You are not a member of this team")

    registration = db.scalar(
        select(CompetitionRegistration.id).where(
            CompetitionRegistration.competition_id == competition.id,
            CompetitionRegistration.team_id == team.id,
        )
    )
    if registration is None:
        raise HTTPException(
            status_code=409,
            detail="Team must register for this competition before submitting flags",
        )

    already_solved = db.scalar(
        select(ChallengeSubmission.id).where(
            ChallengeSubmission.challenge_id == challenge_id,
            ChallengeSubmission.team_id == payload.team_id,
            ChallengeSubmission.is_correct.is_(True),
        )
    )
    if already_solved is not None:
        raise HTTPException(status_code=409, detail="Team has already solved this challenge")

    is_correct = hmac.compare_digest(_flag_digest(payload.flag), stored_flag.flag_hash)
    if not is_correct:
        consume_rate_limit(
            key=f"medusa:submission:incorrect:team:{team.id}:challenge:{challenge_id}",
            limit=settings.incorrect_submission_limit,
            window_seconds=settings.submission_rate_window_seconds,
        )

    attempt = ChallengeSubmission(
        challenge_id=challenge_id,
        team_id=payload.team_id,
        user_id=user.id,
        is_correct=is_correct,
        points_awarded=challenge.points if is_correct else 0,
    )
    db.add(attempt)
    try:
        db.flush()
        record_audit_event(
            db,
            actor=user,
            action="challenge.submission",
            resource_type="challenge",
            resource_id=challenge_id,
            outcome="correct" if is_correct else "incorrect",
            details={
                "team_id": team.id,
                "submission_id": attempt.id,
                "points_awarded": attempt.points_awarded,
            },
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if is_correct:
            raise HTTPException(
                status_code=409, detail="Team has already solved this challenge"
            ) from None
        raise

    db.refresh(attempt)
    if is_correct:
        publish_scoreboard_update(competition.id, attempt.id)
    return ChallengeSubmissionResult(
        submission_id=attempt.id,
        challenge_id=attempt.challenge_id,
        correct=attempt.is_correct,
        submitted_at=attempt.submitted_at,
    )
