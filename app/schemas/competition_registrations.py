"""Request and response schemas for competition registration."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompetitionRegistrationCreate(BaseModel):
    team_id: int = Field(gt=0)


class CompetitionRegistrationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    team_id: int
    registered_by_user_id: int
    registered_at: datetime
