"""Error log model — tracks API failures for retry and debugging."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Index, select
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"
    __table_args__ = (
        Index("idx_errors_resolved", "resolved"),
        Index("idx_errors_command", "command"),
        Index("idx_errors_number", "number"),
        Index("idx_errors_type", "error_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column()
    command: Mapped[str] = mapped_column(default="")
    error_type: Mapped[str] = mapped_column(default="")
    message: Mapped[str] = mapped_column(default="")
    retries: Mapped[int] = mapped_column(default=0)
    resolved: Mapped[bool] = mapped_column(default=False)
    first_seen: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
    )
    last_seen: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
    )

    @classmethod
    async def log(
        cls,
        session,
        *,
        number: str,
        command: str,
        exc: Exception,
    ) -> "ErrorLog":
        """Record an API error. Updates existing unresolved entry if one matches."""
        error_type = type(exc).__name__
        message = str(exc)[:500]
        now = datetime.now(UTC).isoformat()

        stmt = select(cls).where(
            cls.number == number,
            cls.command == command,
            cls.error_type == error_type,
            cls.resolved.is_(False),
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.last_seen = now
            existing.retries += 1
            await session.commit()
            return existing

        obj = cls(
            number=number,
            command=command,
            error_type=error_type,
            message=message,
            last_seen=now,
        )
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj
