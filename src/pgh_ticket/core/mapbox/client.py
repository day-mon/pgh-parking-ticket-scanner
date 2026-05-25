"""Async HTTP client for the Mapbox Geocoding V6 API."""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Unpack

import aiohttp
import pydantic
from aiohttp.client import _RequestOptions

from pgh_ticket.core.mapbox.types import (
    GeocodeBatchItem,
    GeocodeBatchResponse,
    GeocodeResult,
)


class MapboxClient:
    """Async HTTP client for the Mapbox Geocoding V6 API.

    Usage::

        async with MapboxClient(token) as client:
            results = await client.batch_geocode(["123 Main St", "456 Forbes Ave"])
    """

    BASE_URL: ClassVar[str] = "https://api.mapbox.com"
    BOUND_BOX: ClassVar[list[float]] = [-84.51012, 38.50932, -75.12281, 42.73322]

    def __init__(self, token: str) -> None:
        self._token = token
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                raise_for_status=True,
                base_url=self.BASE_URL,
                headers={"Content-Type": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> MapboxClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _request[T: pydantic.BaseModel](
        self,
        method: str,
        endpoint: str,
        *,
        response_model: type[T],
        **kwargs: Unpack[_RequestOptions],
    ) -> T:
        """Make an HTTP request and validate the response with a Pydantic model."""
        async with self.session.request(method, endpoint, **kwargs) as resp:
            data = await resp.json()
        return response_model.model_validate(data)

    async def batch_geocode(
        self,
        locations: list[str],
        *,
        batch_size: int = 1000,
        max_concurrent: int = 5,
    ) -> list[tuple[str, GeocodeResult]]:
        """Geocode location strings using the V6 batch API.

        Batches are sent in parallel (up to ``max_concurrent`` at a time).

        Returns ``(location, result)`` tuples for matched locations.
        Unmatched locations are silently skipped. Each batch has at most
        ``batch_size`` locations (max 1000).
        """
        batches = [
            locations[i : i + batch_size]
            for i in range(0, len(locations), batch_size)
        ]

        sem = asyncio.Semaphore(max_concurrent)

        async def _run(batch: list[str]) -> list[tuple[str, GeocodeResult]]:
            async with sem:
                return await self.geocode_batch(batch)

        tasks = [_run(b) for b in batches]
        batch_results = await asyncio.gather(*tasks)

        results: list[tuple[str, GeocodeResult]] = []
        for br in batch_results:
            results.extend(br)
        return results

    async def geocode_batch(
        self, locations: list[str]
    ) -> list[tuple[str, GeocodeResult]]:
        """Geocode a single batch of locations (max 1000).

        Returns ``(location, result)`` tuples — one per matched location.
        """
        body = [
            GeocodeBatchItem(
                q=f"{loc}, Pittsburgh, PA",
                country=["us"],
                bbox=self.BOUND_BOX,
            ).model_dump()
            for loc in locations
        ]

        resp = await self._request(
            "POST",
            "/search/geocode/v6/batch",
            response_model=GeocodeBatchResponse,
            params={"access_token": self._token},
            json=body,
        )

        results: list[tuple[str, GeocodeResult]] = []
        for loc, entry in zip(locations, resp.batch):
            if not entry.features:
                continue
            feature = entry.features[0]
            geom = feature.geometry
            props = feature.properties
            coords = geom.coordinates if geom else [0.0, 0.0]
            lng = float(coords[0]) if len(coords) > 0 else 0.0
            lat = float(coords[1]) if len(coords) > 1 else 0.0

            if props and props.full_address:
                address = props.full_address
            elif props and (props.name or props.place_formatted):
                address = f"{props.name}, {props.place_formatted}".strip(", ")
            else:
                address = ""

            results.append(
                (loc, GeocodeResult(address=address, latitude=lat, longitude=lng))
            )
        return results
