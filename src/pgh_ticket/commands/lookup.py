"""lookup -- one-off ticket lookups by number (or range)."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from cyclopts import validators as cyclopts_validators

from pgh_ticket.core import Database, TicketView, expand_range, make_progress, resource_map
from pgh_ticket.core.client import ClientPool, PortalClient
from pgh_ticket.core.fmt import console
from pgh_ticket.core.utils import resolve_proxy
from pgh_ticket.repos import ErrorLogRepo, TicketRepo


def _require_at_least_one(value, _):
    if not value:
        raise ValueError("at least one ticket number required")


async def _fetch_one(client: PortalClient, n: str) -> TicketView | None:
    results = await client.lookup(n)
    for r in results:
        return r.to_view()
    return None


async def lookup(
    *tickets: Annotated[str, Parameter(validator=_require_at_least_one)],
    workers: Annotated[
        int,
        Parameter(
            ("-j", "--workers"),
            help="number of concurrent requests",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 10,
    verbose: bool = False,
    proxy: list[str] | None = None,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Look up tickets by number (or range) and store in the database."""

    expanded: list[str] = []
    for t in tickets:
        expanded.extend(expand_range(t))

    proxies = resolve_proxy(proxy)
    proxy_list: list[str] = []
    if isinstance(proxies, list):
        proxy_list = proxies
    elif isinstance(proxies, str):
        proxy_list = [proxies]

    progress = make_progress()
    task = progress.add_task("looking up", total=len(expanded), status="starting...")

    buffer: list[TicketView] = []
    seen: set[str] = set()

    async with ClientPool(proxy_list, workers) as pool:
        with progress:
            clients = [pool.acquire() for _ in range(workers)]
            results, failed = await resource_map(
                expanded,
                clients,
                _fetch_one,
                progress=progress,
                task_id=task,
            )

            for tv in results:
                if tv is None or tv.number in seen:
                    continue
                seen.add(tv.number)
                buffer.append(tv)
                if len(buffer) >= 50:
                    async with db.session() as session:
                        data = [tv.to_model_dict() for tv in buffer[:50]]
                        await TicketRepo(session).bulk_upsert(data)
                    for tv in buffer[:50]:
                        print(tv.verbose_str() if verbose else str(tv))
                    buffer = buffer[50:]

            for n in failed:
                async with db.session() as session:
                    await ErrorLogRepo(session).log(
                        number=n, command="lookup", exc=Exception("lookup failed")
                    )

    if buffer:
        async with db.session() as session:
            data = [tv.to_model_dict() for tv in buffer]
            await TicketRepo(session).bulk_upsert(data)
        for tv in buffer:
            print(tv.verbose_str() if verbose else str(tv))

    if not buffer and not results:
        console.print("no tickets found.")
