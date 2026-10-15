"""Valve symbols: two triangles tip to tip, filled when closed (P&ID convention).

A ball valve has a hollow circle at the tips, a globe valve a solid dot. The
dot is ringed in the background color, so it stays visible on a closed
(filled) valve.
"""

from __future__ import annotations

from enum import StrEnum

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

LENGTH = 40.0
HEIGHT = 24.0
BALL_RADIUS = 5.0
GLOBE_RADIUS = 4.0
GLOBE_RING = 2.0


class ValveState(StrEnum):
    """What a valve is doing, as drawn."""

    OPEN = "open"  # outlined
    CLOSED = "closed"  # both triangles filled
    MOVING = "moving"  # opening or closing: the inlet triangle filled
    UNKNOWN = "unknown"  # no data: outlined


class Body(StrEnum):
    """The mark at the triangles' tips."""

    BALL = "ball"
    GLOBE = "globe"


def valve_box(x: float, y: float, orientation: Orientation) -> Box:
    """Bounding box of a valve centered at (x, y)."""
    w, h = (HEIGHT, LENGTH) if orientation is Orientation.VERTICAL else (LENGTH, HEIGHT)
    return Box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def valve(
    x: float,
    y: float,
    body: Body,
    state: ValveState,
    status: Status,
    orientation: Orientation,
    theme: Theme,
) -> str:
    """Render a valve centered at (x, y), flow from left to right (top to bottom)."""
    color = theme.color(status)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    half_l, half_h = LENGTH / 2, HEIGHT / 2
    filled = {
        ValveState.CLOSED: (True, True),
        ValveState.MOVING: (True, False),
    }.get(state, (False, False))
    parts = []
    for side, fill in zip((-1, 1), filled, strict=True):
        edge = x + side * half_l
        points = f"{svg.fmt(edge)},{svg.fmt(y - half_h)} {svg.fmt(edge)},{svg.fmt(y + half_h)} "
        points += f"{svg.fmt(x)},{svg.fmt(y)}"
        parts.append(
            svg.element(
                "polygon",
                {
                    "points": points,
                    "fill": color if fill else "none",
                    "stroke-linejoin": "round",
                    **outline,
                },
            )
        )
    if body is Body.BALL:
        parts.append(
            svg.element(
                "circle",
                {"cx": x, "cy": y, "r": BALL_RADIUS, "fill": theme.background, **outline},
            )
        )
    else:
        parts.append(
            svg.element(
                "circle",
                {
                    "cx": x,
                    "cy": y,
                    "r": GLOBE_RADIUS,
                    "fill": color,
                    "stroke": theme.background,
                    "stroke-width": GLOBE_RING,
                },
            )
        )
    transform = (
        f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if orientation is Orientation.VERTICAL else None
    )
    return svg.element("g", {"transform": transform}, parts)
