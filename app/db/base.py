"""SQLAlchemy declarative base and model registration."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for persisted models."""
