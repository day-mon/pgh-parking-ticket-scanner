"""Database settings."""

from __future__ import annotations

from pydantic import Field

from pgh_ticket.config.base import BaseConfig


class DBSettings(BaseConfig):
    database_url: str = Field(
        default="postgresql+asyncpg://pgh_ticket:pgh_ticket@localhost:5432/pgh_ticket",
        description="PostgreSQL connection string",
    )


settings = DBSettings()
