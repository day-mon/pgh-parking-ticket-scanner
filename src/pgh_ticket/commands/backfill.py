from __future__ import annotations

import asyncio
import sys
from typing import Annotated

from cyclopts import Parameter

from pgh_ticket.client import Client
from pgh_ticket.db import Database
from pgh_ticket.utils import TicketData


async def run(
    proxy: Annotated[
        str | None,
        Parameter(("--proxy",), help="socks5 proxy (e.g. socks5://10.64.0.1:1080)"),
    ] = None,
    workers: Annotated[
        int,
        Parameter(("-j", "--workers"), help="number of concurrent requests"),
    ] = 5,
    limit: Annotated[
        int | None,
        Parameter(("-n", "--limit"), help="max tickets to backfill (default: all)"),
    ] = None,
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database", show=False),
    ] = None,
) -> None:
    db = Database(db_path)
    db.init()

    unfilled = db.unfilled_tickets(limit=limit)
    if not unfilled:
        print("all tickets are already filled.", file=sys.stderr)
        return

    print(f"backfilling {len(unfilled)} tickets...", file=sys.stderr)

    lock = asyncio.Lock()
    sem = asyncio.Semaphore(workers)
    done = 0
    total = len(unfilled)

    async with Client(proxy=proxy) as cl:
        async def fill(row: dict) -> None:
            nonlocal done
            td = TicketData.from_db(row)
            if not td.number:
                async with lock:
                    done += 1
                return
            async with sem:
                try:
                    results = await cl.search(td.number)
                except Exception:
                    async with lock:
                        done += 1
                    return

            for r in results:
                key = r.get("ticket_key", "")
                if not key:
                    continue
                try:
                    details = await cl.details(key)
                except Exception:
                    continue
                if details:
                    td = TicketData.from_api({**r, **details})
                    db.upsert_ticket(td)

            async with lock:
                done += 1
                if done % 20 == 0 or done == total:
                    print(f"\r  {done}/{total}    ", end="", file=sys.stderr)

        await asyncio.gather(*[fill(r) for r in unfilled], return_exceptions=True)

    print(file=sys.stderr)
    print(f"backfilled {done} tickets", file=sys.stderr)
