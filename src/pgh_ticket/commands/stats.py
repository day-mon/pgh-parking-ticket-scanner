from __future__ import annotations

import sys
from typing import Annotated

from cyclopts import Parameter

from pgh_ticket.db import Database


async def run(
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database", show=False),
    ] = None,
) -> None:
    db = Database(db_path)
    db.init()
    s = db.get_summary()

    if s.get("total", 0) == 0:
        print("no tickets in database.", file=sys.stderr)
        return

    dr = s["date_range"]
    print(f"total tickets: {s['total']}")
    print(f"date range:    {dr['first']} to {dr['last']}")
    print()

    print("by status:")
    for label, n in s["by_status"].items():
        print(f"  {label:<25s}  {n:>5d}  ({100 * n / s['total']:5.1f}%)")

    print()
    print("by state (top 10):")
    for label, n in list(s["by_state"].items())[:10]:
        print(f"  {label:<4s}  {n:>5d}  ({100 * n / s['total']:5.1f}%)")

    if s.get("open_by_state"):
        open_total = sum(s["open_by_state"].values())
        print()
        print(f"open by state (top 10, {open_total} total):")
        for label, n in list(s["open_by_state"].items())[:10]:
            print(f"  {label:<4s}  {n:>5d}  ({100 * n / open_total:5.1f}%)")

    scans = db.recent_scans()
    if scans:
        print()
        print("recent scans:")
        for sc in scans:
            print(
                f"  {sc['scanned_at'][:19]}  "
                f"{sc['range_start']:,}-{sc['range_end']:,}  "
                f"until {sc['until_date']}  "
                f"{sc['tickets_found']} tickets  "
                f"{sc.get('duration_s', 0):.1f}s"
            )
