"""General utility helpers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


async def batch_flush(
    batch: list[Any],
    flush_fn: Callable[[list[Any]], Awaitable[int]],
    batch_size: int,
) -> int:
    """Flush ``batch`` in chunks of ``batch_size`` via ``flush_fn``.

    Returns the number of items flushed.
    """
    total = 0
    while len(batch) >= batch_size:
        chunk = batch[:batch_size]
        del batch[:batch_size]
        total += await flush_fn(chunk)
    return total


def resolve_proxy(proxy: str | None) -> list[str]:
    """Parse comma-separated proxy string into a list of proxy URLs.

    Accepts a single proxy URL or comma-separated list.
    Returns an empty list if ``proxy`` is ``None`` or empty.
    """
    if not proxy:
        return []
    return [p.strip() for p in proxy.split(",") if p.strip()]
