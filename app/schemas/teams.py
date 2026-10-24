"""Request and response schemas for teams and memberships."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class MemberPublic(BaseModel):
    user_id: int
    role: str
    joined_at: datetime


class TeamPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    captain_user_id: int
    created_at: datetime


class TeamDetail(TeamPublic):
    members: list[MemberPublic]
