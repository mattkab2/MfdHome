"""The display server: an HTML shell per display and a WebSocket of live frames.

Browsers only ever receive rendered SVG: the HA token stays in this process.
An optional shared display token (``MFD_DISPLAY_TOKEN``) gates every route.
Run it on the local network only.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
from collections import defaultdict
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from html import escape
from importlib.resources import files
from typing import Any

import aiohttp
from aiohttp import WSMsgType, web

from mfdhome.config.load import load_config
from mfdhome.mfd.alerts import most_urgent
from mfdhome.model.page import Element, GroupElement, TileElement
from mfdhome.model.state import StateSnapshot
from mfdhome.server.runtime import Runtime
from mfdhome.server.store import BoardStore
from mfdhome.sources.ha import HomeAssistant
from mfdhome.themes.builtin import THEMES

logger = logging.getLogger(__name__)

type Clock = Callable[[], datetime]

CLIENT_JS = files("mfdhome.server").joinpath("static/client.js").read_text(encoding="utf-8")

SHELL = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
html, body {{ margin: 0; height: 100%; background: {background}; overflow: hidden; }}
#screen, #screen svg {{ width: 100vw; height: 100vh; display: block; }}
body.offline::after {{ content: "OFFLINE"; position: fixed; top: 8px; right: 12px;
  font: 14px monospace; color: #928374; }}
</style></head>
<body data-display="{display}"><div id="screen">{svg}</div>
<script src="/static/client.js"></script></body></html>
"""


def _now() -> datetime:
    return datetime.now(UTC)


def _tiles(elements: tuple[Element, ...]) -> Iterator[tuple[str, str]]:
    for element in elements:
        if isinstance(element, TileElement):
            yield element.id, element.system
        elif isinstance(element, GroupElement):
            yield from _tiles(element.items)


class Hub:
    """Connected displays: re-renders and pushes frames when something changes."""

    def __init__(self, runtime: Runtime, clock: Clock = _now) -> None:
        self.runtime = runtime
        self.clock = clock
        self.sockets: defaultdict[str, set[web.WebSocketResponse]] = defaultdict(set)
        self.last: dict[str, str] = {}

    def frame(self, display_id: str) -> dict[str, Any]:
        """The message a display should show now: its SVG and its tile map."""
        page = self.runtime.config.pages[self.runtime.selected[display_id]]
        return {
            "type": "frame",
            "svg": self.runtime.render(display_id),
            "tiles": dict(_tiles(page.elements)),
        }

    async def push(self, display_ids: list[str] | None = None, force: bool = False) -> None:
        """Send a fresh frame to each connected display whose SVG changed."""
        for display_id in display_ids or list(self.sockets):
            sockets = self.sockets.get(display_id)
            if not sockets:
                continue
            frame = self.frame(display_id)
            if not force and frame["svg"] == self.last.get(display_id):
                continue
            self.last[display_id] = frame["svg"]
            for ws in list(sockets):
                await ws.send_json(frame)

    async def handle(self, display_id: str, message: dict[str, Any]) -> None:
        """Apply a message from a display: acknowledge, or select a page."""
        now = self.clock()
        if message.get("type") == "ack":
            if message.get("target") == "banner":
                alert = most_urgent(self.runtime.board, self.runtime.config.alerts.alerts)
                changed = alert is not None and self.runtime.acknowledge(
                    display_id, now, ids=[alert.id]
                )
            elif isinstance(system := message.get("system"), str):
                changed = self.runtime.acknowledge(display_id, now, system=system)
            else:
                changed = False
            if changed:
                logger.info("display %s acknowledged %s", display_id, message)
                await self.push()  # acknowledgement is house-wide
        elif message.get("type") == "select" and isinstance(page := message.get("page"), str):
            if self.runtime.select(display_id, page):
                await self.push([display_id])


async def _favicon(_request: web.Request) -> web.Response:
    return web.Response(status=204)


def create_app(
    runtime: Runtime, display_token: str | None = None, clock: Clock = _now
) -> web.Application:
    """The web app for ``runtime``. ``app["hub"]`` is the :class:`Hub`."""
    hub = Hub(runtime, clock)

    def authorized(request: web.Request) -> None:
        given = request.query.get("token", "")
        if display_token and not hmac.compare_digest(given, display_token):
            raise web.HTTPUnauthorized(text="display token required")

    def display_of(request: web.Request) -> str:
        authorized(request)
        display_id = request.match_info["display"]
        if display_id not in runtime.config.displays:
            raise web.HTTPNotFound(text=f"no display {display_id!r}")
        return display_id

    async def index(request: web.Request) -> web.Response:
        authorized(request)
        query = f"?token={escape(request.query['token'])}" if display_token else ""
        links = "".join(
            f'<li><a href="/display/{escape(d)}{query}">{escape(d)}</a></li>'
            for d in runtime.config.displays
        )
        return web.Response(text=f"<!doctype html><ul>{links}</ul>", content_type="text/html")

    async def page(request: web.Request) -> web.Response:
        display_id = display_of(request)
        display = runtime.config.displays[display_id]
        html = SHELL.format(
            title=escape(display_id),
            display=escape(display_id),
            background=THEMES[display.theme].background,
            svg=runtime.render(display_id),
        )
        return web.Response(text=html, content_type="text/html")

    async def socket(request: web.Request) -> web.WebSocketResponse:
        display_id = display_of(request)
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        hub.sockets[display_id].add(ws)
        try:
            await ws.send_json(hub.frame(display_id))
            async for msg in ws:
                if msg.type is not WSMsgType.TEXT:
                    break
                try:
                    message = msg.json()
                except ValueError:
                    continue
                if isinstance(message, dict):
                    await hub.handle(display_id, message)
        finally:
            hub.sockets[display_id].discard(ws)
        return ws

    async def client_js(_request: web.Request) -> web.Response:
        return web.Response(text=CLIENT_JS, content_type="application/javascript")

    app = web.Application()
    app["hub"] = hub
    app.router.add_get("/", index)
    app.router.add_get("/display/{display}", page)
    app.router.add_get("/display/{display}/ws", socket)
    app.router.add_get("/static/client.js", client_js)
    app.router.add_get("/favicon.ico", _favicon)
    return app


async def refresh_loop(
    hub: Hub,
    snapshot: Callable[[], StateSnapshot],
    changed: asyncio.Event,
    tick: float = 30.0,
    settle: float = 0.2,
) -> None:
    """Feed the runtime and push frames after HA changes and every ``tick`` seconds.

    Changes are coalesced over ``settle`` seconds. The periodic tick catches
    entities going stale, which produces no event.
    """
    while True:
        try:
            await asyncio.wait_for(changed.wait(), tick)
            await asyncio.sleep(settle)
        except TimeoutError:
            pass
        changed.clear()
        hub.runtime.update(snapshot(), hub.clock())
        await hub.push()


async def serve(
    config_dir: str,
    ha_url: str,
    ha_token: str,
    *,
    host: str = "0.0.0.0",
    port: int = 8099,
    board_path: str = "var/board.json",
    display_token: str | None = None,
) -> None:
    """Run everything: HA client, runtime, refresh loop and web server."""
    runtime = Runtime(load_config(config_dir), BoardStore(board_path))
    app = create_app(runtime, display_token)
    runner = web.AppRunner(app)
    await runner.setup()
    changed = asyncio.Event()

    async def on_change(_ids: frozenset[str] | None) -> None:
        changed.set()

    async with aiohttp.ClientSession() as session:
        ha = HomeAssistant(ha_url, ha_token, session)
        await web.TCPSite(runner, host, port).start()
        logger.info("serving %d displays on http://%s:%d", len(runtime.config.displays), host, port)
        try:
            await asyncio.gather(
                ha.run(on_change), refresh_loop(app["hub"], lambda: ha.snapshot, changed)
            )
        finally:
            await runner.cleanup()
