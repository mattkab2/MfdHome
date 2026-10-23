"""Valve symbols: two triangles tip to tip, filled when closed (P&ID convention).

A ball valve has a hollow circle at the tips, a globe valve a solid dot. The
dot is ringed in the background color, so it stays visible on a closed
(filled) valve. An actuated valve (motorized or solenoid: a smart shutoff, an
irrigation zone) carries the actuator mark above its body, as a smart
breaker does.
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
ACTUATOR_STEM = 8.0  # from the top of the body to the actuator box
ACTUATOR_WIDTH = 12.0
ACTUATOR_HEIGHT = 8.0
#: How far an actuator reaches beyond the body (top, or right when vertical).
ACTUATOR_REACH = ACTUATOR_STEM + ACTUATOR_HEIGHT


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


def valve_box(x: float, y: float, orientation: Orientation, actuated: bool = False) -> Box:
    """Bounding box of a valve centered at (x, y), including any actuator."""
    reach = ACTUATOR_REACH if actuated else 0.0
    if orientation is Orientation.VERTICAL:
        return Box(x - HEIGHT / 2, y - LENGTH / 2, x + HEIGHT / 2 + reach, y + LENGTH / 2)
    return Box(x - LENGTH / 2, y - HEIGHT / 2 - reach, x + LENGTH / 2, y + HEIGHT / 2)


def valve(
    x: float,
    y: float,
    body: Body,
    state: ValveState,
    status: Status,
    orientation: Orientation,
    theme: Theme,
    actuated: bool = False,
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
        parts.append(svg.circle(x, y, BALL_RADIUS, {"fill": theme.background, **outline}))
    else:
        parts.append(
            svg.circle(
                x,
                y,
                GLOBE_RADIUS,
                {"fill": color, "stroke": theme.background, "stroke-width": GLOBE_RING},
            )
        )
    if actuated:
        # The stem rises from the center mark (where the triangles meet), the bonnet.
        box_top = y - half_h - ACTUATOR_REACH
        stem_from = y - (BALL_RADIUS if body is Body.BALL else GLOBE_RADIUS + GLOBE_RING / 2)
        parts.append(svg.line(x, stem_from, x, box_top + ACTUATOR_HEIGHT, outline))
        parts.append(
            svg.rect(
                x - ACTUATOR_WIDTH / 2,
                box_top,
                ACTUATOR_WIDTH,
                ACTUATOR_HEIGHT,
                {"fill": "none", **outline},
            )
        )
    # Vertical: rotated about the center, so the actuator ends up on the right.
    transform = (
        f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if orientation is Orientation.VERTICAL else None
    )
    return svg.element("g", {"transform": transform}, parts)
