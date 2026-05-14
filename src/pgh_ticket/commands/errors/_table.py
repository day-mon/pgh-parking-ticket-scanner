"""Shared error log table builder."""

from rich.table import Table

from pgh_ticket.models import ErrorLog


def build_table(rows: list[ErrorLog], limit: int | None = None) -> Table:
    title = f"{len(rows)} error log entries"
    if limit:
        title += f" (last {limit})"
    table = Table(title=title)
    table.add_column("id", style="dim", no_wrap=True)
    table.add_column("number", style="cyan")
    table.add_column("cmd")
    table.add_column("type", style="red")
    table.add_column("msg", max_width=40)
    table.add_column("retries", justify="right")
    table.add_column("resolved", justify="center")
    table.add_column("last_seen", style="dim")
    for r in rows:
        table.add_row(
            str(r.id),
            r.number,
            r.command,
            r.error_type,
            (r.message or "")[:40],
            str(r.retries),
            "✓" if r.resolved else "",
            r.last_seen[:19] if r.last_seen else "",
        )
    return table
