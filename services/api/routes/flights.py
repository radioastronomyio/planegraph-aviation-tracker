"""
routes/flights.py — Flight session query endpoints.

GET /api/v1/flights         — paginated list of sessions (newest first)
                              optional filters: start, end, callsign, hex,
                              min_duration_sec
GET /api/v1/flights/{id}    — single session with trajectory GeoJSON
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_pool
from ..models.schemas import FlightDetail, FlightSummary

log = logging.getLogger(__name__)
router = APIRouter()

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

_LIST_BASE = """
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
"""


def _build_list_query(
    start: Optional[datetime],
    end: Optional[datetime],
    callsign: Optional[str],
    hex_: Optional[str],
    min_duration_sec: Optional[int],
    limit: int,
    offset: int,
) -> tuple[str, list]:
    """Build a parameterised flight list query. Returns (sql, params)."""
    conditions: list[str] = []
    params: list[Any] = []
    idx = 1  # $1, $2, …

    if start is not None:
        conditions.append(f"started_at >= ${idx}")
        params.append(start)
        idx += 1

    if end is not None:
        conditions.append(f"started_at <= ${idx}")
        params.append(end)
        idx += 1

    if callsign is not None:
        conditions.append(f"upper(callsign) like upper(${idx} || '%')")
        params.append(callsign)
        idx += 1

    if hex_ is not None:
        conditions.append(f"hex = ${idx}")
        params.append(hex_)
        idx += 1

    if min_duration_sec is not None:
        conditions.append(f"ended_at is not null")
        conditions.append(
            f"extract(epoch from (ended_at - started_at)) >= ${idx}"
        )
        params.append(float(min_duration_sec))
        idx += 1

    where = ("where " + " and ".join(conditions)) if conditions else ""
    sql = (
        f"{_LIST_BASE} {where} "
        f"order by started_at desc "
        f"limit ${idx} offset ${idx + 1}"
    )
    params.extend([limit, offset])
    return sql, params


@router.get("/api/v1/flights", response_model=List[FlightSummary])
async def list_flights(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    callsign: Optional[str] = Query(default=None, max_length=10),
    hex: Optional[str] = Query(default=None, max_length=6),
    min_duration_sec: Optional[int] = Query(default=None, ge=1),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[FlightSummary]:
    """
    Return a paginated list of flight sessions, newest first.

    Optional filters: start, end, callsign (prefix), hex (exact),
    min_duration_sec (implies ended_at IS NOT NULL).
    """
    sql, params = _build_list_query(start, end, callsign, hex, min_duration_sec, limit, offset)
    rows = await pool.fetch(sql, *params)
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
