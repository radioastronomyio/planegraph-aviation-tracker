"""
trajectory_builder.py — Builds trajectory_geom for closed sessions.

Uses ST_MakeLine(geom ORDER BY report_time) to construct a LineStringZ
from the position_reports rows.  Only operates on closed sessions
(ended_at IS NOT NULL).
"""

from __future__ import annotations

import logging
from typing import List
from uuid import UUID

import asyncpg

log = logging.getLogger(__name__)

_BUILD_SQL = """
update flight_sessions fs
set    trajectory_geom = sub.traj,
       updated_at      = now()
from (
    select
        session_id,
        st_makeline(geom order by report_time) as traj
    from   position_reports
    where  session_id = any($1::uuid[])
      and  geom is not null
    group  by session_id
) sub
where  fs.session_id = sub.session_id
  and  fs.ended_at is not null
"""


async def build_trajectories(
    conn: asyncpg.Connection, session_ids: List[UUID]
) -> int:
    """
    Compute and store trajectory_geom for the given closed session_ids.
    Returns the number of sessions updated.
    """
    if not session_ids:
        return 0
    result = await conn.execute(_BUILD_SQL, [str(s) for s in session_ids])
    # result is "UPDATE n"
    try:
        n = int(result.split()[-1])
    except (ValueError, IndexError):
        n = 0
    log.debug("trajectory_builder: updated %d trajectories", n)
    return n
