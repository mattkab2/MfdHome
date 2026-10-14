"""Breaker symbol: a square with a contact bar, closed (across) or open (swung)."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

SIZE = 40.0
OPEN_RISE = 0.6  # open bar rises 0.6 * SIZE over its run (~31 degrees)


def breaker_box(x: float, y: float) -> Box:
    """Bounding box of a breaker centered at (x, y), in either orientation."""
    half = SIZE / 2
    return Box(x - half, y - half, x + half, y + half)


def breaker(
    x: float,
    y: float,
    closed: bool | None,
    status: Status,
    orientation: Orientation,
    theme: Theme,
) -> str:
    """Render a breaker centered at (x, y).

    ``closed=None`` (unknown) draws the box without a contact bar. Vertical
    breakers are the horizontal symbol rotated 90 degrees about the center.
    """
    half = SIZE / 2
    outline = stroke(status, theme, theme.symbol_stroke_width)
    parts = [
        svg.element(
            "rect",
            {
                "x": x - half,
                "y": y - half,
                "width": SIZE,
                "height": SIZE,
                "fill": "none",
                **outline,
            },
        )
    ]
    if closed is not None:
        end_y = y if closed else y - SIZE * OPEN_RISE
        end_x = x + half if closed else x + half * 0.8
        parts.append(
            svg.element(
                "line",
                {
                    "x1": x - half,
                    "y1": y,
                    "x2": end_x,
                    "y2": end_y,
                    **stroke(status, theme, theme.line_width),
                    "stroke-linecap": "round",
                },
            )
        )
    transform = (
        f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if orientation is Orientation.VERTICAL else None
    )
    return svg.element("g", {"transform": transform}, parts)
