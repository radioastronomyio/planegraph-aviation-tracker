"""
db.py — asyncpg connection pool factory.

Creates a single shared pool for the API process.  The pool is initialized
on application startup and closed on shutdown via the FastAPI lifespan handler.
"""

from __future__ import annotations

import os

import asyncpg


def build_dsn() -> str:
    """Construct a DSN from environment variables."""
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ["POSTGRES_DB"]
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


async def create_pool() -> asyncpg.Pool:
    """Create and return an asyncpg connection pool."""
    return await asyncpg.create_pool(
        dsn=build_dsn(),
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
