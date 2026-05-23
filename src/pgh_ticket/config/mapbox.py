"""Mapbox settings."""

from __future__ import annotations

from pydantic import Field

from pgh_ticket.config.base import BaseConfig


class MapboxSettings(BaseConfig):
    mapbox_token: str | None = Field(default=None, description="Mapbox access token for geocoding")


settings = MapboxSettings()
