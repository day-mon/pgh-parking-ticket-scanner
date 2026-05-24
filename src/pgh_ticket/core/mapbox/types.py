"""Pydantic models for the Mapbox Geocoding V6 API."""

from pydantic import BaseModel


class GeocodeBatchItem(BaseModel):
    """A single geocoding query in a batch request body."""

    q: str
    country: list[str]
    bbox: list[float]
    limit: int = 1


class Geometry(BaseModel):
    """GeoJSON geometry coordinates ``[lng, lat]``."""

    coordinates: list[float] = [0.0, 0.0]


class GeocodeProperties(BaseModel):
    """Properties from a Mapbox V6 geocoding feature."""

    name: str = ""
    place_formatted: str = ""
    full_address: str = ""


class GeocodeFeature(BaseModel):
    """A single feature in a geocoding response."""

    geometry: Geometry | None = None
    properties: GeocodeProperties | None = None


class GeocodeBatchEntry(BaseModel):
    """One entry in the batch response array."""

    features: list[GeocodeFeature] = []


class GeocodeBatchResponse(BaseModel):
    """Top-level response from the V6 batch geocoding endpoint."""

    batch: list[GeocodeBatchEntry] = []


class GeocodeResult(BaseModel):
    """Cleaned geocoding result returned to callers."""

    address: str
    latitude: float
    longitude: float
