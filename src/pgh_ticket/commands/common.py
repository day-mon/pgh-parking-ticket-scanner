"""Shared CLI parameters and helpers."""

from dataclasses import dataclass

from cyclopts import Parameter


def status(found: int = 0, stored: int = 0, errs: int = 0) -> str:
    """Build a rich-formatted status string for progress bars."""
    parts = [f"[green]{found}[/] in range", f"[dim]{stored}[/] stored"]
    if errs:
        parts.append(f"[red]{errs}[/] errs")
    return " • ".join(parts)


@Parameter(name="*")
@dataclass
class CommonParams:
    """Parameters shared across most commands -- flattened so --proxy not --common.proxy."""

    verbose: bool = False
    proxy: str | None = None
