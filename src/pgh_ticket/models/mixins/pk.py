"""Mixin for auto-increment integer primary key."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column


class PKMixin:
    """Adds an ``id`` column as auto-increment primary key."""

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
