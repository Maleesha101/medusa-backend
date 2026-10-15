"""Request and response schemas for challenge authoring and catalog."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChallengeDifficulty = Literal["easy", "medium", "hard", "expert"]
ChallengeStatus = Literal["draft", "published", "archived"]


class ChallengeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1, max_length=10000)
    category: str = Field(min_length=2, max_length=60)
    points: int = Field(default=100, gt=0, le=10000)
    difficulty: ChallengeDifficulty = "medium"


class ChallengeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    slug: str | None = Field(
        default=None, min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    category: str | None = Field(default=None, min_length=2, max_length=60)
    points: int | None = Field(default=None, gt=0, le=10000)
    difficulty: ChallengeDifficulty | None = None


class ChallengeStatusUpdate(BaseModel):
    status: ChallengeStatus


class ChallengePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    round_id: int
    name: str
    slug: str
    description: str
    category: str
    points: int
    difficulty: ChallengeDifficulty
    status: ChallengeStatus
    created_at: datetime
    updated_at: datetime
