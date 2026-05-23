"""backfill sub-app -- enrich tickets with missing data."""

from __future__ import annotations

from cyclopts import App

from pgh_ticket.commands.backfill.details import details
from pgh_ticket.commands.backfill.geocode import geocode
from pgh_ticket.commands.backfill.keys import keys

backfill_app = App(
    name="backfill",
    help="Enrich tickets with missing data",
    help_prologue="Examples:\n  pgh-ticket backfill details -w 40 --proxy socks5://...\n  pgh-ticket backfill keys -w 10 --limit 1000\n  pgh-ticket backfill geocode -w 5",
)
backfill_app.command(keys, name="keys")
backfill_app.command(details, name="details")
backfill_app.command(geocode, name="geocode")
