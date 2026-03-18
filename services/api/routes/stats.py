"""
routes/stats.py — Operational statistics endpoint.

Returns a snapshot of:
- active_aircraft        : count from live cache
- flights_today          : closed sessions started since midnight UTC
- ingest_rate_per_sec    : position reports per second over the last minute
- materializer_lag_sec   : seconds since the most recent materialization_log entry
"""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends

from ..dependencies import get_live_cache, get_pool
from ..live_state import LiveCache
from ..models.schemas import StatsResponse

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
        select count(*) / 60.0
        from position_reports
        where report_time > now() - interval '60 seconds'
    ) as ingest_rate_per_sec,
    (
        select extract(epoch from (now() - max(materialized_at)))
        from materialization_log
    ) as materializer_lag_sec
"""


@router.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats(
    pool: asyncpg.Pool = Depends(get_pool),
    cache: LiveCache = Depends(get_live_cache),
) -> StatsResponse:
    """
    Return current operational statistics.

    Parameters
    ----------
    pool : asyncpg.Pool
        Injected DB pool.
    cache : LiveCache
        Injected live cache (provides active aircraft count).

    Returns
    -------
    StatsResponse
    """
    row = await pool.fetchrow(_STATS_SQL)
    lag: Optional[float] = None
    if row["materializer_lag_sec"] is not None:
        lag = float(row["materializer_lag_sec"])

    return StatsResponse(
        active_aircraft=cache.aircraft_count(),
        flights_today=int(row["flights_today"]),
        ingest_rate_per_sec=float(row["ingest_rate_per_sec"]),
        materializer_lag_sec=lag,
    )
