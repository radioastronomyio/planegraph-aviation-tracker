"""
batch_writer.py — Micro-batch writer for position_reports.

Buffers EnrichedReport objects for batch_interval_sec seconds, then
issues one bulk INSERT via unnest(...) and emits NOTIFY new_positions
with a JSON payload containing batch_size and max_time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List

import asyncpg

from .session_manager import EnrichedReport

log = logging.getLogger(__name__)

_INSERT_SQL = """
insert into position_reports (
    session_id, hex, report_time,
    lat, lon, alt_ft, track, speed_kts, vrate_fpm,
    flight_phase, squawk, on_ground, category, geom
)
select
    unnest($1::uuid[]),
    unnest($2::char(6)[]),
    unnest($3::timestamptz[]),
    unnest($4::numeric[]),
    unnest($5::numeric[]),
    unnest($6::integer[]),
    unnest($7::numeric[]),
    unnest($8::integer[]),
    unnest($9::integer[]),
    unnest($10::varchar[]),
    unnest($11::varchar[]),
    unnest($12::boolean[]),
    null,
    st_setsrid(
        st_makepoint(
            unnest($13::double precision[]),  -- lon
            unnest($14::double precision[]),  -- lat
            unnest($15::double precision[])   -- alt metres (approx)
        ),
        4326
    )
"""

_NOTIFY_SQL = "select pg_notify('new_positions', $1)"


class BatchWriter:
    """
    Accumulate EnrichedReport objects and flush them in bulk.

    Usage:
        writer = BatchWriter(pool, cfg)
        await writer.enqueue(enriched_report)
        # The flush loop runs automatically via `start()`
    """

    def __init__(self, pool: asyncpg.Pool, cfg):
        self._pool   = pool
        self._cfg    = cfg
        self._buffer: List[EnrichedReport] = []
        self._lock   = asyncio.Lock()

    async def enqueue(self, report: EnrichedReport) -> None:
        async with self._lock:
            self._buffer.append(report)

    async def flush_loop(self) -> None:
        """Run indefinitely, flushing every batch_interval_sec."""
        while True:
            await asyncio.sleep(self._cfg.batch_interval_sec)
            await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []

        try:
            await self._write(batch)
        except Exception as exc:
            log.error("batch_writer: flush failed: %s", exc, exc_info=True)
            # Re-queue on error to avoid data loss
            async with self._lock:
                self._buffer = batch + self._buffer

    async def _write(self, batch: List[EnrichedReport]) -> None:
        session_ids = [str(r.session_id) for r in batch]
        hexes       = [r.icao_hex.ljust(6)[:6]  for r in batch]
        times       = [r.report_time             for r in batch]
        lats        = [float(r.lat)              for r in batch]
        lons        = [float(r.lon)              for r in batch]
        alts        = [r.alt_ft                  for r in batch]
        tracks      = [float(r.track) if r.track is not None else None for r in batch]
        speeds      = [r.speed_kts               for r in batch]
        vrates      = [r.vrate_fpm               for r in batch]
        phases      = [r.phase                   for r in batch]
        squawks     = [r.squawk                  for r in batch]
        on_grounds  = [r.on_ground               for r in batch]
        lons_geom   = lons
        lats_geom   = lats
        alts_m      = [float(a) * 0.3048 if a is not None else 0.0 for a in alts]

        max_time    = max(r.report_time for r in batch)
        max_time_str = max_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    _INSERT_SQL,
                    session_ids, hexes, times,
                    lats, lons, alts, tracks, speeds, vrates,
                    phases, squawks, on_grounds,
                    lons_geom, lats_geom, alts_m,
                )
                payload = json.dumps(
                    {"batch_size": len(batch), "max_time": max_time_str}
                )
                await conn.execute(_NOTIFY_SQL, payload)

        log.debug("batch_writer: wrote %d rows, max_time=%s", len(batch), max_time_str)
