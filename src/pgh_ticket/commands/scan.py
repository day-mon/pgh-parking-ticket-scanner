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
    number_range: str,
    *,
    until: Annotated[
        str,
        Parameter(("-u", "--until"), help="upper date bound (YYYY-MM-DD)"),
    ],
    proxy: Annotated[
        str | None,
        Parameter(("--proxy",), help="socks5 proxy (e.g. socks5://10.64.0.1:1080)"),
    ] = None,
    workers: Annotated[
        int,
        Parameter(("-j", "--workers"), help="number of concurrent requests"),
    ] = 20,
    step: Annotated[
        int,
        Parameter(("--step",), help="probe interval between numbers"),
    ] = 50,
    output: Annotated[
        str | None,
        Parameter(("-o", "--output"), help="save results to json file"),
    ] = None,
    summary: Annotated[
        bool,
        Parameter(("--summary",), help="show breakdown by state and status"),
    ] = False,
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database", show=False),
    ] = None,
) -> None:
    target = datetime.strptime(until, "%Y-%m-%d").date()
    parts = number_range.split("-")
    if len(parts) != 2:
        print(f"error: bad range '{number_range}'", file=sys.stderr)
        sys.exit(1)

    lo, hi = int(parts[0]), int(parts[1])

    print(f"range: {lo:,} to {hi:,} ({(hi - lo + 1):,} numbers)", file=sys.stderr)
    print(f"until: {target} | step: {step} | workers: {workers}", file=sys.stderr)
    if proxy:
        print(f"proxy: {proxy}", file=sys.stderr)
    print(file=sys.stderr)

    lock = asyncio.Lock()
    hits: list[int] = []
    found: list[TicketData] = []
    seen: set[str] = set()
    errs = 0
    t0 = time.monotonic()

    db = Database(db_path)
    db.init()

    async with Client(proxy=proxy) as cl:
        async def fetch_raw(n: int) -> list[dict]:
            nonlocal errs
            try:
                return await cl.search(str(n))
            except Exception:
                async with lock:
                    errs += 1
                return []

        print("phase 1: probing...", file=sys.stderr)
        coarse = list(range(lo, hi + 1, step))
        total_p1 = len(coarse)
        done_p1 = 0
        sem = asyncio.Semaphore(workers)

        async def probe(n: int) -> None:
            nonlocal done_p1
            async with sem:
                results = await fetch_raw(n)
            async with lock:
                done_p1 += 1
                if results:
                    hits.append(n)

        await asyncio.gather(*[probe(n) for n in coarse], return_exceptions=True)
        print(f"\r  {done_p1}/{total_p1}  {len(hits)} hits, {errs} err    ", file=sys.stderr)
        print(file=sys.stderr)

        if not hits:
            print("no hits in range.", file=sys.stderr)
            return

        print(f"found {len(hits)} clusters, deep-scanning...", file=sys.stderr)

        raw_windows = [(max(lo, h - step // 2), min(hi, h + step // 2)) for h in sorted(hits)]
        raw_windows.sort()
        merged: list[tuple[int, int]] = []
        for a, b in raw_windows:
            if merged and a <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))

        deep_nums: list[int] = []
        for a, b in merged:
            deep_nums.extend(range(a, b + 1))

        total_p2 = len(deep_nums)
        done_p2 = 0

        async def deep_work(n: int) -> None:
            nonlocal done_p2
            async with sem:
                raw = await fetch_raw(n)
            if not raw:
                async with lock:
                    done_p2 += 1
                return

            for r in raw:
                key = r.get("ticket_key")
                if key:
                    try:
                        details = await cl.details(key)
                        if details:
                            r.update(details)
                    except Exception:
                        pass

            async with lock:
                done_p2 += 1
                for r in raw:
                    td = TicketData.from_api(r)
                    db.upsert_ticket(td)
                    d = parse_date(td.issue_date)
                    if d and d <= target and td.number not in seen:
                        seen.add(td.number)
                        found.append(td)
                if done_p2 % max(1, total_p2 // 20) == 0 or done_p2 == total_p2:
                    print(
                        f"\r  {done_p2}/{total_p2}  {len(found)} found, {errs} err    ",
                        end="", file=sys.stderr,
                    )

        await asyncio.gather(*[deep_work(n) for n in deep_nums], return_exceptions=True)

    duration = time.monotonic() - t0
    db.record_scan(lo, hi, until, len(found), errs, duration)
    print(file=sys.stderr)
    print(file=sys.stderr)

    if not found:
        print(f"no tickets found on or before {target}.", file=sys.stderr)
        return

    found.sort(key=lambda t: t.issue_date)
    dates = {parse_date(t.issue_date) for t in found if parse_date(t.issue_date)}
    print(f"found {len(found)} tickets from {min(dates)} to {max(dates)}")
    print()
    print(f"{'number':<12s} {'date':<12s} {'type':<12s} {'plate':<12s} {'st':<4s} {'status':<25s} {'amount':<8s}")
    print("-" * 85)
    for t in found:
        print(t)

    if summary:
        print_summary(found)

    if output:
        with open(output, "w") as f:
            json.dump([t.to_dict() for t in found], f, indent=2)
        print(f"saved {len(found)} tickets to {output}", file=sys.stderr)
