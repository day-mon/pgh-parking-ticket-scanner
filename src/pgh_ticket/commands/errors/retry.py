"""errors retry -- retry failed lookups from error logs."""

from __future__ import annotations

import asyncio
from typing import Annotated

from cyclopts import Parameter
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.core import Database
from pgh_ticket.core.fmt import console
from pgh_ticket.core.utils import resolve_proxy
from pgh_ticket.core.client import PortalClient
from pgh_ticket.repos import ErrorLogRepo, TicketRepo


async def retry(
    workers: Annotated[
        int,
        Parameter(("-j", "--workers"), help="number of concurrent workers"),
    ] = 5,
    *,
    proxy: list[str] | None = None,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Retry unresolved errors."""

    async with db.session() as session:
        errors = await ErrorLogRepo(session).list_unresolved()

    if not errors:
        console.print("[green]no unresolved errors to retry.[/]")
        return

    console.print(f"retrying {len(errors)} unresolved errors...")

    sem = asyncio.Semaphore(workers)
    resolved = [0]
    failed = [0]

    async def try_one(err) -> None:
        async with sem:
            try:
                async with PortalClient(proxy=resolve_proxy(proxy)) as client:
                    results = await client.lookup(err.number)
                if results:
                    async with db.session() as session:
                        data = [_to_model_dict(r) for r in results]
                        await TicketRepo(session).bulk_upsert(data)
                        await ErrorLogRepo(session).mark_resolved(
                            err.number, err.command
                        )
                    resolved[0] += 1
                else:
                    failed[0] += 1
            except Exception:
                failed[0] += 1

    await asyncio.gather(*[try_one(err) for err in errors], return_exceptions=True)

    console.print(
        f"[green]{resolved[0]} resolved[/] • [red]{failed[0]} still failing[/]"
    )


def _to_model_dict(result) -> dict[str, object]:
    return {
        "ticket_number": result.number,
        "ticket_key": result.ticket_key,
        "vehicle_make": result.vehicle_make,
        "license_plate": result.license_plate,
        "state": result.state,
        "issue_date": result.issue_date,
        "location": result.location,
        "violation": result.violation,
        "amount_due": result.amount_due,
        "due_date": result.due_date,
        "officer": result.officer,
        "notes": result.notes,
        "status": result.status,
        "ticket_type": result.ticket_type,
    }


