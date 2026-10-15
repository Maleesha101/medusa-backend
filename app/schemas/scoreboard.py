"""Response schemas for competition scoreboards."""

from datetime import datetime

from pydantic import BaseModel


class ScoreboardEntry(BaseModel):
    """Public score and solve summary for a team."""

    rank: int
    team_id: int
    team_name: str
    points: int
    solves: int
    last_solved_at: datetime | None


class ScoreboardPublic(BaseModel):
    """Public standings for one competition."""

    competition_id: int
    entries: list[ScoreboardEntry]
