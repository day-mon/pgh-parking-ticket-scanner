"""Async HTTP client for the Mapbox Geocoding V6 API."""

from __future__ import annotations

from typing import Any, ClassVar, TypedDict, TypeVar, Unpack

import aiohttp
from pydantic import BaseModel

from pgh_ticket.core.mapbox.types import (
    GeocodeBatchItem,
    GeocodeBatchResponse,
    GeocodeResult,
)

T = TypeVar("T", bound=BaseModel)


class _RequestOptions(TypedDict, total=False):
    """Optional HTTP request parameters passed to _request()."""

    params: dict[str, str]
    json: Any
    headers: dict[str, str]


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

    async def _request(
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
    ) -> list[GeocodeResult | None]:
        """Geocode location strings using the V6 batch API.

        Returns one ``GeocodeResult`` or ``None`` per input location.
        Locations are sent in batches of up to ``batch_size`` (max 1000).
        """
        results: list[GeocodeResult | None] = []
        for i in range(0, len(locations), batch_size):
            batch = locations[i : i + batch_size]
            batch_results = await self.geocode_batch(batch)
            results.extend(batch_results)
        return results

    async def geocode_batch(self, locations: list[str]) -> list[GeocodeResult | None]:
        """Geocode a single batch of locations (max 1000)."""
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

        results: list[GeocodeResult | None] = []
        for entry in resp.batch:
            if not entry.features:
                results.append(None)
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

            results.append(GeocodeResult(address=address, latitude=lat, longitude=lng))
        return results
