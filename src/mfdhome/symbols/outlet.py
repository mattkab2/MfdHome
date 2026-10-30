"""Outlet symbol: where a line ends at a point of use (sink, hose bib, ...).

Drawn the P&ID way, abstractly: a terminal flag (an arrow-shaped pentagon
pointing away from the inlet) with a short tag inside, its flat back flush
with the pipe that feeds it. An outdoor outlet doubles that back edge (the
wall the pipe passes through). An
outlet fed hot and cold (a sink) has two inlets on its back: ``cold`` above,
``hot`` below, so a heater's pair (cold inlet left of its hot outlet) reaches
it without the pipes crossing.
Outlets are always horizontal, so the tag reads upright and fits the flag:
fed from the left with the flag pointing right, or mirrored (``left``), fed
from the right with the flag pointing left.
"""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke, text_at
from mfdhome.themes.theme import Theme

LENGTH = 56.0  # flat back to tip
HEIGHT = 28.0  # room for two cased pipes side by side on the back
TWIN_OFFSET = 7.0  # hot and cold inlets, above and below the center
SHOULDER = 16.0  # where the flag starts to point, from the center
WALL_INSET = 3.5  # the outdoor variant's second back edge, inside the flag
LABEL_AT = -4.0  # tag center, from the center along the flag
LABEL_SCALE = 0.75  # tag size relative to the theme's font size


def outlet_box(x: float, y: float) -> Box:
    """Bounding box of an outlet centered at (x, y)."""
    return Box(x - LENGTH / 2, y - HEIGHT / 2, x + LENGTH / 2, y + HEIGHT / 2)


def inlet_ports(x: float, y: float, inlets: int, left: bool = False) -> dict[str, Port]:
    """Supply ports on the flag's flat back (on the right when the flag points
    ``left``): ``in`` in the middle, or (with two inlets) ``cold`` above and
    ``hot`` below."""
    side = 1.0 if left else -1.0
    back = x + side * LENGTH / 2
    if inlets == 1:
        return {"in": Port((back, y), (side, 0.0))}
    return {
        "cold": Port((back, y - TWIN_OFFSET), (side, 0.0)),
        "hot": Port((back, y + TWIN_OFFSET), (side, 0.0)),
    }


def _flag() -> list[Point]:
    """The pentagon, relative to the center, clockwise from the top of the back."""
    back, tip, half = -LENGTH / 2, LENGTH / 2, HEIGHT / 2
    return [(back, -half), (SHOULDER, -half), (tip, 0.0), (SHOULDER, half), (back, half)]


def outlet(
    x: float,
    y: float,
    label: str,
    outdoor: bool,
    status: Status,
    theme: Theme,
    left: bool = False,
) -> str:
    """Render an outlet centered at (x, y), fed from the left (from the right when
    it points ``left``)."""
    sign = -1.0 if left else 1.0
    outline = stroke(status, theme, theme.symbol_stroke_width)
    parts = [
        svg.polygon(
            ((x + sign * u, y + v) for u, v in _flag()),
            {"fill": "none", "stroke-linejoin": "round", **outline},
        )
    ]
    if outdoor:
        wall = x + sign * (-LENGTH / 2 + WALL_INSET)
        half = HEIGHT / 2
        parts.append(svg.line(wall, y - half, wall, y + half, outline))
    parts.append(
        text_at(
            x + sign * LABEL_AT,
            y,
            label,
            theme,
            theme.font_size * LABEL_SCALE,
            theme.text_in(status),
        )
    )
    return "".join(parts)
