"""A minimal fake Home Assistant websocket server for tests."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import WSMsgType, web

TOKEN = "test-token"


class FakeHA:
    """Speaks enough of HA's websocket API: auth, get_states, subscribe_events."""

    def __init__(self, states: list[dict[str, Any]]) -> None:
        self.states = states
        self.sockets: list[web.WebSocketResponse] = []
        self.subscriptions: dict[web.WebSocketResponse, int] = {}
        self.subscribed = asyncio.Event()
        self.connections = 0

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/api/websocket", self.handler)
        return app

    async def handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        await ws.send_json({"type": "auth_required", "ha_version": "2026.1.0"})
        auth = await ws.receive_json()
        if auth.get("access_token") != TOKEN:
            await ws.send_json({"type": "auth_invalid", "message": "Invalid access token"})
            await ws.close()
            return ws
        await ws.send_json({"type": "auth_ok", "ha_version": "2026.1.0"})
        self.sockets.append(ws)
        async for msg in ws:
            if msg.type is not WSMsgType.TEXT:
                break
            request_msg = msg.json()
            rid, kind = request_msg["id"], request_msg["type"]
            if kind == "get_states":
                await ws.send_json(
                    {"id": rid, "type": "result", "success": True, "result": self.states}
                )
            elif kind == "subscribe_events":
                self.subscriptions[ws] = rid
                await ws.send_json({"id": rid, "type": "result", "success": True, "result": None})
                self.subscribed.set()
        self.sockets.remove(ws)
        self.subscriptions.pop(ws, None)
        return ws

    async def push(self, entity_id: str, new_state: dict[str, Any] | None) -> None:
        """Send a state_changed event to every subscriber."""
        for ws, rid in list(self.subscriptions.items()):
            await ws.send_json(
                {
                    "id": rid,
                    "type": "event",
                    "event": {
                        "event_type": "state_changed",
                        "data": {"entity_id": entity_id, "new_state": new_state},
                    },
                }
            )

    async def drop(self) -> None:
        """Close every client connection (simulates HA restarting)."""
        self.subscribed.clear()
        for ws in list(self.sockets):
            await ws.close()
