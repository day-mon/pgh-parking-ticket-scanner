"""geocode -- geocode ticket locations using Mapbox V6 batch API."""

from __future__ import annotations

import os
import time
from typing import Annotated

from aiohttp import ClientResponseError
from cyclopts import Parameter

from pgh_ticket.core import Database, make_progress
from pgh_ticket.core.fmt import console
from pgh_ticket.core.mapbox import MapboxClient
from pgh_ticket.core.utils import batch_flush
from pgh_ticket.repos import LocationRepo, TicketRepo

# Mapbox allows up to 1000 queries per batch request
_BATCH_SIZE = 1000


async def _flush(db: Database, data: list[dict]) -> int:
    async with db.session() as session:
        count = await LocationRepo(session).bulk_upsert(data)
        await session.commit()
        return count


async def geocode(
    limit: Annotated[
        int | None,
        Parameter(
            ("--limit",),
            help="max unique locations to geocode (default: all)",
        ),
    ] = None,
    batch_size: Annotated[
        int,
        Parameter(
            ("-b", "--batch-size"),
            help="flush to db after this many (default: 500)",
        ),
    ] = 500,
    *,
    dry_run: Annotated[
        bool,
        Parameter(("-n", "--dry-run"), help="show what would be geocoded without writing to DB"),
    ] = False,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Geocode unique ticket locations using Mapbox and store lat/lon/address.

    Uses the Mapbox Geocoding V6 batch API (up to 1000 queries per request).

    Examples:
      pgh-ticket backfill geocode
      pgh-ticket backfill geocode --limit 100
      pgh-ticket backfill geocode --dry-run
    """

    async with db.session() as session:
        all_locations = await TicketRepo(session).get_distinct_locations(limit=limit)
        existing = await LocationRepo(session).get_existing_locations()

    to_geocode = [loc for loc in all_locations if loc not in existing]

    if not to_geocode:
        console.print(f"[green]all {len(all_locations)} unique locations already geocoded.[/]")
        return

    total = len(to_geocode)
    console.print(f"[dim]{len(all_locations)} unique locations, {total} need geocoding[/]")

    token = os.environ.get("MAPBOX_ACCESS_TOKEN") or os.environ.get("MAPBOX_TOKEN")
    if not token:
        console.print("[red]mapbox token not found. set MAPBOX_ACCESS_TOKEN or MAPBOX_TOKEN.[/]")
        return

    t0 = time.monotonic()
    flush_batch: list[dict] = []

    progress = make_progress()
    task = progress.add_task("geocoding", total=total, status="starting...")

    with progress:
        async with MapboxClient(token) as client:
            for i in range(0, total, _BATCH_SIZE):
                chunk = to_geocode[i : i + _BATCH_SIZE]
                try:
                    chunk_results = await client.geocode_batch(chunk)
                except ClientResponseError as exc:
                    console.print(f"\n[red]batch failed at idx {i}: {exc}[/]")
                    continue

                for loc, result in chunk_results:
                    flush_batch.append(
                        {
                            "raw_location": loc,
                            "address": result.address,
                            "latitude": result.latitude,
                            "longitude": result.longitude,
                            "geocoded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        }
                    )
                    if len(flush_batch) >= batch_size and not dry_run:
                        await batch_flush(
                            flush_batch, lambda data: _flush(db, data), batch_size
                        )
                progress.update(task, advance=len(chunk))

    if flush_batch and not dry_run:
        await _flush(db, flush_batch)

    elapsed = time.monotonic() - t0
    rate = total / elapsed if elapsed > 0 else 0.0
    found = len(flush_batch)
    tag = " [yellow](dry run)[/]" if dry_run else ""
    console.print(
        f"\n[bold]{total}/{total}"
        f" — {found} geocoded, {total - found} failed"
        f" ({rate:.1f}/s){tag}[/]"
    )
