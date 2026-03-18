"""
routes/health.py — System health endpoint.

Reports:
- Postgres connectivity
- Ingest freshness (max report_time in position_reports)
- Ultrafeeder availability (TCP reachability on SBS port 30003)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends

from ..dependencies import get_pool
from ..models.schemas import HealthResponse

log = logging.getLogger(__name__)
router = APIRouter()


async def _check_postgres(pool: asyncpg.Pool) -> tuple[str, bool, str | None]:
    """Returns (status, ingest_active, last_report_iso)."""
    try:
        row = await pool.fetchrow(
            "select max(report_time) as last_ts from position_reports"
        )
        last_ts: datetime | None = row["last_ts"] if row else None
        if last_ts is None:
            return "healthy", False, None

        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)

        age_sec = (datetime.now(timezone.utc) - last_ts).total_seconds()
        ingest_active = age_sec < 60  # consider stale after 60 s
        return "healthy", ingest_active, last_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as exc:
        log.warning("health: postgres check failed: %s", exc)
        return "unhealthy", False, None


async def _check_ultrafeeder() -> str:
    """
    Attempt a TCP connection to the SBS output port.

    Returns "healthy" on success, "unreachable" on failure.
    """
    host = os.environ.get("SBS_HOST", "localhost")
    port = int(os.environ.get("SBS_PORT", "30003"))
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=3.0
        )
        writer.close()
        await writer.wait_closed()
        return "healthy"
    except Exception:
        return "unreachable"


@router.get("/api/v1/health", response_model=HealthResponse)
async def health(pool: asyncpg.Pool = Depends(get_pool)) -> HealthResponse:
    """
    Return system health summary.

    Parameters
    ----------
    pool : asyncpg.Pool
        Injected DB pool.

    Returns
    -------
    HealthResponse
        Aggregated health state.
    """
    pg_status, ingest_active, last_ts = await _check_postgres(pool)
    uf_status = await _check_ultrafeeder()

    overall = "healthy"
    if pg_status != "healthy":
        overall = "unhealthy"
    elif uf_status != "healthy" or not ingest_active:
        overall = "degraded"

    return HealthResponse(
        status=overall,
        postgres=pg_status,
        ultrafeeder=uf_status,
        ingest_active=ingest_active,
        last_position_report=last_ts,
    )
