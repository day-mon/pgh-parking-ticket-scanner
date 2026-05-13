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
from pgh_ticket.utils import TicketData, parse_date, print_summary


async def run(
    date: Annotated[str, Parameter(help="target date (YYYY-MM-DD)")],
    *,
    proxy: Annotated[
        str | None,
        Parameter(("--proxy",), help="socks5 proxy (e.g. socks5://10.64.0.1:1080)"),
    ] = None,
    workers: Annotated[
        int,
        Parameter(("-j", "--workers"), help="number of concurrent requests"),
    ] = 3,
    step: Annotated[
        int,
        Parameter(("--step",), help="probe interval"),
    ] = 100,
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
    target = datetime.strptime(date, "%Y-%m-%d").date()
    lo, hi = 8_950_000, 9_245_300

    print(f"searching for tickets on {target}", file=sys.stderr)
    print(f"range: {lo:,} to {hi:,} | workers: {workers}", file=sys.stderr)
    if proxy:
        print(f"proxy: {proxy}", file=sys.stderr)
    print(file=sys.stderr)

    lock = asyncio.Lock()
    found: list[TicketData] = []
    seen: set[str] = set()
    errs = 0
    consecutive_errs = 0
    max_consecutive_errs = 25
    t0 = time.monotonic()

    db = Database(db_path)
    db.init()

    async with Client(proxy=proxy) as cl:
        sem = asyncio.Semaphore(workers)

        async def fetch_raw(n: int) -> list[dict]:
            nonlocal errs, consecutive_errs
            try:
                results = await cl.search(str(n))
                async with lock:
                    consecutive_errs = 0
                return results
            except Exception:
                async with lock:
                    errs += 1
                    consecutive_errs += 1
                if consecutive_errs >= 5 and consecutive_errs % 5 == 0:
                    print(f"\n  {consecutive_errs} consecutive errors, sleeping 3min...", file=sys.stderr)
                    await asyncio.sleep(180)
                elif 0 < consecutive_errs % 3 == 0:
                    print(f"\n  {consecutive_errs} consecutive errors, sleeping 30s...", file=sys.stderr)
                    await asyncio.sleep(30)
                return []

        def match_date(raw: list[dict]) -> None:
            for r in raw:
                td = TicketData.from_api(r)
                d = parse_date(td.issue_date)
                if d == target and td.number not in seen:
                    seen.add(td.number)
                    found.append(td)
                    db.upsert_ticket(td)

        coarse = list(range(lo, hi + 1, step))
        total = len(coarse)
        done = 0

        async def probe(n: int) -> None:
            nonlocal done
            async with sem:
                results = await fetch_raw(n)
            async with lock:
                done += 1
                if results:
                    match_date(results)
                if done % 200 == 0 or done == total:
                    print(f"\r  {done}/{total}  {len(found)} found, {errs} err    ", end="", file=sys.stderr)

        print(f"probing every {step}...", file=sys.stderr)
        await asyncio.gather(*[probe(n) for n in coarse], return_exceptions=True)
        print(file=sys.stderr)

        if found:
            print(f"found {len(found)} tickets on {target}, fetching details...", file=sys.stderr)
            sem2 = asyncio.Semaphore(workers)
            done_d = 0
            total_d = len(found)

            async def enrich(t: TicketData) -> None:
                nonlocal done_d, consecutive_errs
                if not t.number or consecutive_errs >= max_consecutive_errs:
                    return
                async with sem2:
                    try:
                        raw = await cl.search(t.number)
                    except Exception:
                        async with lock:
                            consecutive_errs += 1
                        return
                for r in raw:
                    key = r.get("ticket_key", "")
                    if key:
                        try:
                            details = await cl.details(key)
                            if details:
                                t.vehicle_make = details.get("vehicle_make", t.vehicle_make)
                                t.location = details.get("location", t.location)
                                t.violation = details.get("violation", t.violation)
                                t.officer = details.get("officer", t.officer)
                                t.due_date = details.get("due_date", t.due_date)
                                t.notes = details.get("notes", t.notes)
                                db.upsert_ticket(t)
                        except Exception:
                            pass
                async with lock:
                    consecutive_errs = 0
                    done_d += 1
                    if done_d % 30 == 0 or done_d == total_d:
                        print(f"\r  details: {done_d}/{total_d}    ", end="", file=sys.stderr)

            await asyncio.gather(*[enrich(t) for t in found], return_exceptions=True)
            print(file=sys.stderr)

    duration = time.monotonic() - t0
    db.record_scan(lo, hi, date, len(found), errs, duration)
    print(file=sys.stderr)

    if not found:
        print(f"no tickets found on {target}.", file=sys.stderr)
        return

    found.sort(key=lambda t: t.issue_date)
    print(f"found {len(found)} tickets on {target}")
    print()
    print(f"{'number':<12s} {'type':<12s} {'plate':<12s} {'st':<4s} {'status':<25s} {'amount':<8s}")
    print("-" * 85)
    for t in found:
        print(t)

    if summary:
        print_summary(found)

    if output:
        with open(output, "w") as f:
            json.dump([t.to_dict() for t in found], f, indent=2)
        print(f"saved to {output}", file=sys.stderr)
