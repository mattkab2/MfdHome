"""Outlet symbol: where a line ends at a point of use (sink, hose bib, ...).

Drawn the P&ID way, abstractly: an inlet stub ending in a terminal flag (an
arrow-shaped pentagon pointing away from the inlet) with a short tag inside.
An outdoor outlet crosses the stub with a double bar, the exterior wall.
Outlets are always horizontal (fed from the left, flag pointing right), so
the tag reads upright and fits the flag.
"""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import font, stroke
from mfdhome.themes.theme import Theme

LENGTH = 64.0  # inlet to flag tip
HEIGHT = 24.0
FLAG_START = -14.0  # flag body, from the center along the outlet
FLAG_SHOULDER = 20.0  # where the flag starts to point
WALL = (-26.0, -21.0)  # the exterior wall's two faces, on the stub
WALL_HALF = 8.0
LABEL_SCALE = 0.75  # label size relative to the theme's font size


def outlet_box(x: float, y: float) -> Box:
    """Bounding box of an outlet centered at (x, y)."""
    return Box(x - LENGTH / 2, y - HEIGHT / 2, x + LENGTH / 2, y + HEIGHT / 2)


def inlet(x: float, y: float) -> Port:
    """The outlet's supply: its left end."""
    return Port((x - LENGTH / 2, y), (-1.0, 0.0))


def outlet(x: float, y: float, label: str, outdoor: bool, status: Status, theme: Theme) -> str:
    """Render an outlet centered at (x, y), fed from the left."""
    outline = stroke(status, theme, theme.symbol_stroke_width)

    def line(u1: float, v1: float, u2: float, v2: float) -> str:
        return svg.element(
            "line", {"x1": x + u1, "y1": y + v1, "x2": x + u2, "y2": y + v2, **outline}
        )

    half_h, tip = HEIGHT / 2, LENGTH / 2
    flag = [
        (FLAG_START, -half_h),
        (FLAG_SHOULDER, -half_h),
        (tip, 0.0),
        (FLAG_SHOULDER, half_h),
        (FLAG_START, half_h),
    ]
    parts = [
        line(-tip, 0.0, FLAG_START, 0.0),
        svg.element(
            "polygon",
            {
                "points": svg.points((x + u, y + v) for u, v in flag),
                "fill": "none",
                "stroke-linejoin": "round",
                **outline,
            },
        ),
    ]
    if outdoor:
        parts += [line(u, -WALL_HALF, u, WALL_HALF) for u in WALL]
    lx, ly = x + (FLAG_START + FLAG_SHOULDER) / 2, y
    parts.append(
        svg.element(
            "text",
            {
                "x": lx,
                "y": ly,
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                **font(theme, theme.font_size * LABEL_SCALE, theme.text_in(status)),
            },
            [svg.text(label)],
        )
    )
    return "".join(parts)
