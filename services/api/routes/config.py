"""
routes/config.py — Pipeline configuration endpoints.

GET  /api/v1/config         — return all pipeline_config entries
PATCH /api/v1/config/{key}  — update a single key; the DB trigger emits
                              config_changed so ingest and materializer react
                              without a restart
"""

from __future__ import annotations

import logging
from typing import Any, List

import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_pool
from ..models.schemas import ConfigEntry, ConfigPatch

log = logging.getLogger(__name__)
router = APIRouter()

_LIST_SQL = "select key, value, updated_at from pipeline_config order by key"

_GET_SQL = "select key, value, updated_at from pipeline_config where key = $1"

_UPSERT_SQL = """
insert into pipeline_config (key, value)
values ($1, $2::jsonb)
on conflict (key)
do update set value = excluded.value
returning key, value, updated_at
"""


@router.get("/api/v1/config", response_model=List[ConfigEntry])
async def list_config(pool: asyncpg.Pool = Depends(get_pool)) -> List[ConfigEntry]:
    """
    Return all pipeline configuration entries.

    Parameters
    ----------
    pool : asyncpg.Pool
        Injected DB pool.

    Returns
    -------
    list of ConfigEntry
    """
    rows = await pool.fetch(_LIST_SQL)
    return [
        ConfigEntry(key=row["key"], value=row["value"], updated_at=row["updated_at"])
        for row in rows
    ]


@router.patch("/api/v1/config/{key}", response_model=ConfigEntry)
async def patch_config(
    key: str,
    body: ConfigPatch,
    pool: asyncpg.Pool = Depends(get_pool),
) -> ConfigEntry:
    """
    Update a single pipeline configuration value.

    The database trigger emits a ``config_changed`` NOTIFY, which the ingest
    daemon and materializer listen on and apply without a restart.

    Parameters
    ----------
    key : str
        Configuration key (must exist in pipeline_config).
    body : ConfigPatch
        JSON body with a ``value`` field.
    pool : asyncpg.Pool
        Injected DB pool.

    Returns
    -------
    ConfigEntry
        The updated configuration entry.

    Raises
    ------
    HTTPException (404)
        When the key does not exist.
    """
    # Validate the key exists before upserting.
    existing = await pool.fetchrow(_GET_SQL, key)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")

    import json as _json
    value_json = _json.dumps(body.value)

    row = await pool.fetchrow(_UPSERT_SQL, key, value_json)
    log.info("config: patched key=%s value=%r", key, body.value)
    return ConfigEntry(key=row["key"], value=row["value"], updated_at=row["updated_at"])
