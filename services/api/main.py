"""
main.py — FastAPI application entry point.

Startup sequence
----------------
1. Create asyncpg connection pool.
2. Load current session_gap_threshold_sec from pipeline_config.
3. Create LiveCache and warm-restore from recent position_reports.
4. Start background LISTEN new_positions task (drives cache updates).
5. Start background LISTEN config_changed task (keeps gap threshold current).
6. Start background broadcast task (sends DIFFERENTIAL_UPDATE every second).
7. Register REST routes and WebSocket route.
8. Mount frontend/dist/ if present.

Shutdown sequence
-----------------
1. Cancel all background tasks.
2. Close the asyncpg pool.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import asyncpg
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import create_pool
from .live_state import LiveCache
from .routes import aircraft, airspace, analytics, config, flights, health, stats
from .ws import live as ws_live

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level reference so ws/live.py can access the cache without a
# circular import via Depends (WebSocket endpoints don't support Depends
# for app.state injection in all FastAPI versions).
# ---------------------------------------------------------------------------
_live_cache: Optional[LiveCache] = None


def get_live_cache_from_app() -> LiveCache:
    """Called by the WebSocket handler to access the shared cache."""
    if _live_cache is None:
        raise RuntimeError("LiveCache has not been initialised yet")
    return _live_cache


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def _listen_new_positions(pool: asyncpg.Pool, cache: LiveCache, dsn: str) -> None:
    """
    Maintain a dedicated asyncpg connection that LISTENs on new_positions.

    Each NOTIFY payload is forwarded to LiveCache.process_notify() which
    fetches incremental rows and merges them into the in-memory state.
    A dedicated connection (not pool-acquired) is used so we can remove the
    listener cleanly before closing.
    """
    log.info("api: starting LISTEN new_positions")
    while True:
        conn: Optional[asyncpg.Connection] = None
        try:
            conn = await asyncpg.connect(dsn)

            def _on_notify(_conn, _pid, _chan, payload: str) -> None:
                asyncio.ensure_future(cache.process_notify(pool, payload))

            await conn.add_listener("new_positions", _on_notify)
            log.info("api: listening on new_positions")
            while True:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            if conn is not None:
                try:
                    await conn.remove_listener("new_positions", _on_notify)
                except Exception:
                    pass
                await conn.close()
            log.info("api: LISTEN new_positions cancelled")
            return
        except Exception as exc:
            log.error("api: new_positions listener error: %s — reconnecting in 5 s", exc)
            if conn is not None:
                await conn.close()
            await asyncio.sleep(5)


async def _listen_config_changed(pool: asyncpg.Pool, cache: LiveCache, dsn: str) -> None:
    """
    LISTEN on config_changed and update the cache's session-gap threshold.
    Uses a dedicated connection to allow clean listener removal on shutdown.
    """
    log.info("api: starting LISTEN config_changed")
    while True:
        conn: Optional[asyncpg.Connection] = None
        try:
            conn = await asyncpg.connect(dsn)

            def _on_config(_conn, _pid, _chan, payload: str) -> None:
                try:
                    data = json.loads(payload)
                    if data.get("key") == "session_gap_threshold_sec":
                        cache.update_session_gap(int(data["value"]))
                        log.info(
                            "api: config_changed session_gap=%s", data["value"]
                        )
                except Exception as exc:
                    log.warning("api: config_changed parse error: %s", exc)

            await conn.add_listener("config_changed", _on_config)
            log.info("api: listening on config_changed")
            while True:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            if conn is not None:
                try:
                    await conn.remove_listener("config_changed", _on_config)
                except Exception:
                    pass
                await conn.close()
            log.info("api: LISTEN config_changed cancelled")
            return
        except Exception as exc:
            log.error("api: config_changed listener error: %s — reconnecting in 5 s", exc)
            if conn is not None:
                await conn.close()
            await asyncio.sleep(5)


async def _broadcast_loop(cache: LiveCache) -> None:
    """
    Every second: expire stale aircraft, then broadcast a DIFFERENTIAL_UPDATE
    to all connected WebSocket clients.
    """
    log.info("api: starting broadcast loop")
    while True:
        try:
            await asyncio.sleep(1.0)
            await cache.expire_stale()
            diff = await cache.snapshot_diff()
            if ws_live.manager.count > 0:
                payload = json.dumps(diff)
                await ws_live.manager.broadcast(payload)
        except asyncio.CancelledError:
            log.info("api: broadcast loop cancelled")
            return
        except Exception as exc:
            log.error("api: broadcast loop error: %s", exc)


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _live_cache

    # 1. DB pool
    pool: asyncpg.Pool = await create_pool()
    app.state.pool = pool

    # 2. Read session gap from pipeline_config
    gap_row = await pool.fetchrow(
        "select value from pipeline_config where key = 'session_gap_threshold_sec'"
    )
    session_gap_sec = int(gap_row["value"]) if gap_row else 300

    # 3. Live cache
    cache = LiveCache(session_gap_sec=session_gap_sec)
    _live_cache = cache
    app.state.live_cache = cache
    await cache.restore(pool)

    # 4–6. Background tasks
    from .db import build_dsn
    dsn = build_dsn()
    tasks = [
        asyncio.create_task(_listen_new_positions(pool, cache, dsn), name="listen-new-positions"),
        asyncio.create_task(_listen_config_changed(pool, cache, dsn), name="listen-config-changed"),
        asyncio.create_task(_broadcast_loop(cache), name="broadcast-loop"),
    ]
    log.info("api: live-state listeners active")

    yield  # application runs here

    # Shutdown
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await pool.close()
    log.info("api: shutdown complete")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    application = FastAPI(
        title="Planegraph API",
        description="ADS-B aviation data platform — REST + WebSocket API",
        version="0.3.0",
        lifespan=lifespan,
    )

    # REST routers
    application.include_router(health.router)
    application.include_router(aircraft.router)
    application.include_router(flights.router)
    application.include_router(analytics.router)
    application.include_router(stats.router)
    application.include_router(airspace.router)
    application.include_router(config.router)

    # WebSocket router
    application.include_router(ws_live.router)

    # Serve compiled frontend if present (WU-04+)
    frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        application.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="spa")
        log.info("api: serving frontend from %s", frontend_dist)

    return application


app = create_app()
