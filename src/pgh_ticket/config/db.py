"""Database settings."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir
from pydantic import Field

from pgh_ticket.config.base import BaseConfig

_DB_DIR = Path(user_data_dir("pgh-ticket", ensure_exists=True))


class DBSettings(BaseConfig):
    db_path: str = Field(default=str(_DB_DIR / "tickets.db"), description="SQLite database path")

    @property
    def db_path_obj(self) -> Path:
        return Path(self.db_path)


settings = DBSettings()
