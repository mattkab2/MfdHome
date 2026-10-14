"""The Home Assistant client against a fake HA server."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer

from mfdhome.sources.ha import AuthError, HomeAssistant, websocket_url
from tests.fake_ha import TOKEN, FakeHA

STATES = [
    {"entity_id": "sensor.grid_power", "state": "300", "attributes": {"unit_of_measurement": "W"}},
    {"entity_id": "switch.main_breaker", "state": "on", "attributes": {}},
]

type ServerFactory = Callable[[Any], Awaitable[TestServer]]


def test_websocket_url() -> None:
    assert websocket_url("http://ha.local:8123/") == "ws://ha.local:8123/api/websocket"
    assert websocket_url("https://ha.example") == "wss://ha.example/api/websocket"


class Recorder:
    def __init__(self) -> None:
        self.calls: list[frozenset[str] | None] = []
        self.event = asyncio.Event()

    async def __call__(self, changed: frozenset[str] | None) -> None:
        self.calls.append(changed)
        self.event.set()

    async def wait(self) -> frozenset[str] | None:
        await asyncio.wait_for(self.event.wait(), 2)
        self.event.clear()
        return self.calls[-1]


async def start(
    aiohttp_server: ServerFactory, fake: FakeHA, token: str = TOKEN
) -> tuple[HomeAssistant, aiohttp.ClientSession]:
    server = await aiohttp_server(fake.app())
    session = aiohttp.ClientSession()
    client = HomeAssistant(str(server.make_url("")), token, session, min_backoff=0.01)
    return client, session


async def test_mirrors_states_and_changes(aiohttp_server: ServerFactory) -> None:
    fake = FakeHA(list(STATES))
    client, session = await start(aiohttp_server, fake)
    seen = Recorder()
    task = asyncio.create_task(client.run(seen))
    try:
        assert await seen.wait() is None  # initial full snapshot
        assert client.connected
        assert client.snapshot["sensor.grid_power"].state == "300"

        await asyncio.wait_for(fake.subscribed.wait(), 2)
        await fake.push("sensor.grid_power", {"entity_id": "sensor.grid_power", "state": "-50"})
        assert await seen.wait() == frozenset({"sensor.grid_power"})
        assert client.snapshot["sensor.grid_power"].state == "-50"

        await fake.push("switch.main_breaker", None)  # entity removed
        assert await seen.wait() == frozenset({"switch.main_breaker"})
        assert "switch.main_breaker" not in client.snapshot
    finally:
        task.cancel()
        await session.close()


async def test_disconnect_empties_snapshot_then_reconnects(aiohttp_server: ServerFactory) -> None:
    fake = FakeHA(list(STATES))
    client, session = await start(aiohttp_server, fake)
    seen = Recorder()
    task = asyncio.create_task(client.run(seen))
    try:
        await seen.wait()
        await asyncio.wait_for(fake.subscribed.wait(), 2)
        await fake.drop()
        assert await seen.wait() is None
        assert client.snapshot == {} and not client.connected  # everything unavailable
        assert await seen.wait() is None  # reconnected: fresh snapshot
        assert client.connected and "sensor.grid_power" in client.snapshot
        assert fake.connections == 2
    finally:
        task.cancel()
        await session.close()


async def test_rejected_token_stops(aiohttp_server: ServerFactory) -> None:
    client, session = await start(aiohttp_server, FakeHA(STATES), token="wrong")
    try:
        with pytest.raises(AuthError, match="Invalid access token"):
            await asyncio.wait_for(client.run(Recorder()), 2)
    finally:
        await session.close()


async def test_states_once_and_repr_hides_token(aiohttp_server: ServerFactory) -> None:
    client, session = await start(aiohttp_server, FakeHA(STATES))
    try:
        snap = await client.states_once()
        assert set(snap) == {"sensor.grid_power", "switch.main_breaker"}
        assert TOKEN not in repr(client)
    finally:
        await session.close()
