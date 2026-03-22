"""
routes/analytics.py — Data-science analytics endpoints.

GET /api/v1/flights/{session_id}/track
    Ordered time-series of position reports for a flight.

GET /api/v1/flights/{session_id}/approach-analysis
    Server-side glideslope deviation computation for the approach phase.

GET /api/v1/analytics/heatmap-samples
    Random-sampled weighted position points for a client-side HeatmapLayer.

GET /api/v1/analytics/airports/summary
    Arrivals and departures per airport for a time window.

GET /api/v1/analytics/airports/runway-utilization
    Estimated runway usage based on last-position proximity.

GET /api/v1/analytics/airports/hourly
    Hour-bucketed flight activity for a specific airport.
"""

from __future__ import annotations

import math
import logging
from typing import List
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_pool
from ..models.schemas import (
    AirportHourlyPoint,
    AirportSummary,
    ApproachAnalysis,
    ApproachPoint,
    HeatmapSample,
    RunwayInfo,
    RunwayUtilization,
    TrackPoint,
)

log = logging.getLogger(__name__)
router = APIRouter()

_TAN_3DEG = math.tan(math.radians(3))   # 0.05240778
_FT_PER_NM = 6076.12
_EARTH_RADIUS_NM = 3440.065

# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------

_TRACK_SQL = """
select
    report_time,
    lat::float,
    lon::float,
    alt_ft,
    speed_kts,
    vrate_fpm,
    track::float,
    flight_phase
from position_reports
where session_id = $1
order by report_time asc
"""


@router.get("/api/v1/flights/{session_id}/track", response_model=List[TrackPoint])
async def get_flight_track(
    session_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[TrackPoint]:
    """
    Return ordered time-series position reports for a flight session.

    Raises
    ------
    HTTPException (404)
        When the session does not exist or has no position reports.
    """
    rows = await pool.fetch(_TRACK_SQL, session_id)
    if not rows:
        exists = await pool.fetchval(
            "select 1 from flight_sessions where session_id = $1", session_id
        )
        if exists is None:
            raise HTTPException(status_code=404, detail="Flight session not found")
        raise HTTPException(status_code=404, detail="No track data for this session")

    return [
        TrackPoint(
            timestamp=row["report_time"],
            lat=row["lat"],
            lon=row["lon"],
            alt_ft=row["alt_ft"],
            speed_kts=row["speed_kts"],
            vrate_fpm=row["vrate_fpm"],
            track=row["track"],
            phase=row["flight_phase"],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Approach analysis
# ---------------------------------------------------------------------------

_APP_TRACK_SQL = """
select
    report_time,
    lat::float,
    lon::float,
    alt_ft
from position_reports
where session_id = $1
  and alt_ft is not null
order by report_time asc
"""

_RUNWAY_BY_HEADING_SQL = """
select
    runway_id,
    designator,
    heading_true::float,
    threshold_lat::float,
    threshold_lon::float,
    threshold_elevation_ft
from runways
where airport_icao = $1
"""

_NEAREST_RUNWAY_SQL = """
select
    r.runway_id,
    r.airport_icao,
    r.designator,
    r.heading_true::float,
    r.threshold_lat::float,
    r.threshold_lon::float,
    r.threshold_elevation_ft,
    ST_Distance(
        r.threshold_geom::geography,
        ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
    ) / 1852.0 as distance_nm
from runways r
where ST_Distance(
    r.threshold_geom::geography,
    ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
) <= 27780  -- 15 NM in metres
order by distance_nm asc
limit 1
"""

_THRESHOLD_DIST_SQL = """
select
    ST_Distance(
        $3::geography,
        ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
    ) / 1852.0 as distance_nm
"""


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in nautical miles."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * math.asin(math.sqrt(a)) * _EARTH_RADIUS_NM


def _heading_diff(h1: float, h2: float) -> float:
    """Absolute angular difference between two headings (0–180)."""
    d = abs(h1 - h2) % 360
    return d if d <= 180 else 360 - d


def _severity(deviation_ft: float) -> str:
    abs_dev = abs(deviation_ft)
    if abs_dev <= 100:
        return "GREEN"
    if abs_dev <= 200:
        return "YELLOW"
    return "RED"


@router.get("/api/v1/flights/{session_id}/approach-analysis", response_model=ApproachAnalysis)
async def approach_analysis(
    session_id: UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ApproachAnalysis:
    """
    Compute server-side glideslope deviation for a flight's approach phase.

    Raises
    ------
    HTTPException (404)
        When the session does not exist, has no position data, or no
        approach runway can be identified.
    """
    # 1. Session lookup
    session_row = await pool.fetchrow(
        "select arrival_airport_icao from flight_sessions where session_id = $1",
        session_id,
    )
    if session_row is None:
        raise HTTPException(status_code=404, detail="Flight session not found")

    # 2. Position reports with altitude
    pos_rows = await pool.fetch(_APP_TRACK_SQL, session_id)
    if not pos_rows:
        raise HTTPException(status_code=404, detail="No position data for this session")

    # 3. Determine approach runway
    icao = session_row["arrival_airport_icao"]
    runway: dict | None = None

    if icao:
        icao = icao.strip()
        rwy_rows = await pool.fetch(_RUNWAY_BY_HEADING_SQL, icao)
        if rwy_rows:
            # Average track over final 20 reports
            tail = pos_rows[-20:]
            # We need track data — re-query with track column for the tail
            tail_with_track = await pool.fetch(
                """
                select track::float
                from position_reports
                where session_id = $1 and track is not null
                order by report_time desc
                limit 20
                """,
                session_id,
            )
            if tail_with_track:
                avg_track = sum(r["track"] for r in tail_with_track) / len(tail_with_track)
                # Find runway whose heading is closest to aircraft inbound track.
                # Aircraft approaches heading toward runway, so compare directly.
                best = min(
                    rwy_rows,
                    key=lambda r: _heading_diff(r["heading_true"], avg_track),
                )
            else:
                # Fallback: nearest to last position
                last = pos_rows[-1]
                best = min(
                    rwy_rows,
                    key=lambda r: _haversine_nm(
                        last["lat"], last["lon"],
                        r["threshold_lat"], r["threshold_lon"],
                    ),
                )
            runway = dict(best)
            runway["airport_icao"] = icao

    if runway is None:
        # Nearest runway within 15 NM of last position
        last = pos_rows[-1]
        nr = await pool.fetchrow(_NEAREST_RUNWAY_SQL, last["lat"], last["lon"])
        if nr is None:
            raise HTTPException(status_code=404, detail="No approach runway identified")
        runway = dict(nr)

    thr_lat = runway["threshold_lat"]
    thr_lon = runway["threshold_lon"]
    thr_elev = runway["threshold_elevation_ft"]

    # 4. Compute glideslope deviations for points below 5000 ft AGL
    points: list[ApproachPoint] = []
    for row in pos_rows:
        alt_ft = row["alt_ft"]
        agl = alt_ft - thr_elev
        if agl >= 5000:
            continue

        dist_nm = _haversine_nm(row["lat"], row["lon"], thr_lat, thr_lon)
        dist_ft = dist_nm * _FT_PER_NM
        expected = thr_elev + 50 + dist_ft * _TAN_3DEG
        deviation = alt_ft - expected

        points.append(
            ApproachPoint(
                timestamp=row["report_time"],
                distance_nm=round(dist_nm, 3),
                actual_alt_ft_msl=alt_ft,
                expected_alt_ft_msl=round(expected),
                deviation_ft=round(deviation),
                severity=_severity(deviation),
            )
        )

    return ApproachAnalysis(
        runway=RunwayInfo(
            icao=runway.get("airport_icao", runway.get("icao", "")).strip(),
            designator=runway["designator"],
            threshold_elevation_ft=thr_elev,
            heading_true=runway["heading_true"],
        ),
        points=points,
    )


# ---------------------------------------------------------------------------
# Heatmap samples
# ---------------------------------------------------------------------------

_HEATMAP_SQL = """
select lat::float, lon::float
from position_reports
where report_time > now() - $1 * interval '1 hour'
  and lat is not null
  and lon is not null
order by random()
limit $2
"""


@router.get("/api/v1/analytics/heatmap-samples", response_model=List[HeatmapSample])
async def heatmap_samples(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=50000, ge=1, le=100000),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[HeatmapSample]:
    """Return random-sampled position points for a client-side HeatmapLayer."""
    rows = await pool.fetch(_HEATMAP_SQL, hours, limit)
    return [HeatmapSample(lat=row["lat"], lon=row["lon"], weight=1.0) for row in rows]


# ---------------------------------------------------------------------------
# Airport analytics — summary
# ---------------------------------------------------------------------------

_AIRPORT_SUMMARY_SQL = """
select
    a.icao,
    a.name,
    count(*) filter (where fs.arrival_airport_icao = a.icao)   as arrivals,
    count(*) filter (where fs.departure_airport_icao = a.icao) as departures
from airports a
left join flight_sessions fs
    on (fs.arrival_airport_icao = a.icao or fs.departure_airport_icao = a.icao)
    and fs.ended_at is not null
    and fs.started_at >= now() - $1 * interval '1 hour'
group by a.icao, a.name
order by (
    count(*) filter (where fs.arrival_airport_icao = a.icao)
  + count(*) filter (where fs.departure_airport_icao = a.icao)
) desc
"""


@router.get("/api/v1/analytics/airports/summary", response_model=List[AirportSummary])
async def airports_summary(
    hours: int = Query(default=24, ge=1, le=720),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[AirportSummary]:
    """Return arrivals and departures per airport for the past N hours."""
    rows = await pool.fetch(_AIRPORT_SUMMARY_SQL, hours)
    return [
        AirportSummary(
            icao=row["icao"].strip(),
            name=row["name"],
            arrivals=int(row["arrivals"]),
            departures=int(row["departures"]),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Airport analytics — runway utilization
# ---------------------------------------------------------------------------

_RUNWAY_UTIL_SQL = """
with last_positions as (
    select distinct on (pr.session_id)
        pr.session_id,
        pr.lat::float,
        pr.lon::float,
        pr.alt_ft
    from position_reports pr
    join flight_sessions fs on fs.session_id = pr.session_id
    where fs.ended_at is not null
      and fs.started_at >= now() - $1 * interval '1 hour'
    order by pr.session_id, pr.report_time desc
)
select
    r.airport_icao,
    r.designator,
    count(*) as flight_count
from last_positions lp
join runways r on ST_DWithin(
    r.threshold_geom::geography,
    ST_SetSRID(ST_MakePoint(lp.lon, lp.lat), 4326)::geography,
    5556
)
where lp.alt_ft is not null
  and lp.alt_ft - r.threshold_elevation_ft < 1500
group by r.airport_icao, r.designator
order by flight_count desc
"""


@router.get("/api/v1/analytics/airports/runway-utilization", response_model=List[RunwayUtilization])
async def runway_utilization(
    hours: int = Query(default=24, ge=1, le=720),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[RunwayUtilization]:
    """Return estimated flight count per runway for the past N hours."""
    rows = await pool.fetch(_RUNWAY_UTIL_SQL, hours)
    return [
        RunwayUtilization(
            airport_icao=row["airport_icao"].strip(),
            designator=row["designator"],
            flight_count=int(row["flight_count"]),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Airport analytics — hourly
# ---------------------------------------------------------------------------

_AIRPORT_HOURLY_SQL = """
with slots as (
    select generate_series(
        date_trunc('hour', now() - $1 * interval '1 hour'),
        date_trunc('hour', now()) - interval '1 hour',
        interval '1 hour'
    ) as slot
    union all
    select date_trunc('hour', now())
)
select
    slots.slot::text as hour_start,
    count(fs.session_id) as flight_count
from slots
left join flight_sessions fs
    on date_trunc('hour', fs.started_at) = slots.slot
    and fs.ended_at is not null
    and (fs.arrival_airport_icao = $2 or fs.departure_airport_icao = $2)
group by slots.slot
order by slots.slot
"""


@router.get("/api/v1/analytics/airports/hourly", response_model=List[AirportHourlyPoint])
async def airport_hourly(
    icao: str = Query(..., min_length=4, max_length=4),
    hours: int = Query(default=24, ge=1, le=168),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[AirportHourlyPoint]:
    """Return hour-bucketed flight activity for a specific airport."""
    rows = await pool.fetch(_AIRPORT_HOURLY_SQL, hours, icao.upper())
    return [
        AirportHourlyPoint(hour_start=row["hour_start"], flight_count=int(row["flight_count"]))
        for row in rows
    ]
