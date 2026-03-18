"""
partition_manager.py — Daily partition lifecycle manager.

On startup: ensures today's and tomorrow's partitions exist.
Hourly:     ensures tomorrow's partition still exists.
Daily:      calls drop_expired_partitions().
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

import asyncpg

log = logging.getLogger(__name__)

_CREATE_SQL = "select create_daily_partition($1::date)"
_DROP_SQL   = "select drop_expired_partitions()"


class PartitionManager:

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def startup(self) -> None:
        today    = date.today()
        tomorrow = today + timedelta(days=1)
        await self._create(today)
        await self._create(tomorrow)
        log.info("partition_manager: startup partitions ensured for %s and %s", today, tomorrow)

    async def run(self) -> None:
        """Runs indefinitely.  Hourly look-ahead; daily expiry drop."""
        hours_since_drop = 0
        while True:
            await asyncio.sleep(3600)
            tomorrow = date.today() + timedelta(days=1)
            await self._create(tomorrow)
            hours_since_drop += 1
            if hours_since_drop >= 24:
                await self._drop_expired()
                hours_since_drop = 0

    async def _create(self, target: date) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(_CREATE_SQL, target)
        except Exception as exc:
            log.error("partition_manager: create %s failed: %s", target, exc)

    async def _drop_expired(self) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(_DROP_SQL)
            log.info("partition_manager: drop_expired_partitions() called")
        except Exception as exc:
            log.error("partition_manager: drop_expired failed: %s", exc)
