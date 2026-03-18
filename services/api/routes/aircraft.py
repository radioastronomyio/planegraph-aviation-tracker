"""
routes/aircraft.py — Live aircraft endpoint.

Reads exclusively from the in-memory LiveCache.  No database query is made.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends

from ..dependencies import get_live_cache
from ..live_state import LiveCache
from ..models.schemas import AircraftRecord

router = APIRouter()


@router.get("/api/v1/aircraft", response_model=List[AircraftRecord])
async def list_aircraft(cache: LiveCache = Depends(get_live_cache)) -> List[AircraftRecord]:
    """
    Return all currently tracked aircraft from the live cache.

    Parameters
    ----------
    cache : LiveCache
        Injected in-memory aircraft cache.

    Returns
    -------
    list of AircraftRecord
        One entry per currently tracked ICAO hex.
    """
    return cache.aircraft_list()
