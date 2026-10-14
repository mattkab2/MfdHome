"""PNG snapshots for e-paper displays.

An e-paper display polls for its image. The image carries an "as of" stamp
showing when its content last changed (not the time of the request), so an
unchanged page yields the same PNG and the panel need not redraw. A device
that cannot reach the server marks that itself (see docs/running.md).
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime

from mfdhome.render.panels import PANELS
from mfdhome.render.raster import rasterize
from mfdhome.server.runtime import Runtime
from mfdhome.themes.builtin import THEMES


@dataclass(frozen=True)
class Image:
    """A rendered PNG and its entity tag (a hash of the bytes)."""

    png: bytes
    etag: str


def stamp_text(when: datetime) -> str:
    """``"AS OF 14:05"``, in the server's local time."""
    return f"AS OF {when.astimezone():%H:%M}"


class PanelImages:
    """Tracks content changes and caches the current PNG for each e-paper display."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._content: dict[str, str] = {}
        self._changed_at: dict[str, datetime] = {}
        self._image: dict[str, tuple[str, Image]] = {}

    def panels(self) -> list[str]:
        """Ids of the displays that have a panel."""
        return [d.id for d in self.runtime.config.displays.values() if d.panel is not None]

    def observe(self, now: datetime, display_ids: list[str] | None = None) -> None:
        """Note the time for each display whose content (the page without its stamp) changed."""
        for display_id in display_ids if display_ids is not None else self.panels():
            content = self.runtime.render(display_id)
            if content != self._content.get(display_id):
                self._content[display_id] = content
                self._changed_at[display_id] = now

    def changed_at(self, display_id: str) -> datetime | None:
        """When the display's content last changed, if it has been observed."""
        return self._changed_at.get(display_id)

    async def image(self, display_id: str, now: datetime) -> Image:
        """The display's current PNG, rasterized only when its SVG changed."""
        self.observe(now, [display_id])
        display = self.runtime.config.displays[display_id]
        assert display.panel is not None
        svg = self.runtime.render(display_id, stamp_text(self._changed_at[display_id]))
        cached = self._image.get(display_id)
        if cached is not None and cached[0] == svg:
            return cached[1]
        background = THEMES[display.theme].background
        png = await asyncio.to_thread(rasterize, svg, PANELS[display.panel], background)
        image = Image(png, hashlib.sha256(png).hexdigest()[:32])
        self._image[display_id] = (svg, image)
        return image
