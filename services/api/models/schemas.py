"""
schemas.py — Pydantic models for API request / response validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class ConfigEntry(BaseModel):
    key: str
    value: Any
    updated_at: datetime


class ConfigPatch(BaseModel):
    value: Any


# ---------------------------------------------------------------------------
# Flights
# ---------------------------------------------------------------------------

class FlightSummary(BaseModel):
    session_id: UUID
    hex: str
    callsign: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]
    on_ground: bool
    total_distance_nm: Optional[float]
    departure_airport_icao: Optional[str]
    arrival_airport_icao: Optional[str]


class FlightDetail(FlightSummary):
    """Extends FlightSummary with trajectory GeoJSON."""
    trajectory: Optional[Dict[str, Any]]  # GeoJSON LineString or None


# ---------------------------------------------------------------------------
# Aircraft (live cache)
# ---------------------------------------------------------------------------

class AircraftRecord(BaseModel):
    hex: str
    session_id: Optional[str]
    callsign: Optional[str]
    lat: float
    lon: float
    alt: Optional[int]
    track: Optional[float]
    speed: Optional[int]
    vrate: Optional[int]
    phase: str
    squawk: Optional[str]
    on_ground: bool
    category: Optional[str]
    last_seen: str  # ISO-8601 UTC string


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class StatsResponse(BaseModel):
    active_aircraft: int
    flights_today: int
    flights_in_last_hour: int
    ingest_rate_per_sec: float
    materializer_lag_sec: Optional[float]
    storage_bytes: Optional[int]
    oldest_data_date: Optional[str]  # YYYY-MM-DD


class HourlyStatPoint(BaseModel):
    hour_start: str  # ISO-8601 timestamp
    flight_count: int


class PhaseStatEntry(BaseModel):
    phase: str
    count: int


class TopAircraftEntry(BaseModel):
    hex: str
    callsign: Optional[str]
    flight_count: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    postgres: str
    ultrafeeder: str
    ingest_active: bool
    last_position_report: Optional[str]  # ISO-8601 UTC string


# ---------------------------------------------------------------------------
# Airspace
# ---------------------------------------------------------------------------

class AirspaceBoundary(BaseModel):
    boundary_id: int
    name: str
    icao: Optional[str]
    airspace_class: Optional[str]
    lower_alt_ft: Optional[int]
    upper_alt_ft: Optional[int]
    geometry: Dict[str, Any]  # GeoJSON


class AirspaceResponse(BaseModel):
    airports: List[Dict[str, Any]]
    boundaries: List[AirspaceBoundary]
    points_of_interest: List[Dict[str, Any]]
