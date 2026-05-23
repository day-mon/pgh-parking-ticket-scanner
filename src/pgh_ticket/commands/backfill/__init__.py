"""backfill sub-app -- enrich tickets with missing data."""

from __future__ import annotations

from cyclopts import App

from pgh_ticket.commands.backfill.details import details
from pgh_ticket.commands.backfill.geocode import geocode
from pgh_ticket.commands.backfill.keys import keys

backfill_app = App(name="backfill", help="Enrich tickets with missing data")
backfill_app.command(keys, name="keys")
backfill_app.command(details, name="details")
backfill_app.command(geocode, name="geocode")
