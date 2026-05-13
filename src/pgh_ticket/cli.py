"""pgh-ticket — Pittsburgh parking ticket scanner."""

from cyclopts import App

from pgh_ticket.commands import backfill, list as list_cmd, lookup, scan, stats, sync

app = App(
    help="Pittsburgh parking ticket scanner",
    help_prologue="An async scanner for the Pittsburgh Parking Authority portal.",
    help_epilogue="Data stored in ~/.local/share/pgh-ticket/tickets.db",
    group_arguments=None,
)

app.command(lookup.run, name="lookup")
app.command(scan.run, name="scan")
app.command(sync.run, name="sync")
app.command(list_cmd.run, name="list")
app.command(stats.run, name="stats")
app.command(backfill.run, name="backfill")

if __name__ == "__main__":
    app()
