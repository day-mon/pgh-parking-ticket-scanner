"""/stats -- aggregate summaries of all tickets in the database."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.table import Table
from rich.text import Text
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.commands.base import BaseCommand
from pgh_ticket.models import Scan, Ticket

console = Console()


class StatsCommand(BaseCommand):
    """Show aggregate ticket statistics (by status, by state, recent scans)."""

    async def __call__(
        self,
        *,
        session: Annotated[AsyncSession, Parameter(parse=False)] = None,  # type: ignore[assignment]
    ) -> None:
        # Total count
        total = (await session.execute(select(func.count(Ticket.ticket_number)))).scalar_one() or 0

        if total == 0:
            console.print("[yellow]no tickets in database.[/]")
            return

        # Date range
        first_date, last_date = (
            await session.execute(
                select(func.min(Ticket.issue_date), func.max(Ticket.issue_date))
            )
        ).one()

        # By status
        by_status = {
            r[0] or "": r[1]
            for r in (
                await session.execute(
                    select(Ticket.status, func.count(Ticket.ticket_number))
                    .group_by(Ticket.status)
                    .order_by(func.count(Ticket.ticket_number).desc())
                )
            ).all()
        }

        # By state
        by_state = {
            r[0] or "": r[1]
            for r in (
                await session.execute(
                    select(Ticket.state, func.count(Ticket.ticket_number))
                    .group_by(Ticket.state)
                    .order_by(func.count(Ticket.ticket_number).desc())
                )
            ).all()
        }

        # Open by state
        open_by_state = {
            r[0] or "": r[1]
            for r in (
                await session.execute(
                    select(Ticket.state, func.count(Ticket.ticket_number))
                    .where(func.lower(Ticket.status) == "open")
                    .group_by(Ticket.state)
                    .order_by(func.count(Ticket.ticket_number).desc())
                )
            ).all()
        }

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

        # By status table
        status_table = Table(title="by status", title_style="bold")
        status_table.add_column("status", style="cyan")
        status_table.add_column("count", justify="right")
        status_table.add_column("%", justify="right")
        for label, n in by_status.items():
            status_table.add_row(label, str(n), f"{100 * n / total:5.1f}%")
        console.print(status_table)
        console.print()

        # By state table
        state_table = Table(title="by state", title_style="bold")
        state_table.add_column("state", style="cyan")
        state_table.add_column("count", justify="right")
        state_table.add_column("%", justify="right")
        for label, n in list(by_state.items())[:10]:
            state_table.add_row(label, str(n), f"{100 * n / total:5.1f}%")
        console.print(state_table)

        # Open by state
        if open_by_state:
            open_total = sum(open_by_state.values())
            console.print()
            open_table = Table(title=f"open by state ({open_total} total)", title_style="bold")
            open_table.add_column("state", style="cyan")
            open_table.add_column("count", justify="right")
            open_table.add_column("%", justify="right")
            for label, n in list(open_by_state.items())[:10]:
                open_table.add_row(label, str(n), f"{100 * n / open_total:5.1f}%")
            console.print(open_table)

        # Recent scans
        scans = (
            await session.execute(
                select(Scan).order_by(Scan.scanned_at.desc()).limit(10)
            )
        ).scalars().all()
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


stats_cmd = StatsCommand()
