"""
routes/stats.py — Operational statistics endpoints.

GET /api/v1/stats
    Snapshot: active aircraft, flights today/last-hour, ingest rate,
    materializer lag, storage size, oldest data date.

GET /api/v1/stats/hourly?hours=N
    Flight counts bucketed by hour for the past N hours (default 24).

GET /api/v1/stats/phases
    Distribution of flight_phase values in position_reports over the
    last hour.

GET /api/v1/stats/top-aircraft?limit=N
    Aircraft ranked by number of completed sessions in the last 24 h.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..dependencies import get_live_cache, get_pool
from ..live_state import LiveCache
from ..models.schemas import (
    HourlyStatPoint,
    PhaseStatEntry,
    StatsResponse,
    TopAircraftEntry,
)

log = logging.getLogger(__name__)
router = APIRouter()

_STATS_SQL = """
select
    (
        select count(*)
        from flight_sessions
        where started_at >= date_trunc('day', now() at time zone 'utc')
          and ended_at is not null
    ) as flights_today,
    (
        select count(*)
        from flight_sessions
        where started_at >= now() - interval '1 hour'
          and ended_at is not null
    ) as flights_in_last_hour,
    (
        select count(*) / 60.0
        from position_reports
        where report_time > now() - interval '60 seconds'
    ) as ingest_rate_per_sec,
    (
        select extract(epoch from (now() - max(materialized_at)))
        from materialization_log
    ) as materializer_lag_sec,
    pg_database_size(current_database()) as storage_bytes,
    (
        select min(report_time)::date
        from position_reports
    ) as oldest_data_date
"""

_HOURLY_SQL = """
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
group by slots.slot
order by slots.slot
"""

_PHASES_SQL = """
select flight_phase as phase, count(*) as count
from position_reports
where report_time > now() - interval '1 hour'
  and flight_phase is not null
group by flight_phase
order by count desc
"""

_TOP_AIRCRAFT_SQL = """
select
    hex,
    (array_agg(callsign order by started_at desc)
        filter (where callsign is not null))[1] as callsign,
    count(*) as flight_count
from flight_sessions
where ended_at is not null
  and started_at >= now() - interval '24 hours'
group by hex
order by flight_count desc
limit $1
"""


@router.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats(
    pool: asyncpg.Pool = Depends(get_pool),
    cache: LiveCache = Depends(get_live_cache),
) -> StatsResponse:
    """Return current operational statistics."""
    row = await pool.fetchrow(_STATS_SQL)

    lag: Optional[float] = None
    if row["materializer_lag_sec"] is not None:
        lag = float(row["materializer_lag_sec"])

    storage: Optional[int] = None
    if row["storage_bytes"] is not None:
        storage = int(row["storage_bytes"])

    oldest: Optional[str] = None
    if row["oldest_data_date"] is not None:
        oldest = str(row["oldest_data_date"])

    return StatsResponse(
        active_aircraft=cache.aircraft_count(),
        flights_today=int(row["flights_today"]),
        flights_in_last_hour=int(row["flights_in_last_hour"]),
        ingest_rate_per_sec=float(row["ingest_rate_per_sec"]),
        materializer_lag_sec=lag,
        storage_bytes=storage,
        oldest_data_date=oldest,
    )


@router.get("/api/v1/stats/hourly", response_model=List[HourlyStatPoint])
async def get_stats_hourly(
    hours: int = Query(default=24, ge=1, le=168),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[HourlyStatPoint]:
    """Return per-hour flight counts for the past ``hours`` hours."""
    rows = await pool.fetch(_HOURLY_SQL, hours)
    return [
        HourlyStatPoint(hour_start=row["hour_start"], flight_count=int(row["flight_count"]))
        for row in rows
    ]


@router.get("/api/v1/stats/phases", response_model=List[PhaseStatEntry])
async def get_stats_phases(
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[PhaseStatEntry]:
    """Return phase distribution from position_reports over the last hour."""
    rows = await pool.fetch(_PHASES_SQL)
    return [
        PhaseStatEntry(phase=row["phase"], count=int(row["count"]))
        for row in rows
    ]


@router.get("/api/v1/stats/top-aircraft", response_model=List[TopAircraftEntry])
async def get_stats_top_aircraft(
    limit: int = Query(default=20, ge=1, le=100),
    pool: asyncpg.Pool = Depends(get_pool),
) -> List[TopAircraftEntry]:
    """Return aircraft ranked by completed flight count in the last 24 h."""
    rows = await pool.fetch(_TOP_AIRCRAFT_SQL, limit)
    return [
        TopAircraftEntry(
            hex=row["hex"],
            callsign=row["callsign"],
            flight_count=int(row["flight_count"]),
        )
        for row in rows
    ]
