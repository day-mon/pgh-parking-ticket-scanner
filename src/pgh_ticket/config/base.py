"""Base settings shared across all config domains."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """All PGH-Ticket settings inherit from this."""

    model_config = SettingsConfigDict(
        env_prefix="PGH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
