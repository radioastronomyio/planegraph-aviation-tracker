"""
main.py — Materializer daemon entry point.

Startup sequence:
  1. Load environment configuration
  2. Open asyncpg pool
  3. Establish watermark from materialization_log
  4. Start LISTEN new_positions
  5. Start LISTEN config_changed
  6. On each new_positions notification, process newly closed sessions
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.materializer.trajectory_builder import build_trajectories
from services.materializer.scalar_computer    import compute_scalars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("materializer.main")


def _build_dsn() -> str:
    return (
        f"postgresql://{os.environ['POSTGRES_USER']}"
        f":{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'localhost')}"
        f":{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ['POSTGRES_DB']}"
    )


# --- Config hot-reload -------------------------------------------------------

class _Config:
    pass  # placeholder — materializer has no threshold config yet


_cfg = _Config()


def _apply_config(key: str, value) -> None:
    log.info("materializer: config_changed key=%s value=%r", key, value)
    # Future: apply materializer-specific thresholds here


# --- Materializer core -------------------------------------------------------

# Watermark: last report_time we have fully processed
_watermark: Optional[datetime] = None

# Queue of notifications from new_positions LISTEN channel
_notify_queue: asyncio.Queue = asyncio.Queue()


async def _load_watermark(pool: asyncpg.Pool) -> None:
    global _watermark
    row = await pool.fetchrow(
        "select max(materialized_at) as wm from materialization_log"
    )
    if row and row["wm"]:
        _watermark = row["wm"]
        log.info("materializer: watermark loaded: %s", _watermark)
    else:
        _watermark = None
        log.info("materializer: no watermark found, will process all closed sessions")


_CLOSED_SINCE_SQL = """
select distinct session_id
from   flight_sessions
where  ended_at is not null
  and  trajectory_geom is null
  and  ($1::timestamptz is null or ended_at > $1)
"""


async def _process_notification(pool: asyncpg.Pool, payload: str) -> None:
    global _watermark

    # Parse the batch boundary from the notification payload
    try:
        data = json.loads(payload)
        max_time_str = data.get("max_time")
        if max_time_str:
            batch_max = datetime.fromisoformat(max_time_str.rstrip("Z")).replace(
                tzinfo=timezone.utc
            )
        else:
            batch_max = datetime.now(timezone.utc)
    except Exception:
        batch_max = datetime.now(timezone.utc)

    # Find closed sessions with no trajectory yet, newer than watermark
    rows = await pool.fetch(_CLOSED_SINCE_SQL, _watermark)
    session_ids = [row["session_id"] for row in rows]

    if not session_ids:
        return

    log.info(
        "materializer: processing %d closed sessions (watermark=%s)",
        len(session_ids), _watermark,
    )

    async with pool.acquire() as conn:
        async with conn.transaction():
            await build_trajectories(conn, session_ids)
            await compute_scalars(conn, session_ids)

    _watermark = batch_max
    log.info("materializer: done, watermark advanced to %s", _watermark)


async def _notification_processor(pool: asyncpg.Pool) -> None:
    while True:
        payload = await _notify_queue.get()
        try:
            await _process_notification(pool, payload)
        except Exception as exc:
            log.error("materializer: processing error: %s", exc, exc_info=True)
        finally:
            _notify_queue.task_done()


# --- Listeners ---------------------------------------------------------------

async def _listen_new_positions(pool: asyncpg.Pool) -> None:
    conn: Optional[asyncpg.Connection] = None
    while True:
        try:
            conn = await pool.acquire()

            def _on_notify(_conn, _pid, _channel, payload):
                _notify_queue.put_nowait(payload)

            await conn.add_listener("new_positions", _on_notify)
            log.info("materializer: listening on new_positions")
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("materializer: new_positions listener error (%s), reconnecting", exc)
            await asyncio.sleep(5)
        finally:
            if conn is not None:
                try:
                    await pool.release(conn)
                except Exception:
                    pass
                conn = None


async def _listen_config_changed(pool: asyncpg.Pool) -> None:
    conn: Optional[asyncpg.Connection] = None
    while True:
        try:
            conn = await pool.acquire()

            def _on_config(_conn, _pid, _channel, payload):
                try:
                    data = json.loads(payload)
                    _apply_config(data.get("key", ""), data.get("value"))
                except Exception as e:
                    log.warning("materializer: config payload parse error: %s", e)

            await conn.add_listener("config_changed", _on_config)
            log.info("materializer: listening on config_changed")
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("materializer: config_changed listener error (%s), reconnecting", exc)
            await asyncio.sleep(5)
        finally:
            if conn is not None:
                try:
                    await pool.release(conn)
                except Exception:
                    pass
                conn = None


# --- Entry point -------------------------------------------------------------

async def main() -> None:
    dsn = _build_dsn()

    log.info("materializer: connecting to database")
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5, command_timeout=60)
    log.info("materializer: database pool ready")

    await _load_watermark(pool)

    # Catch up on any sessions that closed while we were down
    rows = await pool.fetch(_CLOSED_SINCE_SQL, _watermark)
    if rows:
        log.info(
            "materializer: startup catch-up: %d unprocessed closed sessions", len(rows)
        )
        session_ids = [row["session_id"] for row in rows]
        async with pool.acquire() as conn:
            async with conn.transaction():
                await build_trajectories(conn, session_ids)
                await compute_scalars(conn, session_ids)
        log.info("materializer: startup catch-up complete")

    async with asyncio.TaskGroup() as tg:
        tg.create_task(_listen_new_positions(pool),    name="listen_new_positions")
        tg.create_task(_listen_config_changed(pool),   name="listen_config_changed")
        tg.create_task(_notification_processor(pool),  name="notification_processor")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("materializer: shutdown requested")
