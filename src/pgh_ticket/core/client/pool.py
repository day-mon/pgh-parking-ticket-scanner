"""Client pool for concurrent workers with isolated sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from pgh_ticket.core.client.client import PortalClient


class ClientPool:
    """Pool of independent PortalClient instances, each with its own proxy + session."""

    def __init__(self, proxies: list[str] | None, max_clients: int) -> None:
        self._proxies = proxies or []
        self._max_clients = max_clients
        self._clients: list[PortalClient] = []
        self._index = 0

    async def __aenter__(self) -> ClientPool:
        # create all clients in parallel — each primes its own session
        self._clients = await asyncio.gather(*[
            PortalClient(proxy=self._proxies or None).__aenter__()
            for _ in range(self._max_clients)
        ])
        return self

    async def __aexit__(self, *args: Any) -> None:
        await asyncio.gather(*[
            client.__aexit__(*args) for client in self._clients
        ], return_exceptions=True)
        self._clients.clear()

    def acquire(self) -> PortalClient:
        """Round-robin client selection."""
        client = self._clients[self._index % len(self._clients)]
        self._index += 1
        return client
