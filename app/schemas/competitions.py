"""Request and response schemas for competitions and rounds."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CompetitionStatus = Literal["draft", "published", "active", "completed", "archived"]


class CompetitionCreate(BaseModel):
    organization_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = Field(default=None, max_length=5000)
    is_public: bool = False
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        pairs = (
            (self.registration_opens_at, self.registration_closes_at),
            (self.starts_at, self.ends_at),
        )
        for start, end in pairs:
            if start is not None and end is not None and start >= end:
                raise ValueError("Schedule start must be earlier than end")
        return self


class CompetitionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    created_by_user_id: int
    name: str
    slug: str
    description: str | None
    status: CompetitionStatus
    is_public: bool
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime


class CompetitionStatusUpdate(BaseModel):
    status: CompetitionStatus


class RoundCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    position: int = Field(ge=1)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.starts_at >= self.ends_at
        ):
            raise ValueError("Round start must be earlier than end")
        return self


class RoundPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    competition_id: int
    name: str
    slug: str
    position: int
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime
