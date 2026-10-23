"""PNG snapshots for e-paper displays.

An e-paper display polls for its image every ``refresh``. Its image is
rendered when it asks, from values averaged over its window, and carries an
"as of" stamp showing when its content last changed as seen at a fetch (not
the time of the request), so an unchanged page yields the same PNG and the
panel need not redraw. A device that cannot reach the server marks that
itself (see docs/running.md).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from mfdhome.render.panels import PANELS
from mfdhome.render.raster import rasterize
from mfdhome.server.runtime import Runtime
from mfdhome.themes.builtin import THEMES

logger = logging.getLogger(__name__)

#: Fetch intervals remembered per display, to notice a device polling at the wrong rate.
FETCH_HISTORY = 5
#: A device's typical fetch interval may stray this far (as a factor) from ``refresh``.
DRIFT = 2.0


@dataclass(frozen=True)
class Image:
    """A rendered PNG and its entity tag (a hash of the bytes)."""

    png: bytes
    etag: str


def window_text(window: timedelta) -> str:
    """A window as a short label: ``5M``, ``30S``, ``1H``, ``90S``."""
    seconds = round(window.total_seconds())
    for unit, size in (("H", 3600), ("M", 60)):
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}S"


def stamp_text(when: datetime, average: timedelta | None = None) -> str:
    """``"AS OF 14:05"`` in the server's local time; for an averaging display,
    ``"AVG 5M"`` above it, so nobody takes the values for live ones."""
    stamp = f"AS OF {when.astimezone():%H:%M}"
    return stamp if average is None else f"AVG {window_text(average)}\n{stamp}"


class PanelImages:
    """Tracks content changes and caches the current PNG for each e-paper display."""

    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._content: dict[str, str] = {}
        self._changed_at: dict[str, datetime] = {}
        self._image: dict[str, tuple[str, Image]] = {}
        self._fetches: dict[str, deque[datetime]] = {}
        self._drifting: set[str] = set()

    def observe(self, display_id: str, now: datetime) -> None:
        """Note the time if the display's content (the page without its stamp) changed."""
        content = self.runtime.render(display_id, now=now)
        if content != self._content.get(display_id):
            self._content[display_id] = content
            self._changed_at[display_id] = now

    def changed_at(self, display_id: str) -> datetime | None:
        """When the display's content last changed, if it has been observed."""
        return self._changed_at.get(display_id)

    async def image(self, display_id: str, now: datetime) -> Image:
        """The display's current PNG, rasterized only when its SVG changed."""
        self._fetched(display_id, now)
        self.observe(display_id, now)
        display = self.runtime.config.displays[display_id]
        assert display.panel is not None
        stamp = stamp_text(self._changed_at[display_id], display.average)
        svg = self.runtime.render(display_id, stamp, now=now)
        cached = self._image.get(display_id)
        if cached is not None and cached[0] == svg:
            return cached[1]
        background = THEMES[display.theme].background
        png = await asyncio.to_thread(rasterize, svg, PANELS[display.panel], background)
        image = Image(png, hashlib.sha256(png).hexdigest()[:32])
        self._image[display_id] = (svg, image)
        return image

    def _fetched(self, display_id: str, now: datetime) -> None:
        """Warn once when a device's typical fetch interval strays far from its
        ``refresh``: its averages then cover more or less than what it shows.
        The median of recent intervals ignores the extra fetch after a key press.
        """
        refresh = self.runtime.config.displays[display_id].refresh
        fetches = self._fetches.setdefault(display_id, deque(maxlen=FETCH_HISTORY + 1))
        fetches.append(now)
        if refresh is None or len(fetches) <= FETCH_HISTORY:
            return
        typical = statistics.median((b - a).total_seconds() for a, b in pairwise(fetches))
        expected = refresh.total_seconds()
        if expected / DRIFT <= typical <= expected * DRIFT:
            self._drifting.discard(display_id)
        elif display_id not in self._drifting:
            self._drifting.add(display_id)
            logger.warning(
                "display %s fetches about every %.0fs, but its refresh is %.0fs;"
                " set the device's update interval to match",
                display_id,
                typical,
                expected,
            )
