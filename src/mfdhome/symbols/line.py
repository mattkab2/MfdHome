"""Power line symbol: a polyline with an optional flow chevron and value label."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from enum import StrEnum

from mfdhome.model.binding import Status
from mfdhome.model.page import Point
from mfdhome.symbols import svg
from mfdhome.symbols.style import font, stroke
from mfdhome.themes.theme import Theme

ARROW_SIZE = 10.0
LABEL_OFFSET = 14.0


class Flow(StrEnum):
    """Flow direction relative to the line's point order."""

    FORWARD = "forward"
    REVERSE = "reverse"


def _midpoint(pts: Sequence[Point]) -> tuple[Point, Point]:
    """Return the point halfway along the polyline and the unit direction there."""
    segments = [(a, b, math.dist(a, b)) for a, b in itertools.pairwise(pts)]
    remaining = sum(length for _, _, length in segments) / 2
    for (ax, ay), (bx, by), length in segments:
        if length == 0:
            continue
        if remaining <= length:
            t = remaining / length
            point = (ax + (bx - ax) * t, ay + (by - ay) * t)
            return point, ((bx - ax) / length, (by - ay) / length)
        remaining -= length
    return pts[0], (1.0, 0.0)


def line(
    pts: Sequence[Point],
    status: Status,
    flow: Flow | None,
    label: str | None,
    theme: Theme,
) -> str:
    """Render a power line.

    ``flow`` draws a chevron at the line's midpoint pointing along (FORWARD) or
    against (REVERSE) the point order. ``label`` is drawn beside the midpoint.
    """
    if len(pts) < 2:
        return ""
    color = theme.color(status)
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
    (mx, my), (dx, dy) = _midpoint(pts)
    if flow is not None:
        if flow is Flow.REVERSE:
            dx, dy = -dx, -dy
        s = ARROW_SIZE
        tip = (mx + dx * s, my + dy * s)
        left = (mx - dx * s - dy * s, my - dy * s + dx * s)
        right = (mx - dx * s + dy * s, my - dy * s - dx * s)
        parts.append(
            svg.element("polygon", {"points": svg.points((tip, left, right)), "fill": color})
        )
    if label:
        # Place the label on the "upper"/right side of the line, away from the chevron.
        nx, ny = abs(dy), -abs(dx)
        anchor = "start" if abs(nx) > abs(ny) else "middle"
        parts.append(
            svg.element(
                "text",
                {
                    "x": mx + nx * LABEL_OFFSET,
                    "y": my + ny * LABEL_OFFSET,
                    "text-anchor": anchor,
                    "dominant-baseline": "middle" if anchor == "start" else None,
                    **font(theme, theme.font_size, color),
                },
                [svg.text(label)],
            )
        )
    return "".join(parts)
