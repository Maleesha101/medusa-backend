"""Request and response schemas for challenge flags and submissions."""

from datetime import datetime

from pydantic import BaseModel, Field


class ChallengeFlagSet(BaseModel):
    """A flag value accepted only by the private organizer endpoint."""

    flag: str = Field(min_length=8, max_length=512)


class ChallengeSubmissionCreate(BaseModel):
    """A participant's flag attempt for a team."""

    team_id: int = Field(gt=0)
    flag: str = Field(min_length=8, max_length=512)


class ChallengeSubmissionResult(BaseModel):
    """Safe submission result; never echoes the submitted flag."""

    submission_id: int
    challenge_id: int
    correct: bool
    submitted_at: datetime
