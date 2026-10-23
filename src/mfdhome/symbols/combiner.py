"""Combiner symbol: several branch inputs, each through a small breaker, onto one bus."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

LENGTH = 60.0  # along the conductor (inputs to output)
DEPTH = 80.0  # across it (the side the inputs share)
MAX_INPUTS = 4
BUS_U = 10.0  # bus bar position along the conductor, from the center
MARK_U = -10.0  # branch breaker marks
MARK_LENGTH = 10.0
MARK_DEPTH = 8.0


def combiner_box(x: float, y: float, orientation: Orientation) -> Box:
    """Bounding box of a combiner centered at (x, y)."""
    w, h = (DEPTH, LENGTH) if orientation is Orientation.VERTICAL else (LENGTH, DEPTH)
    return Box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def input_offsets(inputs: int) -> list[float]:
    """Offsets of the inputs across the conductor, evenly spaced, first on top (or right)."""
    step = DEPTH / inputs
    return [-DEPTH / 2 + (i + 0.5) * step for i in range(inputs)]


def _place(x: float, y: float, orientation: Orientation, u: float, v: float) -> Point:
    """Local (along ``u``, across ``v``) to canvas; vertical is rotated 90 degrees clockwise."""
    return (x - v, y + u) if orientation is Orientation.VERTICAL else (x + u, y + v)


def input_port(x: float, y: float, orientation: Orientation, inputs: int, index: int) -> Port:
    """Input ``index`` (0-based): on the left edge, or the top edge when vertical."""
    point = _place(x, y, orientation, -LENGTH / 2, input_offsets(inputs)[index])
    direction = (0.0, -1.0) if orientation is Orientation.VERTICAL else (-1.0, 0.0)
    return Port(point, direction)


def output_port(x: float, y: float, orientation: Orientation) -> Port:
    """The output: right edge center, or bottom center when vertical."""
    direction = (0.0, 1.0) if orientation is Orientation.VERTICAL else (1.0, 0.0)
    return Port(_place(x, y, orientation, LENGTH / 2, 0.0), direction)


def combiner(
    x: float, y: float, inputs: int, status: Status, orientation: Orientation, theme: Theme
) -> str:
    """Render a combiner with ``inputs`` branch circuits centered at (x, y)."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    box = combiner_box(x, y, orientation)
    parts = [
        svg.rect(
            box.left,
            box.top,
            box.right - box.left,
            box.bottom - box.top,
            {"fill": "none", **outline},
        )
    ]

    def line(u1: float, v1: float, u2: float, v2: float) -> str:
        (x1, y1), (x2, y2) = (_place(x, y, orientation, u1, v1), _place(x, y, orientation, u2, v2))
        return svg.line(x1, y1, x2, y2, outline)

    offsets = input_offsets(inputs)
    for v in offsets:
        parts.append(line(-LENGTH / 2, v, BUS_U, v))
        cx, cy = _place(x, y, orientation, MARK_U, v)
        w, h = (
            (MARK_DEPTH, MARK_LENGTH)
            if orientation is Orientation.VERTICAL
            else (MARK_LENGTH, MARK_DEPTH)
        )
        parts.append(svg.rect(cx - w / 2, cy - h / 2, w, h, {"fill": "none", **outline}))
    parts.append(line(BUS_U, min(offsets[0], 0.0), BUS_U, max(offsets[-1], 0.0)))
    parts.append(line(BUS_U, 0.0, LENGTH / 2, 0.0))
    return "".join(parts)
