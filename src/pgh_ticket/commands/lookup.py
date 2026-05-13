from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Annotated

from cyclopts import Parameter

from pgh_ticket.client import Client
from pgh_ticket.db import Database
from pgh_ticket.utils import TicketData, expand_range, parse_date, print_summary


async def run(
    *tickets: str,
    verbose: Annotated[
        bool,
        Parameter(("-v", "--verbose"), help="show full ticket details"),
    ] = False,
    proxy: Annotated[
        str | None,
        Parameter(("--proxy",), help="socks5 proxy (e.g. socks5://10.64.0.1:1080)"),
    ] = None,
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database", show=False),
    ] = None,
) -> None:
    if not tickets:
        print("error: at least one ticket number required", file=sys.stderr)
        sys.exit(1)

    expanded: list[str] = []
    for t in tickets:
        expanded.extend(expand_range(t))

    db = Database(db_path)
    db.init()

    async with Client(proxy=proxy) as cl:
        for issue in expanded:
            try:
                results = await cl.lookup(issue)
            except Exception as e:
                print(f"[{issue}] error: {e}", file=sys.stderr)
                continue

            for r in results:
                td = TicketData.from_api(r)
                db.upsert_ticket(td)
                print(td.verbose_str() if verbose else str(td))
