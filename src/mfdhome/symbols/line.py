"""Power line symbol: a polyline with an optional flow chevron."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from mfdhome.layout.path import Point, point_along
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

ARROW_SIZE = 10.0


class Flow(StrEnum):
    """Flow direction relative to the line's point order."""

    FORWARD = "forward"
    REVERSE = "reverse"


def line(pts: Sequence[Point], status: Status, flow: Flow | None, theme: Theme) -> str:
    """Render a power line.

    ``flow`` draws a chevron at the line's midpoint pointing along (FORWARD) or
    against (REVERSE) the point order.
    """
    if len(pts) < 2:
        return ""
    parts = [
        svg.element(
            "polyline",
            {
                "points": svg.points(pts),
                "fill": "none",
                **stroke(status, theme, theme.line_width),
                "stroke-linejoin": "round",
            },
        )
    ]
    if flow is not None:
        (mx, my), (dx, dy) = point_along(pts, 0.5)
        if flow is Flow.REVERSE:
            dx, dy = -dx, -dy
        s = ARROW_SIZE
        tip = (mx + dx * s, my + dy * s)
        left = (mx - dx * s - dy * s, my - dy * s + dx * s)
        right = (mx - dx * s + dy * s, my - dy * s - dx * s)
        parts.append(
            svg.element(
                "polygon", {"points": svg.points((tip, left, right)), "fill": theme.color(status)}
            )
        )
    return "".join(parts)
