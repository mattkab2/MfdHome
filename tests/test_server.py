"""The display server: pages, live frames, acknowledgement, selection and PNG snapshots."""

import asyncio
import io
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestClient
from PIL import Image

from mfdhome.config import load_config
from mfdhome.mfd import Phase
from mfdhome.model import snapshot_from_ha_states
from mfdhome.render.raster import image_colors
from mfdhome.server.app import create_app, refresh_loop
from mfdhome.server.images import stamp_text
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


async def test_keys_and_lock_enforcement(aiohttp_client: ClientFactory) -> None:
    runtime = islanded()
    client = await aiohttp_client(create_app(runtime, clock=lambda: T0))
    ws = await client.ws_connect("/display/workshop/ws")
    await ws.receive_json()
    await ws.send_json({"type": "key", "key": "4"})  # NEXT
    assert 'data-page="electrical"' in (await ws.receive_json())["svg"]
    await ws.send_json({"type": "key", "key": "3"})  # LOCK
    assert ">LOCKED<" in (await ws.receive_json())["svg"]
    # While locked: keys, acknowledgements and selection are all ignored.
    for message in (
        {"type": "key", "key": "2"},  # ALERTS
        {"type": "ack", "target": "banner"},
        {"type": "ack", "system": "GRID"},
        {"type": "select", "page": "status"},
    ):
        await ws.send_json(message)
    await ws.send_json({"type": "key", "key": "3"})  # unlock
    unlocked = await ws.receive_json()  # the only frame since locking
    assert ">LOCK<" in unlocked["svg"] and 'data-page="electrical"' in unlocked["svg"]
    assert runtime.board["grid_lost"].phase is Phase.ACTIVE_UNACKED
    await ws.close()


async def test_ack_key_is_house_wide(aiohttp_client: ClientFactory) -> None:
    runtime = islanded()
    client = await aiohttp_client(create_app(runtime, clock=lambda: T0))
    workshop = await client.ws_connect("/display/workshop/ws")
    hallway = await client.ws_connect("/display/hallway/ws")
    await workshop.receive_json()
    await hallway.receive_json()
    await workshop.send_json({"type": "key", "key": "2"})  # ACK on the alerts page
    assert "BATTERY LOW" in (await workshop.receive_json())["svg"]
    assert "BATTERY LOW" in (await hallway.receive_json())["svg"]  # banner moved on everywhere
    assert runtime.board["grid_lost"].acked_by == "workshop"
    await workshop.close()
    await hallway.close()


class Clock:
    """A settable clock."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def test_panel_png_and_change_detection(aiohttp_client: ClientFactory) -> None:
    runtime = islanded()
    clock = Clock(T0)
    client = await aiohttp_client(create_app(runtime, clock=clock))
    first = await client.get("/display/main_floor.png")
    assert first.status == 200 and first.content_type == "image/png"
    png = await first.read()
    image = Image.open(io.BytesIO(png))
    assert image.size == (800, 480)
    assert image_colors(image) <= {"#000000", "#ffffff"}  # the mono panel
    etag = first.headers["ETag"]

    # Nothing changed: same image, and a conditional request costs nothing.
    clock.now = T0 + timedelta(minutes=5)
    again = await client.get("/display/main_floor.png")
    assert again.headers["ETag"] == etag and await again.read() == png
    unchanged = await client.get("/display/main_floor.png", headers={"If-None-Match": etag})
    assert unchanged.status == 304 and unchanged.headers["ETag"] == etag

    # A page change is new content, stamped with the time it happened.
    assert (await client.post("/display/main_floor/key/4")).status == 204  # NEXT
    assert runtime.selected["main_floor"] == "electrical"
    changed = await client.get("/display/main_floor.png", headers={"If-None-Match": etag})
    assert changed.status == 200 and changed.headers["ETag"] != etag
    assert client.app["hub"].images.changed_at("main_floor") == clock.now


async def test_panel_routes_reject_bad_requests(aiohttp_client: ClientFactory) -> None:
    client = await aiohttp_client(create_app(islanded(), display_token="s3cret"))
    assert (await client.get("/display/main_floor.png")).status == 401
    assert (await client.post("/display/main_floor/key/4")).status == 401
    assert (await client.get("/display/main_floor.png?token=s3cret")).status == 200
    assert (await client.get("/display/workshop.png?token=s3cret")).status == 404  # no panel
    assert (await client.get("/display/nope.png?token=s3cret")).status == 404
    assert (await client.post("/display/main_floor/key/eject?token=s3cret")).status == 404
    assert (await client.post("/display/main_floor/key/next?token=s3cret")).status == 404


async def test_panel_keys_respect_the_lock(aiohttp_client: ClientFactory) -> None:
    runtime = islanded()
    client = await aiohttp_client(create_app(runtime, clock=lambda: T0))
    await client.post("/display/main_floor/key/3")  # LOCK
    await client.post("/display/main_floor/key/4")
    assert runtime.locked["main_floor"] and runtime.selected["main_floor"] == "status"
    await client.post("/display/main_floor/key/3")
    await client.post("/display/main_floor/key/4")
    assert runtime.selected["main_floor"] == "electrical"


def test_stamp_uses_local_time() -> None:
    assert stamp_text(T0) == f"AS OF {T0.astimezone():%H:%M}"
