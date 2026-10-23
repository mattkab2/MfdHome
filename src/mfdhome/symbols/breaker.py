"""Breaker symbols: a square with a contact bar, closed (across) or open (swung).

A smart breaker (remotely switched, such as a battery system's smart circuit)
adds an actuator: a small box below the bar, linked to it by a stem.
"""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

SIZE = 40.0
OPEN_RISE = 0.6  # open bar rises 0.6 * SIZE over its run (~31 degrees)
ACTUATOR_WIDTH = 12.0
ACTUATOR_HEIGHT = 8.0
ACTUATOR_GAP = 8.0  # from the bar to the top of the actuator box


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
    actuator: bool = False,
) -> str:
    """Render a breaker centered at (x, y).

    ``closed=None`` (unknown) draws the box without a contact bar. Vertical
    breakers are the horizontal symbol rotated 90 degrees about the center.
    ``actuator`` draws the smart-breaker mark, which stays in every state.
    """
    half = SIZE / 2
    outline = stroke(status, theme, theme.symbol_stroke_width)
    parts = [svg.rect(x - half, y - half, SIZE, SIZE, {"fill": "none", **outline})]
    if closed is not None:
        end_y = y if closed else y - SIZE * OPEN_RISE
        end_x = x + half if closed else x + half * 0.8
        parts.append(
            svg.line(
                x - half,
                y,
                end_x,
                end_y,
                {**stroke(status, theme, theme.line_width), "stroke-linecap": "round"},
            )
        )
    if actuator:
        top = y + ACTUATOR_GAP
        parts.append(svg.line(x, y, x, top, outline))
        parts.append(
            svg.rect(
                x - ACTUATOR_WIDTH / 2,
                top,
                ACTUATOR_WIDTH,
                ACTUATOR_HEIGHT,
                {"fill": "none", **outline},
            )
        )
    transform = (
        f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if orientation is Orientation.VERTICAL else None
    )
    return svg.element("g", {"transform": transform}, parts)
