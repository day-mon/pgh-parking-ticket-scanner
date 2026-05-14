"""Cyclopts validators for pgh-ticket CLI."""

from __future__ import annotations


def number_range(type_: type, value: str) -> None:
    """Validate 'LO-HI' ticket number range format."""
    parts = value.split("-")
    if len(parts) != 2:
        raise ValueError(f"must be 'LO-HI' format, got '{value}'")
    try:
        lo, hi = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"both sides must be integers, got '{value}'")
    if lo > hi:
        raise ValueError(f"start must be <= end, got {lo} > {hi}")
