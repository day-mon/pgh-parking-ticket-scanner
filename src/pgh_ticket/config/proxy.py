"""Proxy settings."""

from __future__ import annotations

from pydantic import Field

from pgh_ticket.config.base import BaseConfig


class ProxySettings(BaseConfig):
    proxy: str | None = Field(default=None, description="SOCKS5 proxy URL")


settings = ProxySettings()
