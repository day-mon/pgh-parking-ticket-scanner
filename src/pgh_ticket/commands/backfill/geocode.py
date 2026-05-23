"""geocode -- geocode ticket locations using Mapbox."""

from __future__ import annotations

import os
import time
from typing import Annotated

from cyclopts import Parameter
from cyclopts import validators as cyclopts_validators

from pgh_ticket.core import Database, make_progress, resource_map
from pgh_ticket.core.fmt import console
from pgh_ticket.core.utils import batch_flush
from pgh_ticket.repos import LocationRepo, TicketRepo


async def _geocode_one(location: str) -> dict | None:
    """Geocode a single location string using Mapbox."""
    if not location or location.lower() in ("unknown", "", "n/a"):
        return None

    try:
        from mapbox import Geocoder

        token = os.environ.get("MAPBOX_ACCESS_TOKEN") or os.environ.get("MAPBOX_TOKEN")
        if not token:
            console.print("[red]mapbox token not found. set MAPBOX_ACCESS_TOKEN or MAPBOX_TOKEN.[/]")
            return None

        geocoder = Geocoder(access_token=token)
        response = geocoder.forward(location + ", Pittsburgh, PA")

        if response.status_code != 200:
            return None

        data = response.json()
        features = data.get("features", [])
        if not features:
            return None

        first = features[0]
        coords = first.get("geometry", {}).get("coordinates", [0, 0])
        return {
            "address": first.get("place_name", ""),
            "longitude": float(coords[0]),
            "latitude": float(coords[1]),
        }
    except Exception:
        return None


async def _fetch_and_geocode(location: str) -> dict | None:
    """Fetch geocode data for a location."""
    result = await _geocode_one(location)
    if not result:
        return None
    return {
        "raw_location": location,
        "address": result["address"],
        "latitude": result["latitude"],
        "longitude": result["longitude"],
        "geocoded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


async def _flush(db: Database, data: list[dict]) -> int:
    async with db.session() as session:
        count = await LocationRepo(session).bulk_upsert(data)
        await session.commit()
        return count


async def geocode(
    workers: Annotated[
        int,
        Parameter(
            ("-j", "--workers"),
            help="max concurrent requests",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 5,
    limit: Annotated[
        int | None,
        Parameter(
            ("-n", "--limit"),
            help="max unique locations to geocode (default: all)",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = None,
    batch_size: Annotated[
        int,
        Parameter(
            ("-b", "--batch-size"),
            help="flush to db after this many (default: 500)",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 500,
    *,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Geocode unique ticket locations using Mapbox and store lat/lon/address."""

    async with db.session() as session:
        all_locations = await TicketRepo(session).get_distinct_locations(limit=limit)
        existing = await LocationRepo(session).get_existing_locations()

    to_geocode = [loc for loc in all_locations if loc not in existing]

    if not to_geocode:
        console.print(f"[green]all {len(all_locations)} unique locations already geocoded.[/]")
        return

    total = len(to_geocode)
    console.print(f"[dim]{len(all_locations)} unique locations, {total} need geocoding[/]")

    t0 = time.monotonic()
    batch: list[dict] = []

    progress = make_progress()
    task = progress.add_task("geocoding", total=total, status="starting...")

    with progress:
        dummy_resources = [None] * workers
        results, failed_items = await resource_map(
            to_geocode,
            dummy_resources,
            lambda _, loc: _fetch_and_geocode(loc),
            progress=progress,
            task_id=task,
        )

        for item in results:
            if item:
                batch.append(item)
                if len(batch) >= batch_size:
                    await batch_flush(batch, lambda data: _flush(db, data), batch_size)

        if batch:
            await _flush(db, batch)

    elapsed = time.monotonic() - t0
    rate = total / elapsed if elapsed > 0 else 0.0
    found = len([r for r in results if r is not None])
    console.print(
        f"\n[bold]{total}/{total}"
        f" — {found} geocoded, {len(failed_items)} failed"
        f" ({rate:.1f}/s)[/]"
    )

    if failed_items:
        console.print(f"[red]failed ({len(failed_items)}):[/] {', '.join(failed_items[:20])}")
        if len(failed_items) > 20:
            console.print(f"[dim]... and {len(failed_items) - 20} more[/]")
