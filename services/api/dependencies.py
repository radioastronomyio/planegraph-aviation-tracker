"""
dependencies.py — FastAPI dependency injectors.

Provides pool and live_cache accessors via FastAPI's Depends() mechanism.
Both objects are stored on app.state during startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
from fastapi import Request

from .live_state import LiveCache

if TYPE_CHECKING:
    pass


def get_pool(request: Request) -> asyncpg.Pool:
    """Inject the shared asyncpg pool."""
    return request.app.state.pool


def get_live_cache(request: Request) -> LiveCache:
    """Inject the shared in-memory live aircraft cache."""
    return request.app.state.live_cache
