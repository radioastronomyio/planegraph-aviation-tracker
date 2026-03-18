"""
session_manager.py — In-memory flight session manager.

Tracks one FlightSessionState per ICAO hex.  Handles:
  - session creation on first sighting
  - session closure on temporal gap > gap_threshold_sec
  - session split on ground turnaround (GND for > turnaround_threshold_sec
    followed by a non-GND phase)
  - crash-recovery rehydration from the database
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

import asyncpg

from .phase_classifier import PhaseClassifier, make_speed_window, make_vrate_window
from .sbs_reader import PositionReport

log = logging.getLogger(__name__)


@dataclass
class EnrichedReport:
    """A PositionReport enriched with session_id and phase."""
    session_id:  uuid.UUID
    icao_hex:    str
    report_time: datetime
    lat:         float
    lon:         float
    alt_ft:      Optional[int]
    speed_kts:   Optional[int]
    track:       Optional[float]
    vrate_fpm:   Optional[int]
    phase:       str
    squawk:      Optional[str]
    on_ground:   bool
    callsign:    Optional[str]


@dataclass
class FlightSessionState:
    session_id:           uuid.UUID
    icao_hex:             str
    callsign:             Optional[str]
    started_at:           datetime
    last_seen:            datetime
    current_phase:        str              = "UNKNOWN"
    ground_duration_sec:  float            = 0.0
    trajectory_buffer:    List[Tuple]      = field(default_factory=list)
    speed_window:         deque            = field(default_factory=make_speed_window)
    vrate_window:         deque            = field(default_factory=make_vrate_window)
    # last-known values for state merging
    altitude:             Optional[int]    = None
    speed:                Optional[int]    = None
    vrate:                Optional[int]    = None
    track:                Optional[float]  = None
    squawk:               Optional[str]    = None
    on_ground:            bool             = False


class SessionManager:
    """
    Manages all in-flight session state.

    Call `process(report)` for each PositionReport.  Returns:
      - (EnrichedReport, None)         — normal update
      - (EnrichedReport, closed_id)    — report belongs to NEW session after
                                         a split; closed_id is the session
                                         that was closed

    Closed sessions are delivered to the `on_close` callback so the caller
    can persist the session record.
    """

    def __init__(
        self,
        classifier: PhaseClassifier,
        gap_threshold_sec: int,
        turnaround_threshold_sec: int,
        on_close: Optional[Callable[[FlightSessionState], None]] = None,
    ):
        self._classifier              = classifier
        self.gap_threshold_sec        = gap_threshold_sec
        self.turnaround_threshold_sec = turnaround_threshold_sec
        self._on_close                = on_close
        self._sessions: Dict[str, FlightSessionState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, report: PositionReport) -> EnrichedReport:
        icao = report.icao_hex
        now  = report.report_time
        state = self._sessions.get(icao)

        if state is None:
            state = self._new_session(icao, report)
        else:
            elapsed = (now - state.last_seen).total_seconds()
            if elapsed > self.gap_threshold_sec:
                self._close(state)
                state = self._new_session(icao, report)
            else:
                # accumulate ground-dwell time
                if state.current_phase == "GND":
                    state.ground_duration_sec += elapsed

        # Classify phase (updates rolling windows in-place)
        phase = self._classifier.classify(
            alt_ft=report.alt_ft,
            speed_kts=report.speed_kts,
            vrate_fpm=report.vrate_fpm,
            on_ground=report.on_ground,
            speed_window=state.speed_window,
            vrate_window=state.vrate_window,
        )

        # Turnaround / touch-and-go split
        if (
            state.current_phase == "GND"
            and phase not in ("GND", "UNKNOWN")
            and state.ground_duration_sec >= self.turnaround_threshold_sec
        ):
            self._close(state)
            state = self._new_session(icao, report)
            phase = self._classifier.classify(
                alt_ft=report.alt_ft,
                speed_kts=report.speed_kts,
                vrate_fpm=report.vrate_fpm,
                on_ground=report.on_ground,
                speed_window=state.speed_window,
                vrate_window=state.vrate_window,
            )

        # Capture previous phase before overwriting for ground-duration reset
        prev_phase = state.current_phase

        # Update state
        state.last_seen = now
        state.current_phase = phase
        if report.callsign:
            state.callsign = report.callsign
        state.altitude  = report.alt_ft
        state.speed     = report.speed_kts
        state.vrate     = report.vrate_fpm
        state.track     = report.track
        state.squawk    = report.squawk
        state.on_ground = report.on_ground

        # Reset ground-dwell counter on transition INTO GND
        if phase == "GND" and prev_phase != "GND":
            state.ground_duration_sec = 0.0

        state.trajectory_buffer.append(
            (report.lon, report.lat, report.alt_ft or 0, now)
        )

        return EnrichedReport(
            session_id=state.session_id,
            icao_hex=icao,
            report_time=now,
            lat=report.lat,
            lon=report.lon,
            alt_ft=report.alt_ft,
            speed_kts=report.speed_kts,
            track=report.track,
            vrate_fpm=report.vrate_fpm,
            phase=phase,
            squawk=report.squawk,
            on_ground=report.on_ground,
            callsign=state.callsign,
        )

    def reap_stale(self) -> List[uuid.UUID]:
        """
        Close sessions that have not been updated within gap_threshold_sec.
        Returns list of closed session_ids.  Call periodically.
        """
        now    = datetime.now(timezone.utc)
        closed = []
        for icao, state in list(self._sessions.items()):
            if (now - state.last_seen).total_seconds() > self.gap_threshold_sec:
                self._close(state)
                closed.append(state.session_id)
        return closed

    async def rehydrate(self, pool: asyncpg.Pool) -> int:
        """
        On startup, reload open sessions from the DB so we can resume
        without creating duplicate active session records.

        Returns count of sessions reloaded.
        """
        rows = await pool.fetch(
            """
            select session_id, hex, callsign, started_at
            from   flight_sessions
            where  ended_at is null
            """
        )
        count = 0
        for row in rows:
            icao = row["hex"].strip()
            sid  = row["session_id"]
            if icao in self._sessions:
                continue  # already in memory (shouldn't happen on cold start)
            now = datetime.now(timezone.utc)
            state = FlightSessionState(
                session_id  = sid,
                icao_hex    = icao,
                callsign    = row["callsign"],
                started_at  = row["started_at"],
                last_seen   = now,
            )
            self._sessions[icao] = state
            count += 1

        log.info("session_manager: rehydrated %d open sessions", count)
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_session(self, icao: str, report: PositionReport) -> FlightSessionState:
        now   = report.report_time
        state = FlightSessionState(
            session_id = uuid.uuid4(),
            icao_hex   = icao,
            callsign   = report.callsign,
            started_at = now,
            last_seen  = now,
        )
        self._sessions[icao] = state
        return state

    def _close(self, state: FlightSessionState) -> None:
        icao = state.icao_hex
        log.debug(
            "session_manager: closing session %s for %s (phase=%s)",
            state.session_id, icao, state.current_phase,
        )
        self._sessions.pop(icao, None)
        if self._on_close:
            self._on_close(state)
