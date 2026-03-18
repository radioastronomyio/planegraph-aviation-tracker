"""
ws/live.py — WebSocket endpoint for live aircraft position streaming.

Protocol
--------
- On connect   : one FULL_STATE frame is sent immediately.
- Every second : one DIFFERENTIAL_UPDATE frame is sent when there are changes.
                 If there are no changes the frame is still sent (empty updates
                 and removals) so the client can use it as a heartbeat.

Wire format: JSON only.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..live_state import LiveCache

log = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Tracks all active WebSocket connections and provides broadcast."""

    def __init__(self) -> None:
        self._active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)
        log.debug("ws: client connected, total=%d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        log.debug("ws: client disconnected, total=%d", len(self._active))

    async def broadcast(self, payload: str) -> None:
        """Send payload to all connected clients; silently drop dead connections."""
        dead: Set[WebSocket] = set()
        for ws in list(self._active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self._active -= dead

    @property
    def count(self) -> int:
        return len(self._active)


# Module-level singleton — shared with the broadcast loop in main.py.
manager = ConnectionManager()


@router.websocket("/api/v1/live")
async def live_feed(ws: WebSocket) -> None:
    """
    WebSocket endpoint for live aircraft positions.

    Sends FULL_STATE immediately on connection, then participates in the
    server-wide broadcast loop for DIFFERENTIAL_UPDATE frames.
    """
    await manager.connect(ws)
    # Import here to avoid circular dependency at module load time.
    from ..main import get_live_cache_from_app

    live_cache: LiveCache = get_live_cache_from_app()

    try:
        # Send initial full state.
        full = await live_cache.full_state()
        await ws.send_text(json.dumps(full))

        # Keep connection alive until the client disconnects.
        while True:
            try:
                # We don't process incoming messages but we must await
                # to detect client disconnection.
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # No message from client — just continue.
                pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("ws: connection error: %s", exc)
    finally:
        manager.disconnect(ws)
