"""
routes/flights.py — Flight session query endpoints.

GET /api/v1/flights         — paginated list of sessions (newest first)
GET /api/v1/flights/{id}    — single session with trajectory GeoJSON
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_pool
from ..models.schemas import FlightDetail, FlightSummary

log = logging.getLogger(__name__)
router = APIRouter()

_LIST_SQL = """
select
    session_id,
    hex,
    callsign,
    started_at,
    ended_at,
    on_ground,
    total_distance_nm,
    departure_airport_icao,
    arrival_airport_icao
from flight_sessions
order by started_at desc
limit  $1
offset $2
"""

_DETAIL_SQL = """
select
    session_id,
    hex,
    callsign,
    started_at,
    ended_at,
    on_ground,
    total_distance_nm,
    departure_airport_icao,
    arrival_airport_icao,
    st_asgeojson(trajectory_geom)::text as trajectory_geojson
from flight_sessions
where session_id = $1
"""


@router.get("/api/v1/flights", response_model=List[FlightSummary])
async def list_flights(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[FlightSummary]:
    """
    Return a paginated list of flight sessions, newest first.

    Parameters
    ----------
    limit : int
        Maximum number of sessions to return (1–500, default 50).
    offset : int
        Row offset for pagination.
    pool : asyncpg.Pool
        Injected DB pool.

    Returns
    -------
    list of FlightSummary
    """
    rows = await pool.fetch(_LIST_SQL, limit, offset)
    return [
        FlightSummary(
            session_id=row["session_id"],
            hex=row["hex"].strip(),
            callsign=row["callsign"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            on_ground=row["on_ground"],
            total_distance_nm=float(row["total_distance_nm"]) if row["total_distance_nm"] is not None else None,
            departure_airport_icao=row["departure_airport_icao"],
            arrival_airport_icao=row["arrival_airport_icao"],
        )
        for row in rows
    ]


@router.get("/api/v1/flights/{session_id}", response_model=FlightDetail)
async def get_flight(
    session_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> FlightDetail:
    """
    Return detailed session data including trajectory as GeoJSON.

    Parameters
    ----------
    session_id : UUID
        Flight session identifier.
    pool : asyncpg.Pool
        Injected DB pool.

    Returns
    -------
    FlightDetail
        Session metadata plus optional trajectory GeoJSON.

    Raises
    ------
    HTTPException (404)
        When session_id is not found.
    """
    row = await pool.fetchrow(_DETAIL_SQL, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Flight session not found")

    trajectory: Optional[Dict[str, Any]] = None
    if row["trajectory_geojson"]:
        try:
            trajectory = json.loads(row["trajectory_geojson"])
        except Exception:
            log.warning("flights: could not parse trajectory GeoJSON for %s", session_id)

    return FlightDetail(
        session_id=row["session_id"],
        hex=row["hex"].strip(),
        callsign=row["callsign"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        on_ground=row["on_ground"],
        total_distance_nm=float(row["total_distance_nm"]) if row["total_distance_nm"] is not None else None,
        departure_airport_icao=row["departure_airport_icao"],
        arrival_airport_icao=row["arrival_airport_icao"],
        trajectory=trajectory,
    )
