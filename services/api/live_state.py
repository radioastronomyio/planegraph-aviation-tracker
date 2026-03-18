"""
live_state.py — In-memory live aircraft cache.

Maintains one mutable record per ICAO hex.  Updated reactively via
PostgreSQL LISTEN new_positions notifications; never polls the database
on a timer.

Cache lifecycle
---------------
1.  restore()       — warm-start from the last N minutes of position_reports
2.  process_notify()— called on each NOTIFY new_positions payload;
                      fetches only rows newer than the last watermark and
                      merges them into the cache
3.  full_state()    — returns a FULL_STATE payload dict (sent once per WS connect)
4.  snapshot_diff() — returns a DIFFERENTIAL_UPDATE payload dict and clears
                      the accumulated dirty / removal sets (called by the
                      broadcast loop every second)
5.  expire_stale()  — removes aircraft last seen beyond the session gap window;
                      may be called before snapshot_diff() to populate removals
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import asyncpg

log = logging.getLogger(__name__)

# Columns returned from position_reports for live cache population.
_FETCH_SQL = """
select
    pr.hex,
    pr.session_id::text,
    fs.callsign,
    pr.lat,
    pr.lon,
    pr.alt_ft,
    pr.track,
    pr.speed_kts,
    pr.vrate_fpm,
    pr.flight_phase,
    pr.squawk,
    pr.on_ground,
    pr.category,
    pr.report_time
from position_reports pr
join flight_sessions fs using (session_id)
where pr.report_time > $1
order by pr.report_time asc
"""

_RESTORE_SQL = """
select distinct on (pr.hex)
    pr.hex,
    pr.session_id::text,
    fs.callsign,
    pr.lat,
    pr.lon,
    pr.alt_ft,
    pr.track,
    pr.speed_kts,
    pr.vrate_fpm,
    pr.flight_phase,
    pr.squawk,
    pr.on_ground,
    pr.category,
    pr.report_time
from position_reports pr
join flight_sessions fs using (session_id)
where pr.report_time > now() - ($1 || ' seconds')::interval
order by pr.hex, pr.report_time desc
"""


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_record(row: asyncpg.Record) -> Dict[str, Any]:
    return {
        "hex": row["hex"].strip(),
        "session_id": row["session_id"],
        "callsign": row["callsign"],
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "alt": row["alt_ft"],
        "track": float(row["track"]) if row["track"] is not None else None,
        "speed": row["speed_kts"],
        "vrate": row["vrate_fpm"],
        "phase": row["flight_phase"] or "UNKNOWN",
        "squawk": row["squawk"],
        "on_ground": row["on_ground"],
        "category": row["category"],
        "last_seen": _fmt_ts(row["report_time"]),
        "_last_seen_dt": row["report_time"],
    }


class LiveCache:
    """
    Thread-safe (asyncio) in-memory live aircraft cache.

    Parameters
    ----------
    session_gap_sec : int
        Aircraft are expired from the cache after this many seconds without
        a new position report.  Mirrors the pipeline_config value.
    """

    def __init__(self, session_gap_sec: int = 300) -> None:
        self._aircraft: Dict[str, Dict[str, Any]] = {}
        self._watermark: Optional[datetime] = None
        self._session_gap_sec: int = session_gap_sec

        # Accumulated since the last snapshot_diff() call.
        self._dirty: Set[str] = set()
        self._removals: List[str] = []

        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def update_session_gap(self, seconds: int) -> None:
        """Called when config_changed delivers a new session_gap_threshold_sec."""
        self._session_gap_sec = seconds
        log.info("live_cache: session_gap updated to %d s", seconds)

    # ------------------------------------------------------------------
    # Startup warm-restore
    # ------------------------------------------------------------------

    async def restore(self, pool: asyncpg.Pool) -> int:
        """
        Populate the cache from recent position_reports at startup.

        Returns the number of aircraft loaded.
        """
        rows = await pool.fetch(_RESTORE_SQL, str(self._session_gap_sec))
        async with self._lock:
            for row in rows:
                record = _row_to_record(row)
                hex_ = record["hex"]
                self._aircraft[hex_] = record
                # Watermark = most recent report seen
                rt: datetime = row["report_time"]
                if self._watermark is None or rt > self._watermark:
                    self._watermark = rt
            count = len(self._aircraft)
        log.info("live_cache: restored %d aircraft from DB", count)
        return count

    # ------------------------------------------------------------------
    # Notification handler
    # ------------------------------------------------------------------

    async def process_notify(self, pool: asyncpg.Pool, payload: str) -> None:
        """
        Handle a NOTIFY new_positions event.

        Fetches all rows newer than the current watermark, merges them into
        the cache, and updates the watermark.
        """
        import json

        try:
            data = json.loads(payload)
        except Exception:
            log.warning("live_cache: bad notify payload: %r", payload)
            return

        since = self._watermark or datetime.fromtimestamp(0, tz=timezone.utc)

        try:
            rows = await pool.fetch(_FETCH_SQL, since)
        except Exception as exc:
            log.error("live_cache: fetch after notify failed: %s", exc)
            return

        if not rows:
            return

        async with self._lock:
            new_watermark = self._watermark
            for row in rows:
                record = _row_to_record(row)
                hex_ = record["hex"]
                self._aircraft[hex_] = record
                self._dirty.add(hex_)
                rt: datetime = row["report_time"]
                if new_watermark is None or rt > new_watermark:
                    new_watermark = rt
            self._watermark = new_watermark

        log.debug("live_cache: merged %d rows, watermark=%s", len(rows), new_watermark)

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    async def expire_stale(self) -> List[str]:
        """
        Remove aircraft not updated within session_gap_sec.

        Returns a list of expired ICAO hex codes.
        """
        now = datetime.now(timezone.utc)
        expired: List[str] = []

        async with self._lock:
            for hex_, record in list(self._aircraft.items()):
                last_dt: datetime = record["_last_seen_dt"]
                # Ensure timezone-aware comparison
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                elapsed = (now - last_dt).total_seconds()
                if elapsed > self._session_gap_sec:
                    del self._aircraft[hex_]
                    expired.append(hex_)
                    self._removals.append(hex_)

        if expired:
            log.debug("live_cache: expired %d stale aircraft: %s", len(expired), expired)
        return expired

    # ------------------------------------------------------------------
    # WebSocket payload generators
    # ------------------------------------------------------------------

    async def full_state(self) -> Dict[str, Any]:
        """Return a FULL_STATE payload dict."""
        async with self._lock:
            aircraft = {
                hex_: _public_record(rec)
                for hex_, rec in self._aircraft.items()
            }
        return {
            "type": "FULL_STATE",
            "timestamp": time.time(),
            "aircraft": aircraft,
        }

    async def snapshot_diff(self) -> Dict[str, Any]:
        """
        Return a DIFFERENTIAL_UPDATE payload and clear the dirty / removal sets.

        Safe to call even when there are no changes — the result will have
        empty updates and removals.
        """
        async with self._lock:
            updates = {
                hex_: _public_record(self._aircraft[hex_])
                for hex_ in self._dirty
                if hex_ in self._aircraft
            }
            removals = list(self._removals)
            self._dirty.clear()
            self._removals.clear()

        return {
            "type": "DIFFERENTIAL_UPDATE",
            "timestamp": time.time(),
            "updates": updates,
            "removals": removals,
        }

    # ------------------------------------------------------------------
    # Sync read-only accessors (no lock — read under GIL is safe for dict)
    # ------------------------------------------------------------------

    def aircraft_list(self) -> List[Dict[str, Any]]:
        """Return all current aircraft records as a list (no internal state)."""
        return [_public_record(rec) for rec in self._aircraft.values()]

    def aircraft_count(self) -> int:
        return len(self._aircraft)

    def watermark(self) -> Optional[datetime]:
        return self._watermark


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _public_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal keys (prefixed with _) before sending over the wire."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}
