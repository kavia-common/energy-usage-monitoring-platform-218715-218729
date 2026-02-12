from __future__ import annotations

import asyncio
import json
from typing import Any, Dict
from uuid import UUID

from fastapi import WebSocket


class ConnectionManager:
    """Manage per-user websocket connections and broadcasting."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._connections.pop(user_id, None)

    async def send_json(self, websocket: WebSocket, data: Dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(data, default=str))

    async def broadcast_user(self, user_id: UUID, data: Dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._connections.get(user_id, set()))
        for ws in conns:
            try:
                await self.send_json(ws, data)
            except Exception:
                # Ignore failed sends; client disconnect will be handled on receive loop.
                pass


manager = ConnectionManager()
