"""Public competition scoreboard endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select, union
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.challenge import Challenge
from app.models.challenge_submission import ChallengeSubmission
from app.models.competition import Competition
from app.models.competition_registration import CompetitionRegistration
from app.models.competition_round import CompetitionRound
from app.models.team import Team
from app.schemas.scoreboard import ScoreboardEntry, ScoreboardPublic

router = APIRouter(prefix="/competitions", tags=["scoreboard"])

PUBLIC_COMPETITION_STATUSES = {"published", "active", "completed"}


@router.get("/{competition_id}/scoreboard", response_model=ScoreboardPublic)
def get_competition_scoreboard(
    competition_id: int,
    db: Session = Depends(get_db),
) -> ScoreboardPublic:
    """Return standings for registered teams and teams that have submitted."""
    competition = db.get(Competition, competition_id)
    if (
        competition is None
        or not competition.is_public
        or competition.status not in PUBLIC_COMPETITION_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Competition not found")

    correct = ChallengeSubmission.is_correct.is_(True)
    submission_scores = (
        select(
            ChallengeSubmission.team_id.label("team_id"),
            func.coalesce(
                func.sum(case((correct, ChallengeSubmission.points_awarded), else_=0)),
                0,
            ).label("points"),
            func.count(case((correct, ChallengeSubmission.id), else_=None)).label("solves"),
            func.max(case((correct, ChallengeSubmission.submitted_at), else_=None)).label(
                "last_solved_at"
            ),
        )
        .join(Challenge, Challenge.id == ChallengeSubmission.challenge_id)
        .join(CompetitionRound, CompetitionRound.id == Challenge.round_id)
        .where(CompetitionRound.competition_id == competition_id)
        .group_by(ChallengeSubmission.team_id)
        .subquery()
    )

    registered_team_ids = select(CompetitionRegistration.team_id).where(
        CompetitionRegistration.competition_id == competition_id
    )
    submitted_team_ids = select(submission_scores.c.team_id)
    eligible_team_ids = union(registered_team_ids, submitted_team_ids).subquery()

    query = (
        select(
            Team.id.label("team_id"),
            Team.name.label("team_name"),
            func.coalesce(submission_scores.c.points, 0).label("points"),
            func.coalesce(submission_scores.c.solves, 0).label("solves"),
            submission_scores.c.last_solved_at.label("last_solved_at"),
        )
        .join(eligible_team_ids, eligible_team_ids.c.team_id == Team.id)
        .outerjoin(submission_scores, submission_scores.c.team_id == Team.id)
        .where(Team.organization_id == competition.organization_id)
        .order_by(
            func.coalesce(submission_scores.c.points, 0).desc(),
            submission_scores.c.last_solved_at.asc(),
            Team.name.asc(),
            Team.id.asc(),
        )
    )

    rows = db.execute(query).all()
    entries: list[ScoreboardEntry] = []
    previous_points: int | None = None
    current_rank = 0
    for position, row in enumerate(rows, start=1):
        points = int(row.points)
        if previous_points is None or points != previous_points:
            current_rank = position
        entries.append(
            ScoreboardEntry(
                rank=current_rank,
                team_id=row.team_id,
                team_name=row.team_name,
                points=points,
                solves=int(row.solves),
                last_solved_at=row.last_solved_at,
            )
        )
        previous_points = points

    return ScoreboardPublic(competition_id=competition_id, entries=entries)
