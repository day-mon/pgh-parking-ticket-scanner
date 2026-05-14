"""Timestamp mixins for created_at / updated_at columns."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Mapped, mapped_column


class CreatedAtMixin:
    """Adds a ``created_at`` column (ISO format, UTC)."""

    created_at: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
    )


class UpdatedAtMixin:
    """Adds an ``updated_at`` column that auto-updates on every flush."""

    updated_at: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
        onupdate=lambda: datetime.now(UTC).isoformat(),
    )
