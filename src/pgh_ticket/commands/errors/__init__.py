"""errors sub-app -- view and manage error logs."""

from __future__ import annotations

from cyclopts import App

from pgh_ticket.commands.errors.clear import clear
from pgh_ticket.commands.errors.list import list_
from pgh_ticket.commands.errors.retry import retry
from pgh_ticket.commands.errors.stats import stats

errors_app = App(name="errors", help="View and manage error logs")
errors_app.command(list_, name="list")
errors_app.command(stats, name="stats")
errors_app.command(clear, name="clear")
errors_app.command(retry, name="retry")
