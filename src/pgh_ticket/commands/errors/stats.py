"""errors stats -- show error log statistics."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.core.fmt import console
from pgh_ticket.repos import ErrorLogRepo


async def stats(
    *,
    session: Annotated[AsyncSession, Parameter(parse=False)],
) -> None:
    """Show error log statistics."""

    repo = ErrorLogRepo(session)
    data = await repo.stats()

    console.print(f"total errors: {data['total']}")
    console.print(f"unresolved: {data['unresolved']}")

    if data["by_type"]:
        console.print("\nby type:")
        for error_type, count in data["by_type"].items():
            console.print(f"  {error_type}: {count}")
