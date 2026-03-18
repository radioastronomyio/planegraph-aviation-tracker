"""
main.py — Ingest daemon entry point.

Startup sequence:
  1. Load environment configuration (Config)
  2. Open asyncpg pool
  3. Load pipeline_config rows and apply to Config
  4. Rehydrate active sessions from flight_sessions
  5. Start LISTEN config_changed
  6. Start SBS reader → session manager → batch writer pipeline
  7. Start partition manager schedule
  8. Periodically reap stale sessions
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

import asyncpg

# Ensure the repo root is on the path when run as `python -m services.ingest.main`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.ingest.config          import Config
from services.ingest.sbs_reader      import SBSReader
from services.ingest.phase_classifier import PhaseClassifier
from services.ingest.session_manager  import SessionManager, FlightSessionState
from services.ingest.batch_writer     import BatchWriter
from services.ingest.partition_manager import PartitionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("ingest.main")

# How often to sweep for stale sessions (seconds)
_REAP_INTERVAL = 30

# --- Session close callback --------------------------------------------------

_CLOSE_POOL: Optional[asyncpg.Pool] = None

_UPSERT_SESSION_SQL = """
insert into flight_sessions (session_id, hex, callsign, started_at, ended_at, on_ground)
values ($1, $2, $3, $4, $5, $6)
on conflict (session_id) do update
    set ended_at  = excluded.ended_at,
        callsign  = coalesce(excluded.callsign, flight_sessions.callsign),
        on_ground = excluded.on_ground,
        updated_at = now()
"""

_ENSURE_SESSION_SQL = """
insert into flight_sessions (session_id, hex, callsign, started_at, on_ground)
values ($1, $2, $3, $4, $5)
on conflict (session_id) do nothing
"""


async def _close_session_async(state: FlightSessionState) -> None:
    if _CLOSE_POOL is None:
        return
    now = datetime.now(timezone.utc)
    try:
        async with _CLOSE_POOL.acquire() as conn:
            await conn.execute(
                _UPSERT_SESSION_SQL,
                state.session_id,
                state.icao_hex.ljust(6)[:6],
                state.callsign,
                state.started_at,
                now,
                state.on_ground,
            )
        log.debug("closed session %s for %s", state.session_id, state.icao_hex)
    except Exception as exc:
        log.error("failed to persist closed session %s: %s", state.session_id, exc)


def _on_close_sync(state: FlightSessionState) -> None:
    """Synchronous close callback — schedules the async DB write."""
    loop = asyncio.get_event_loop()
    loop.create_task(_close_session_async(state))


# --- Config listener ---------------------------------------------------------

async def config_listener(pool: asyncpg.Pool, cfg: Config) -> None:
    """Maintains a persistent LISTEN config_changed connection."""
    conn: Optional[asyncpg.Connection] = None
    while True:
        try:
            conn = await pool.acquire()
            await conn.add_listener(
                "config_changed",
                lambda _conn, _pid, _channel, payload: cfg.apply_notify_payload(payload),
            )
            log.info("config_listener: listening on config_changed")
            # Keep the connection alive indefinitely
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("config_listener: error (%s), reconnecting in 5s", exc)
            await asyncio.sleep(5)
        finally:
            if conn is not None:
                try:
                    await pool.release(conn)
                except Exception:
                    pass
                conn = None


# --- Load config from pipeline_config table ----------------------------------

async def load_pipeline_config(pool: asyncpg.Pool, cfg: Config) -> None:
    rows = await pool.fetch("select key, value from pipeline_config")
    for row in rows:
        # asyncpg returns JSONB as Python objects already
        value = row["value"]
        cfg.apply_db_row(row["key"], value)
    log.info("load_pipeline_config: loaded %d keys", len(rows))


# --- Ensure session exists in DB for an open session -------------------------

async def ensure_session(pool: asyncpg.Pool, state: FlightSessionState) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                _ENSURE_SESSION_SQL,
                state.session_id,
                state.icao_hex.ljust(6)[:6],
                state.callsign,
                state.started_at,
                state.on_ground,
            )
    except Exception as exc:
        log.error("ensure_session failed for %s: %s", state.icao_hex, exc)


# --- Session reaper ----------------------------------------------------------

async def session_reaper(manager: SessionManager, pool: asyncpg.Pool) -> None:
    while True:
        await asyncio.sleep(_REAP_INTERVAL)
        closed = manager.reap_stale()
        if closed:
            log.info("session_reaper: reaped %d stale sessions", len(closed))


# --- Main ingest pipeline ----------------------------------------------------

async def ingest_pipeline(
    cfg: Config,
    pool: asyncpg.Pool,
    manager: SessionManager,
    writer: BatchWriter,
) -> None:
    reader = SBSReader(cfg.sbs_host, cfg.sbs_port)
    seen_sessions: set[uuid.UUID] = set()

    async for report in reader.read():
        enriched = manager.process(report)

        # Ensure a flight_sessions row exists before we INSERT position_reports
        # (FK constraint).  We only do this once per session_id.
        sid = enriched.session_id
        if sid not in seen_sessions:
            seen_sessions.add(sid)
            state = manager._sessions.get(report.icao_hex)
            if state is not None:
                await ensure_session(pool, state)

        await writer.enqueue(enriched)


# --- Entry point -------------------------------------------------------------

async def main() -> None:
    global _CLOSE_POOL

    cfg = Config()

    log.info("ingest: connecting to database")
    pool = await asyncpg.create_pool(
        cfg.db_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    _CLOSE_POOL = pool
    log.info("ingest: database pool ready")

    # Load config from DB
    await load_pipeline_config(pool, cfg)

    # Build components
    classifier = PhaseClassifier(cfg.phase_classification)
    manager    = SessionManager(
        classifier               = classifier,
        gap_threshold_sec        = cfg.session_gap_threshold_sec,
        turnaround_threshold_sec = cfg.ground_turnaround_threshold_sec,
        on_close                 = _on_close_sync,
    )
    writer     = BatchWriter(pool, cfg)
    partitions = PartitionManager(pool)

    # Rehydrate open sessions from DB
    await manager.rehydrate(pool)

    # Ensure partitions for today and tomorrow exist
    await partitions.startup()

    # Wire config updates to sub-components
    _orig_apply = cfg.apply_db_row

    def _apply_and_propagate(key: str, value) -> None:
        _orig_apply(key, value)
        if key == "phase_classification" and isinstance(cfg.phase_classification, dict):
            classifier.update_config(cfg.phase_classification)
        elif key == "session_gap_threshold_sec":
            manager.gap_threshold_sec = cfg.session_gap_threshold_sec
        elif key == "ground_turnaround_threshold_sec":
            manager.turnaround_threshold_sec = cfg.ground_turnaround_threshold_sec

    cfg.apply_db_row = _apply_and_propagate

    log.info("ingest: starting pipeline tasks")
    async with asyncio.TaskGroup() as tg:
        tg.create_task(config_listener(pool, cfg),            name="config_listener")
        tg.create_task(writer.flush_loop(),                   name="batch_writer")
        tg.create_task(partitions.run(),                      name="partition_manager")
        tg.create_task(session_reaper(manager, pool),         name="session_reaper")
        tg.create_task(
            ingest_pipeline(cfg, pool, manager, writer),      name="ingest_pipeline"
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("ingest: shutdown requested")
