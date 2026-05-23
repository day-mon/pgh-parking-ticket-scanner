"""stats -- aggregate summaries of all tickets in the database."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.table import Table
from rich.text import Text
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.core.fmt import console
from pgh_ticket.repos import ScanRepo, TicketRepo


async def stats(
    *,
    session: Annotated[AsyncSession, Parameter(parse=False)],
) -> None:
    """Show aggregate ticket statistics."""

    ticket_repo = TicketRepo(session)
    total = await ticket_repo.count()

    if total == 0:
        console.print("[yellow]no tickets in database.[/]")
        return

    first_date, last_date = await ticket_repo.date_range()
    by_status = await ticket_repo.by_status()
    by_state = await ticket_repo.by_state()
    open_by_state = await ticket_repo.open_by_state()

    # Overview
    overview = Table.grid(padding=(0, 4))
    overview.add_row(
        Text("total tickets:", style="bold"),
        str(total),
        Text("date range:", style="bold"),
        f"{first_date or ''} to {last_date or ''}",
    )
    console.print(overview)
    console.print()

    # By status
    status_table = Table(title="by status", title_style="bold")
    status_table.add_column("status", style="cyan")
    status_table.add_column("count", justify="right")
    status_table.add_column("%", justify="right")
    for label, n in by_status:
        status_table.add_row(label or "", str(n), f"{100 * n / total:5.1f}%")
    console.print(status_table)
    console.print()

    # By state
    state_table = Table(title="by state", title_style="bold")
    state_table.add_column("state", style="cyan")
    state_table.add_column("count", justify="right")
    state_table.add_column("%", justify="right")
    for label, n in by_state[:10]:
        state_table.add_row(label or "", str(n), f"{100 * n / total:5.1f}%")
    console.print(state_table)

    # Open by state
    if open_by_state:
        open_total = sum(n for _, n in open_by_state)
        console.print()
        open_table = Table(title=f"open by state ({open_total} total)", title_style="bold")
        open_table.add_column("state", style="cyan")
        open_table.add_column("count", justify="right")
        open_table.add_column("%", justify="right")
        for label, n in open_by_state[:10]:
            open_table.add_row(label or "", str(n), f"{100 * n / open_total:5.1f}%")
        console.print(open_table)

    # Recent scans
    scan_repo = ScanRepo(session)
    scans = await scan_repo.recent(limit=10)
    if scans:
        console.print()
        scan_table = Table(title="recent scans", title_style="bold")
        scan_table.add_column("when", style="dim")
        scan_table.add_column("range")
        scan_table.add_column("until")
        scan_table.add_column("tickets", justify="right")
        scan_table.add_column("duration", justify="right")
        for sc in scans:
            scan_table.add_row(
                sc.scanned_at[:19],
                f"{sc.range_start:,}-{sc.range_end:,}",
                sc.until_date,
                str(sc.tickets_found),
                f"{sc.duration_s:.1f}s",
            )
        console.print(scan_table)
