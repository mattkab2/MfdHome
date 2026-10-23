"""Inline water fittings: check valve, backflow preventer, pressure reducing valve.

These are self-acting (no power, usually no sensors), so they bind nothing by
default; status rules can still color them. All run left to right (top to
bottom when vertical) and are rotated as a whole.
"""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.symbols.valve import HEIGHT as VALVE_HEIGHT
from mfdhome.symbols.valve import LENGTH as VALVE_LENGTH
from mfdhome.themes.theme import Theme

CHECK_LENGTH = 32.0
CHECK_HEIGHT = 24.0
CHECK_HALF = 10.0  # the triangle's half height and half length
BFP_LENGTH = 64.0
BFP_HEIGHT = 28.0
DOME_RADIUS = 8.0
DOME_STEM = 6.0
#: How far the PRV's dome reaches above the valve body.
DOME_REACH = DOME_STEM + DOME_RADIUS


def _box(x: float, y: float, orientation: Orientation, length: float, height: float) -> Box:
    w, h = (height, length) if orientation is Orientation.VERTICAL else (length, height)
    return Box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def check_box(x: float, y: float, orientation: Orientation) -> Box:
    """Bounding box of a check valve centered at (x, y)."""
    return _box(x, y, orientation, CHECK_LENGTH, CHECK_HEIGHT)


def bfp_box(x: float, y: float, orientation: Orientation) -> Box:
    """Bounding box of a backflow preventer centered at (x, y)."""
    return _box(x, y, orientation, BFP_LENGTH, BFP_HEIGHT)


def prv_box(x: float, y: float, orientation: Orientation) -> Box:
    """Bounding box of a pressure reducing valve, including its dome."""
    if orientation is Orientation.VERTICAL:
        return Box(
            x - VALVE_HEIGHT / 2,
            y - VALVE_LENGTH / 2,
            x + VALVE_HEIGHT / 2 + DOME_REACH,
            y + VALVE_LENGTH / 2,
        )
    return Box(
        x - VALVE_LENGTH / 2,
        y - VALVE_HEIGHT / 2 - DOME_REACH,
        x + VALVE_LENGTH / 2,
        y + VALVE_HEIGHT / 2,
    )


def _rotated(x: float, y: float, orientation: Orientation, parts: list[str]) -> str:
    vertical = orientation is Orientation.VERTICAL
    transform = f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if vertical else None
    return svg.element("g", {"transform": transform}, parts)


def _check_mark(cx: float, y: float, outline: dict[str, svg.AttrValue]) -> list[str]:
    """A check: a triangle pointing downstream, centered at cx, with a bar at its tip."""
    h = CHECK_HALF
    return [
        svg.polygon(
            ((cx - h, y - h), (cx - h, y + h), (cx + h, y)),
            {"fill": "none", "stroke-linejoin": "round", **outline},
        ),
        svg.line(cx + h, y - h, cx + h, y + h, outline),
    ]


def check_valve(x: float, y: float, status: Status, orientation: Orientation, theme: Theme) -> str:
    """Render a check valve centered at (x, y): flow passes left to right only."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    half = CHECK_LENGTH / 2
    parts = [
        svg.line(x - half, y, x - CHECK_HALF, y, outline),
        *_check_mark(x, y, outline),
        svg.line(x + CHECK_HALF, y, x + half, y, outline),
    ]
    return _rotated(x, y, orientation, parts)


def backflow_preventer(
    x: float, y: float, status: Status, orientation: Orientation, theme: Theme
) -> str:
    """Render a backflow preventer centered at (x, y): two checks in series in a box."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    half_l, half_h = BFP_LENGTH / 2, BFP_HEIGHT / 2
    first, second = x - 14.0, x + 14.0
    parts = [
        svg.rect(x - half_l, y - half_h, BFP_LENGTH, BFP_HEIGHT, {"fill": "none", **outline}),
        svg.line(x - half_l, y, first - CHECK_HALF, y, outline),
        *_check_mark(first, y, outline),
        svg.line(first + CHECK_HALF, y, second - CHECK_HALF, y, outline),
        *_check_mark(second, y, outline),
        svg.line(second + CHECK_HALF, y, x + half_l, y, outline),
    ]
    return _rotated(x, y, orientation, parts)


def prv(x: float, y: float, status: Status, orientation: Orientation, theme: Theme) -> str:
    """Render a pressure reducing valve centered at (x, y): a valve body with a spring dome."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    half_l, half_h = VALVE_LENGTH / 2, VALVE_HEIGHT / 2
    parts = [
        svg.polygon(
            ((x + side * half_l, y - half_h), (x + side * half_l, y + half_h), (x, y)),
            {"fill": "none", "stroke-linejoin": "round", **outline},
        )
        for side in (-1, 1)
    ]
    dome_base = y - half_h - DOME_STEM
    r = DOME_RADIUS
    parts += [
        svg.line(x, y, x, dome_base, outline),
        svg.element(
            "path",
            {
                "d": f"M{svg.fmt(x - r)} {svg.fmt(dome_base)} "
                f"A{svg.fmt(r)} {svg.fmt(r)} 0 0 1 {svg.fmt(x + r)} {svg.fmt(dome_base)} Z",
                "fill": "none",
                "stroke-linejoin": "round",
                **outline,
            },
        ),
    ]
    return _rotated(x, y, orientation, parts)
