"""Application settings — workers, steps, backoff, ticket range."""

from __future__ import annotations

from pydantic import Field

from pgh_ticket.config.base import BaseConfig


class AppSettings(BaseConfig):
    # Ticket number range
    lo: int = Field(default=2_078_060, description="Lowest possible ticket number")
    hi: int = Field(default=9_262_307, description="Highest possible ticket number")

    # Concurrency
    workers: int = Field(default=20, ge=1, le=100, description="Default worker count for scans")
    sync_workers: int = Field(default=3, ge=1, le=50, description="Worker count for sync (slower, no proxy)")

    # Step sizes
    scan_step: int = Field(default=50, ge=1, description="Probe interval for scan phase 1")
    sync_step: int = Field(default=100, ge=1, description="Probe interval for sync")
    frontier_step: int = Field(default=500, ge=1, description="Step for frontier/expansion scans")

    # Backoff
    backoff_short: int = Field(default=30, ge=0, description="Short backoff seconds (circuit breaker)")
    backoff_long: int = Field(default=180, ge=0, description="Long backoff seconds (circuit breaker)")


settings = AppSettings()
