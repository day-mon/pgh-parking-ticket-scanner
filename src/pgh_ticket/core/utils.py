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


def resolve_proxy(proxy: list[str] | None) -> str | list[str] | None:
    """Normalize a list of proxy strings into a single proxy or list.

    Splits comma-separated values and returns a single string if only
    one proxy is given, otherwise a list.
    """
    if not proxy:
        return None
    proxies: list[str] = []
    for item in proxy:
        if "," in item:
            proxies.extend(p.strip() for p in item.split(",") if p.strip())
        else:
            proxies.append(item.strip())
    if len(proxies) == 1:
        return proxies[0]
    return proxies
