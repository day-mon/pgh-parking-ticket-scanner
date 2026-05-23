"""Configuration — split by domain.

All values can be overridden via environment variables with the PGH_ prefix:
    PGH_DB_PATH=/tmp/tickets.db
    PGH_WORKERS=50
    PGH_PROXY=socks5://10.64.0.1:1080

Import specific domains:
    from pgh_ticket.config import db
    db.settings.db_path

    from pgh_ticket.config.app import settings
    settings.workers
"""

from __future__ import annotations

from pgh_ticket.config import app, db, mapbox, portal, proxy
from pgh_ticket.config.app import AppSettings
from pgh_ticket.config.base import BaseConfig
from pgh_ticket.config.db import DBSettings
from pgh_ticket.config.mapbox import MapboxSettings
from pgh_ticket.config.portal import PortalSettings
from pgh_ticket.config.proxy import ProxySettings

__all__ = [
    "AppSettings",
    "BaseConfig",
    "DBSettings",
    "MapboxSettings",
    "PortalSettings",
    "ProxySettings",
    "app",
    "db",
    "mapbox",
    "portal",
    "proxy",
]
