"""Home Assistant client: a live state snapshot over HA's websocket API.

This is the only module that talks to Home Assistant. It keeps an in-memory
snapshot current and tells the caller which entities changed; everything else
works on snapshots. While disconnected the snapshot is empty, so every bound
element renders as unavailable rather than showing old values.

The access token is only ever sent in the auth message: it is never logged and
never leaves this process.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import aiohttp

from mfdhome.model.state import EntityState, StateSnapshot, snapshot_from_ha_states

logger = logging.getLogger(__name__)

#: Called with the entity ids that changed (``None``: the whole snapshot was replaced).
type OnChange = Callable[[frozenset[str] | None], Awaitable[None]]


class AuthError(Exception):
    """Home Assistant rejected the access token."""


class ProtocolError(Exception):
    """Home Assistant sent something unexpected."""


def websocket_url(base_url: str) -> str:
    """``http://host:8123`` -> ``ws://host:8123/api/websocket`` (https -> wss)."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base.removeprefix("https://")
    elif base.startswith("http://"):
        base = "ws://" + base.removeprefix("http://")
    return base + "/api/websocket"


class HomeAssistant:
    """A reconnecting connection to Home Assistant that mirrors entity states.

    ``snapshot`` is always safe to read: a fresh dict is swapped in on change,
    never mutated in place.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        session: aiohttp.ClientSession,
        *,
        min_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ) -> None:
        self.url = websocket_url(base_url)
        self._token = token
        self._session = session
        self._min_backoff = min_backoff
        self._max_backoff = max_backoff
        self._states: dict[str, EntityState] = {}
        self.connected = False

    def __repr__(self) -> str:  # never show the token
        return f"HomeAssistant(url={self.url!r}, connected={self.connected})"

    @property
    def snapshot(self) -> StateSnapshot:
        """The current entity states (empty while disconnected)."""
        return self._states

    async def run(self, on_change: OnChange) -> None:
        """Mirror HA forever, reconnecting with exponential backoff.

        Returns only by cancellation; raises ``AuthError`` if the token is
        rejected (retrying would not help).
        """
        backoff = self._min_backoff
        while True:
            try:
                await self._session_loop(on_change)
                backoff = self._min_backoff  # clean close: reconnect promptly
            except AuthError:
                raise
            except (aiohttp.ClientError, ProtocolError, TimeoutError, ValueError) as exc:
                logger.warning("Home Assistant connection to %s lost: %s", self.url, exc)
            if self.connected or self._states:
                self.connected = False
                self._states = {}
                await on_change(None)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._max_backoff)

    async def states_once(self) -> StateSnapshot:
        """Connect, fetch every state once, and disconnect (for CLI commands)."""
        async with self._session.ws_connect(self.url) as ws:
            await self._authenticate(ws)
            await ws.send_json({"id": 1, "type": "get_states"})
            return snapshot_from_ha_states(await self._result(ws, 1))

    async def _session_loop(self, on_change: OnChange) -> None:
        async with self._session.ws_connect(self.url, heartbeat=30) as ws:
            await self._authenticate(ws)
            logger.info("connected to Home Assistant at %s", self.url)
            # Subscribe before fetching, so no change can slip between the two.
            await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
            await ws.send_json({"id": 2, "type": "get_states"})
            async for msg in ws:
                if msg.type is not aiohttp.WSMsgType.TEXT:
                    break
                await self._handle(msg.json(), on_change)

    async def _handle(self, message: Mapping[str, Any], on_change: OnChange) -> None:
        kind = message.get("type")
        if kind == "result":
            if not message.get("success"):
                raise ProtocolError(f"request {message.get('id')} failed: {message.get('error')}")
            if message.get("id") == 2:
                self._states = dict(snapshot_from_ha_states(message.get("result") or []))
                self.connected = True
                await on_change(None)
        elif kind == "event":
            data = (message.get("event") or {}).get("data") or {}
            entity_id = data.get("entity_id")
            if not isinstance(entity_id, str):
                return
            states = dict(self._states)
            new_state = data.get("new_state")
            if new_state is None:
                states.pop(entity_id, None)  # entity removed
            else:
                states.update(snapshot_from_ha_states([new_state]))
            self._states = states
            await on_change(frozenset({entity_id}))

    async def _authenticate(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        hello = await ws.receive_json()
        if hello.get("type") != "auth_required":
            raise ProtocolError(f"expected auth_required, got {hello.get('type')!r}")
        await ws.send_json({"type": "auth", "access_token": self._token})
        reply = await ws.receive_json()
        if reply.get("type") == "auth_invalid":
            raise AuthError(reply.get("message") or "access token rejected")
        if reply.get("type") != "auth_ok":
            raise ProtocolError(f"expected auth_ok, got {reply.get('type')!r}")

    @staticmethod
    async def _result(ws: aiohttp.ClientWebSocketResponse, request_id: int) -> Any:
        while True:
            message = await ws.receive_json()
            if message.get("type") == "result" and message.get("id") == request_id:
                if not message.get("success"):
                    raise ProtocolError(f"request failed: {message.get('error')}")
                return message.get("result")
