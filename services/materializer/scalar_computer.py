"""
scalar_computer.py — Computes scalar metrics for closed sessions.

Currently computes total_distance_nm using ST_Length on the
trajectory_geom (geography cast for geodetic metres → nautical miles).

Also writes a materialization_log entry.
"""

from __future__ import annotations

import json
import logging
from typing import List
from uuid import UUID

import asyncpg

log = logging.getLogger(__name__)

_DISTANCE_SQL = """
update flight_sessions
set    total_distance_nm = round(
           (st_length(trajectory_geom::geography) / 1852.0)::numeric,
           2
       ),
       updated_at = now()
where  session_id = any($1::uuid[])
  and  trajectory_geom is not null
  and  ended_at is not null
"""

_PHASE_SUMMARY_SQL = """
select
    session_id,
    jsonb_object_agg(phase, cnt) as phase_summary
from (
    select session_id, flight_phase as phase, count(*) as cnt
    from   position_reports
    where  session_id = any($1::uuid[])
    group  by session_id, flight_phase
) sub
group by session_id
"""

_LOG_SQL = """
insert into materialization_log (session_id, materialized_at, distance_nm, phase_summary)
select
    fs.session_id,
    now(),
    fs.total_distance_nm,
    $2::jsonb
from flight_sessions fs
where fs.session_id = $1
  and fs.ended_at is not null
on conflict (session_id, materialized_at) do nothing
"""


async def compute_scalars(
    conn: asyncpg.Connection, session_ids: List[UUID]
) -> None:
    """Update total_distance_nm and write materialization_log for each session."""
    if not session_ids:
        return

    str_ids = [str(s) for s in session_ids]

    await conn.execute(_DISTANCE_SQL, str_ids)

    # Fetch phase summaries for log
    rows = await conn.fetch(_PHASE_SUMMARY_SQL, str_ids)
    phase_map = {row["session_id"]: row["phase_summary"] for row in rows}

    for sid in session_ids:
        summary = phase_map.get(sid, {})
        try:
            await conn.execute(
                _LOG_SQL,
                sid,
                json.dumps(summary),
            )
        except Exception as exc:
            log.warning("scalar_computer: log write failed for %s: %s", sid, exc)

    log.debug("scalar_computer: scalars computed for %d sessions", len(session_ids))
