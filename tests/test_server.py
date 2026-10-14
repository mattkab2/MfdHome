"""The display server: pages, live frames, acknowledgement and selection."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestClient

from mfdhome.config import load_config
from mfdhome.mfd import Phase
from mfdhome.model import snapshot_from_ha_states
from mfdhome.server.app import create_app, refresh_loop
from mfdhome.server.runtime import Runtime
from mfdhome.server.store import BoardStore
from tests.support import CONFIG, FIXTURES

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
type ClientFactory = Callable[[web.Application], Awaitable[TestClient[Any, Any]]]


def islanded() -> Runtime:
    runtime = Runtime(load_config(CONFIG))
    items = json.loads((FIXTURES / "electrical_islanded.json").read_text())
    runtime.update(snapshot_from_ha_states(items), T0)
    return runtime


async def test_pages(aiohttp_client: ClientFactory) -> None:
    client = await aiohttp_client(create_app(islanded(), clock=lambda: T0))
    index = await client.get("/")
    assert '<a href="/display/workshop">workshop</a>' in await index.text()
    page = await client.get("/display/workshop")
    html = await page.text()
    assert page.status == 200 and '<body data-display="workshop">' in html
    assert 'data-page="status"' in html and "background: #1d2021" in html
    assert (await client.get("/display/nope")).status == 404
    js = await client.get("/static/client.js")
    assert "function patch" in await js.text()


async def test_display_token(aiohttp_client: ClientFactory) -> None:
    client = await aiohttp_client(create_app(islanded(), display_token="s3cret"))
    assert (await client.get("/display/workshop")).status == 401
    assert (await client.get("/display/workshop?token=wrong")).status == 401
    assert (await client.get("/display/workshop?token=s3cret")).status == 200
    assert (
        'href="/display/hallway?token=s3cret"' in await (await client.get("/?token=s3cret")).text()
    )


async def test_live_frames_ack_and_select(aiohttp_client: ClientFactory) -> None:
    runtime = islanded()
    client = await aiohttp_client(create_app(runtime, clock=lambda: T0))
    workshop = await client.ws_connect("/display/workshop/ws")
    hallway = await client.ws_connect("/display/hallway/ws")
    first = await workshop.receive_json()
    assert first["tiles"]["annunciator.GRID"] == "GRID"
    assert 'id="banner"' in first["svg"] and "GRID POWER LOST" in first["svg"]
    await hallway.receive_json()

    await workshop.send_json({"type": "ack", "system": "GRID"})
    after = await workshop.receive_json()
    assert runtime.board["grid_lost"].phase is Phase.ACTIVE_ACKED
    assert runtime.board["grid_lost"].acked_by == "workshop"
    assert "BATTERY LOW" in after["svg"]  # the banner moves on to the next alert
    assert "BATTERY LOW" in (await hallway.receive_json())["svg"]  # house-wide

    await workshop.send_json({"type": "ack", "target": "banner"})
    final = await workshop.receive_json()
    assert 'id="banner"' not in final["svg"]

    await workshop.send_json({"type": "select", "page": "electrical"})
    selected = await workshop.receive_json()
    assert 'data-page="electrical"' in selected["svg"] and selected["tiles"] == {}
    await hallway.send_json({"type": "select", "page": "status"})  # mirror is fixed
    await workshop.close()
    await hallway.close()
    assert runtime.selected["hallway"] == "electrical"


async def test_refresh_loop_feeds_runtime(aiohttp_client: ClientFactory, tmp_path: Path) -> None:
    runtime = Runtime(load_config(CONFIG), BoardStore(tmp_path / "board.json"))
    app = create_app(runtime, clock=lambda: T0)
    client = await aiohttp_client(app)
    ws = await client.ws_connect("/display/workshop/ws")
    assert 'id="banner"' not in (await ws.receive_json())["svg"]
    items = json.loads((FIXTURES / "electrical_islanded.json").read_text())
    changed = asyncio.Event()
    task = asyncio.create_task(
        refresh_loop(app["hub"], lambda: snapshot_from_ha_states(items), changed, settle=0)
    )
    changed.set()
    frame = await asyncio.wait_for(ws.receive_json(), 2)
    task.cancel()
    assert "GRID POWER LOST" in frame["svg"]
    assert (tmp_path / "board.json").exists()  # board persisted
    await ws.close()
