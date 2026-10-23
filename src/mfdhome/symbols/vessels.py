"""Vessels and movers: a tank (softener, filter, expansion tank) and a pump.

A tank is a rounded vessel with a short tag inside; its pipes are on top,
on the sides (inline) or a single one at the bottom. A pump is a circle
with a triangle pointing downstream, filled while it runs.
"""

from __future__ import annotations

from enum import StrEnum

from mfdhome.layout.anchors import Box
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke, text_at
from mfdhome.themes.theme import Theme

TANK_WIDTH = 40.0
TANK_HEIGHT = 56.0
TANK_CORNER = 8.0
TANK_PIPE_INSET = 9.0  # top connections, from the center line
TAG_SCALE = 0.75
PUMP_RADIUS = 16.0
PUMP_TRIANGLE = 8.0  # the triangle's half size


class Connections(StrEnum):
    """Where a tank's pipes are."""

    TOP = "top"  # in and out on top (a softener, a tank heater)
    SIDES = "sides"  # in on the left, out on the right (an inline filter)
    BOTTOM = "bottom"  # one connection underneath (an expansion tank)


def tank_box(x: float, y: float) -> Box:
    """Bounding box of a tank centered at (x, y)."""
    return Box(x - TANK_WIDTH / 2, y - TANK_HEIGHT / 2, x + TANK_WIDTH / 2, y + TANK_HEIGHT / 2)


def tank_ports(x: float, y: float, connections: Connections) -> dict[str, Port]:
    """The tank's connections: ``in``/``out``, or a single ``port`` underneath."""
    top, bottom = y - TANK_HEIGHT / 2, y + TANK_HEIGHT / 2
    match connections:
        case Connections.TOP:
            return {
                "in": Port((x - TANK_PIPE_INSET, top), (0.0, -1.0)),
                "out": Port((x + TANK_PIPE_INSET, top), (0.0, -1.0)),
            }
        case Connections.SIDES:
            return {
                "in": Port((x - TANK_WIDTH / 2, y), (-1.0, 0.0)),
                "out": Port((x + TANK_WIDTH / 2, y), (1.0, 0.0)),
            }
        case _:
            return {"port": Port((x, bottom), (0.0, 1.0))}


def tank(x: float, y: float, tag: str, status: Status, theme: Theme) -> str:
    """Render a tank centered at (x, y) with ``tag`` across its middle."""
    box = tank_box(x, y)
    body = svg.rect(
        box.left,
        box.top,
        TANK_WIDTH,
        TANK_HEIGHT,
        {"rx": TANK_CORNER, "fill": "none", **stroke(status, theme, theme.symbol_stroke_width)},
    )
    if not tag:
        return body
    return body + text_at(x, y, tag, theme, theme.font_size * TAG_SCALE, theme.text_in(status))


def pump_box(x: float, y: float) -> Box:
    """Bounding box of a pump centered at (x, y), in either orientation."""
    return Box(x - PUMP_RADIUS, y - PUMP_RADIUS, x + PUMP_RADIUS, y + PUMP_RADIUS)


def pump(
    x: float, y: float, running: bool, status: Status, orientation: Orientation, theme: Theme
) -> str:
    """Render a pump centered at (x, y), pumping left to right (top to bottom)."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    t = PUMP_TRIANGLE
    if orientation is Orientation.VERTICAL:
        points = ((x - t, y - t), (x + t, y - t), (x, y + t))
    else:
        points = ((x - t, y - t), (x - t, y + t), (x + t, y))
    return svg.circle(x, y, PUMP_RADIUS, {"fill": "none", **outline}) + svg.polygon(
        points,
        {"fill": theme.color(status) if running else "none", "stroke-linejoin": "round", **outline},
    )
