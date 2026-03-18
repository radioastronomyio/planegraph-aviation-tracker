"""
sbs_reader.py — Async SBS/BaseStation TCP reader.

Connects to localhost:30003, parses MSG records, maintains per-ICAO
rolling state to merge fields across subtypes, and yields complete
PositionReport objects only after lat, lon, and altitude are known.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

log = logging.getLogger(__name__)

# SBS MSG field indices (0-based after splitting on comma)
F_MSG_TYPE   = 0   # "MSG"
F_SUBTYPE    = 1   # 1-8
F_ICAO       = 4   # hex ident
F_DATE_GEN   = 6
F_TIME_GEN   = 7
F_CALLSIGN   = 10
F_ALT        = 11
F_SPEED      = 12
F_TRACK      = 13
F_LAT        = 14
F_LON        = 15
F_VRATE      = 16
F_SQUAWK     = 17
F_ON_GROUND  = 21  # last field


@dataclass
class PositionReport:
    icao_hex:   str
    report_time: datetime
    lat:        float
    lon:        float
    alt_ft:     Optional[int]   = None
    speed_kts:  Optional[int]   = None
    track:      Optional[float] = None
    vrate_fpm:  Optional[int]   = None
    callsign:   Optional[str]   = None
    squawk:     Optional[str]   = None
    on_ground:  bool            = False


@dataclass
class _IcaoState:
    """Rolling state buffer for one ICAO hex address."""
    lat:        Optional[float] = None
    lon:        Optional[float] = None
    alt_ft:     Optional[int]   = None
    speed_kts:  Optional[int]   = None
    track:      Optional[float] = None
    vrate_fpm:  Optional[int]   = None
    callsign:   Optional[str]   = None
    squawk:     Optional[str]   = None
    on_ground:  bool            = False


def _parse_sbs_line(line: str) -> Optional[PositionReport]:
    """
    Parse one SBS line and return a PositionReport if enough data is present.
    Returns None if the line is not a complete positional MSG record.
    """
    parts = line.split(",")
    if len(parts) < 22:
        return None
    if parts[F_MSG_TYPE] != "MSG":
        return None

    subtype = parts[F_SUBTYPE]
    icao = parts[F_ICAO].strip().upper()
    if not icao:
        return None

    # Parse timestamp from the message-generated date/time fields
    try:
        ts_str = f"{parts[F_DATE_GEN]} {parts[F_TIME_GEN]}"
        report_time = datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S.%f").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        try:
            ts_str = f"{parts[F_DATE_GEN]} {parts[F_TIME_GEN]}"
            report_time = datetime.strptime(ts_str, "%Y/%m/%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            report_time = datetime.now(timezone.utc)

    def _int(s: str) -> Optional[int]:
        s = s.strip()
        return int(float(s)) if s else None

    def _float(s: str) -> Optional[float]:
        s = s.strip()
        return float(s) if s else None

    def _str(s: str) -> Optional[str]:
        s = s.strip()
        return s if s else None

    def _bool(s: str) -> bool:
        return s.strip() == "1"

    # Accumulate state into a per-ICAO dict (returned as partial update dict)
    update: dict = {"icao_hex": icao, "report_time": report_time}

    if subtype == "1":   # ES identification — callsign
        cs = _str(parts[F_CALLSIGN])
        if cs:
            update["callsign"] = cs

    elif subtype == "2":  # Surface position
        lat = _float(parts[F_LAT])
        lon = _float(parts[F_LON])
        spd = _int(parts[F_SPEED])
        trk = _float(parts[F_TRACK])
        og  = _bool(parts[F_ON_GROUND])
        if lat is not None:
            update["lat"] = lat
        if lon is not None:
            update["lon"] = lon
        if spd is not None:
            update["speed_kts"] = spd
        if trk is not None:
            update["track"] = trk
        update["on_ground"] = og

    elif subtype == "3":  # Airborne position — alt, lat, lon
        alt = _int(parts[F_ALT])
        lat = _float(parts[F_LAT])
        lon = _float(parts[F_LON])
        og  = _bool(parts[F_ON_GROUND])
        if alt is not None:
            update["alt_ft"] = alt
        if lat is not None:
            update["lat"] = lat
        if lon is not None:
            update["lon"] = lon
        update["on_ground"] = og

    elif subtype == "4":  # Velocity — speed, track, vrate
        spd   = _int(parts[F_SPEED])
        trk   = _float(parts[F_TRACK])
        vrate = _int(parts[F_VRATE])
        if spd is not None:
            update["speed_kts"] = spd
        if trk is not None:
            update["track"] = trk
        if vrate is not None:
            update["vrate_fpm"] = vrate

    elif subtype == "5":  # Surveillance alt
        alt = _int(parts[F_ALT])
        if alt is not None:
            update["alt_ft"] = alt

    elif subtype == "6":  # Surveillance ID — squawk
        sq = _str(parts[F_SQUAWK])
        if sq:
            update["squawk"] = sq

    elif subtype == "7":  # Air-to-air — altitude
        alt = _int(parts[F_ALT])
        if alt is not None:
            update["alt_ft"] = alt

    elif subtype == "8":  # All-call reply — capture on_ground status
        update["on_ground"] = _bool(parts[F_ON_GROUND])

    else:
        return None

    return update  # type: ignore[return-value]  — partial dict, merged below


class SBSReader:
    """
    Async SBS reader.  Connects to the ultrafeeder TCP socket, merges
    per-ICAO rolling state across subtypes, and yields PositionReport
    objects only when lat, lon, and altitude are all known.
    """

    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._state: dict[str, _IcaoState] = {}

    async def read(self) -> AsyncIterator[PositionReport]:
        """Yields PositionReport objects indefinitely. Reconnects on error."""
        backoff = 1
        while True:
            try:
                reader, _ = await asyncio.open_connection(self._host, self._port)
                log.info("sbs_reader: connected to %s:%d", self._host, self._port)
                backoff = 1
                async for report in self._read_loop(reader):
                    yield report
            except (ConnectionRefusedError, OSError) as exc:
                log.warning(
                    "sbs_reader: connection lost (%s), retrying in %ds", exc, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
            except asyncio.CancelledError:
                raise

    async def _read_loop(self, reader: asyncio.StreamReader) -> AsyncIterator[PositionReport]:
        while True:
            raw = await reader.readline()
            if not raw:
                log.warning("sbs_reader: EOF from ultrafeeder")
                return
            line = raw.decode("ascii", errors="ignore").strip()
            if not line:
                continue

            update = _parse_sbs_line(line)
            if not update or "icao_hex" not in update:
                continue

            icao = update["icao_hex"]
            state = self._state.setdefault(icao, _IcaoState())

            # Merge partial update into rolling state
            if "lat" in update:
                state.lat = update["lat"]
            if "lon" in update:
                state.lon = update["lon"]
            if "alt_ft" in update:
                state.alt_ft = update["alt_ft"]
            if "speed_kts" in update:
                state.speed_kts = update["speed_kts"]
            if "track" in update:
                state.track = update["track"]
            if "vrate_fpm" in update:
                state.vrate_fpm = update["vrate_fpm"]
            if "callsign" in update:
                state.callsign = update["callsign"]
            if "squawk" in update:
                state.squawk = update["squawk"]
            if "on_ground" in update:
                state.on_ground = update["on_ground"]

            # Only emit once we have a valid positional fix
            if state.lat is None or state.lon is None or state.alt_ft is None:
                continue

            yield PositionReport(
                icao_hex=icao,
                report_time=update["report_time"],
                lat=state.lat,
                lon=state.lon,
                alt_ft=state.alt_ft,
                speed_kts=state.speed_kts,
                track=state.track,
                vrate_fpm=state.vrate_fpm,
                callsign=state.callsign,
                squawk=state.squawk,
                on_ground=state.on_ground,
            )
