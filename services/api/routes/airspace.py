"""
routes/airspace.py — Reference geometry endpoint.

Returns airports, airspace boundaries, and points of interest as GeoJSON-
enriched records for map initialization.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import asyncpg
from fastapi import APIRouter, Depends

from ..dependencies import get_pool

log = logging.getLogger(__name__)
router = APIRouter()

_AIRPORTS_SQL = """
select
    icao,
    name,
    city,
    lat,
    lon,
    elevation_ft,
    st_asgeojson(geom)::text as geometry
from airports
order by icao
"""

_BOUNDARIES_SQL = """
select
    boundary_id,
    name,
    class as airspace_class,
    floor_ft   as lower_alt_ft,
    ceiling_ft as upper_alt_ft,
    st_asgeojson(geom)::text as geometry
from airspace_boundaries
order by boundary_id
"""

_POIS_SQL = """
select
    poi_id,
    name,
    type,
    lat,
    lon,
    radius_nm,
    st_asgeojson(geom)::text as geometry
from points_of_interest
order by poi_id
"""


def _parse_geom(raw: str | None) -> Dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


@router.get("/api/v1/airspace")
async def get_airspace(pool: asyncpg.Pool = Depends(get_pool)) -> Dict[str, Any]:
    """
    Return all reference geometry needed for map initialization.

    Parameters
    ----------
    pool : asyncpg.Pool
        Injected DB pool.

    Returns
    -------
    dict
        Keys: airports, boundaries, points_of_interest — each a list of records
        with embedded GeoJSON geometry.
    """
    airports_rows = await pool.fetch(_AIRPORTS_SQL)
    boundaries_rows = await pool.fetch(_BOUNDARIES_SQL)
    pois_rows = await pool.fetch(_POIS_SQL)

    airports: List[Dict[str, Any]] = [
        {
            "icao": row["icao"].strip(),
            "name": row["name"],
            "city": row["city"],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "elevation_ft": row["elevation_ft"],
            "geometry": _parse_geom(row["geometry"]),
        }
        for row in airports_rows
    ]

    boundaries: List[Dict[str, Any]] = [
        {
            "boundary_id": row["boundary_id"],
            "name": row["name"],
            "airspace_class": row["airspace_class"],
            "lower_alt_ft": row["lower_alt_ft"],
            "upper_alt_ft": row["upper_alt_ft"],
            "geometry": _parse_geom(row["geometry"]),
        }
        for row in boundaries_rows
    ]

    pois: List[Dict[str, Any]] = [
        {
            "poi_id": row["poi_id"],
            "name": row["name"],
            "type": row["type"],
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "radius_nm": float(row["radius_nm"]),
            "geometry": _parse_geom(row["geometry"]),
        }
        for row in pois_rows
    ]

    return {
        "airports": airports,
        "boundaries": boundaries,
        "points_of_interest": pois,
    }
