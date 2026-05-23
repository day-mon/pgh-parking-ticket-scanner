"""Portal settings."""

from __future__ import annotations

from pydantic import Field

from pgh_ticket.config.base import BaseConfig


class PortalSettings(BaseConfig):
    portal_base: str = Field(
        default="https://www.dsparkingportal.com",
        description="Parking portal base URL",
    )
    lo: int = Field(default=2_078_060, description="Lowest ticket number")
    hi: int = Field(default=9_262_307, description="Highest ticket number")


settings = PortalSettings()
