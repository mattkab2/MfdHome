"""Power line symbol: a polyline, solid or cased, with an optional flow chevron.

Line severity is carried by pattern as well as color, so it survives palettes
without color: solid = normal/active, dashed = caution, hatched = warning,
dotted = unavailable. Stroke widths here are structural only (style weight);
the theme's per-status weights apply to symbols, not lines.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from mfdhome.layout.path import Point, point_along
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import dotted
from mfdhome.themes.theme import Theme

ARROW_SIZE = 10.0
#: Arrow half-length relative to a cased line's outer width.
ARROW_CASING_RATIO = 1.25
#: Inner (hollow) width never drops below this, so a cased line stays visibly hollow.
MIN_HOLLOW = 1.0
#: Caution dashes, as multiples of the drawn width: dash, gap.
CAUTION_DASH = (1.5, 1.0)
#: Hatch stripes cross the line at this angle to its direction.
HATCH_ANGLE = 45.0


class Flow(StrEnum):
    """Flow direction relative to the line's point order."""

    FORWARD = "forward"
    REVERSE = "reverse"


@dataclass(frozen=True)
class LineParts:
    """A rendered line, split into layers.

    ``casing`` (the outer strokes of cased lines) is drawn beneath every
    line's ``body``, so hollow pipes merge cleanly where they meet.
    ``half_width`` is half the drawn width, for placing labels clear of it.
    """

    casing: str
    body: str
    half_width: float


def _polyline(pts: Sequence[Point], attrs: dict[str, svg.AttrValue]) -> str:
    return svg.element(
        "polyline", {"points": svg.points(pts), "fill": "none", **attrs, "stroke-linejoin": "round"}
    )


def _arrow(pts: Sequence[Point], flow: Flow, size: float, color: str) -> str:
    """A chevron at the middle of the longest segment, so it never sits on a bend."""
    a, b = max(pairwise(pts), key=lambda seg: math.dist(*seg))
    (mx, my), (dx, dy) = point_along((a, b), 0.5)
    if flow is Flow.REVERSE:
        dx, dy = -dx, -dy
    tip = (mx + dx * size, my + dy * size)
    left = (mx - dx * size - dy * size, my - dy * size + dx * size)
    right = (mx - dx * size + dy * size, my - dy * size - dx * size)
    return svg.element("polygon", {"points": svg.points((tip, left, right)), "fill": color})


def _pattern(status: Status, theme: Theme, width: float) -> dict[str, svg.AttrValue]:
    """Dash attributes for a stroke ``width`` wide in ``status``."""
    if status is Status.UNAVAILABLE:
        # Dots as wide as the stroke, spaced so they stay distinct.
        return {**dotted(theme), "stroke-dasharray": f"0 {svg.fmt(2 * width)}"}
    if status is Status.CAUTION:
        dash, gap = (width * k for k in CAUTION_DASH)
        return {"stroke-dasharray": f"{svg.fmt(dash)} {svg.fmt(gap)}"}
    return {}


def _hatch(line_id: str, pts: Sequence[Point], width: float, color: str, theme: Theme) -> list[str]:
    """Fill a hollow ``width`` wide with stripes, one pattern per segment.

    Each segment's stripes are rotated relative to that segment, so they always
    cross the line (a single page-fixed pattern vanishes on lines at its angle).
    """
    spacing = theme.hatch_spacing
    parts = []
    for i, ((ax, ay), (bx, by)) in enumerate(pairwise(pts)):
        if (ax, ay) == (bx, by):
            continue
        angle = math.degrees(math.atan2(by - ay, bx - ax)) + HATCH_ANGLE
        pattern_id = f"hatch-{line_id}-{i}"
        stripe = svg.element(
            "rect", {"x": 0, "y": 0, "width": spacing / 2, "height": spacing, "fill": color}
        )
        background = svg.element(
            "rect",
            {"x": 0, "y": 0, "width": spacing, "height": spacing, "fill": theme.background},
        )
        parts.append(
            svg.element(
                "pattern",
                {
                    "id": pattern_id,
                    "width": spacing,
                    "height": spacing,
                    "patternUnits": "userSpaceOnUse",
                    "patternTransform": f"rotate({svg.fmt(angle)})",
                },
                [background, stripe],
            )
        )
        parts.append(
            svg.element(
                "line",
                {
                    "x1": ax,
                    "y1": ay,
                    "x2": bx,
                    "y2": by,
                    "stroke": f"url(#{pattern_id})",
                    "stroke-width": width,
                    "stroke-linecap": "round" if 0 < i < len(pts) - 2 else "butt",
                },
            )
        )
    return parts


def line(
    pts: Sequence[Point],
    status: Status,
    flow: Flow | None,
    theme: Theme,
    weight: float = 1.0,
    casing: bool = False,
    line_id: str = "line",
) -> LineParts:
    """Render a power line.

    A solid line is ``theme.line_width * weight`` wide. A cased line is a
    hollow pipe ``theme.casing_width * weight`` wide with ``theme.casing_wall``
    walls. Severity patterns: caution dashes the stroke (or the pipe's walls);
    warning hatches the pipe's interior, forcing casing on so stripes have
    room; unavailable is dotted. ``flow`` draws a chevron at the midpoint
    pointing along (FORWARD) or against (REVERSE) the point order. ``line_id``
    keeps hatch pattern ids unique on the page.
    """
    if len(pts) < 2:
        return LineParts("", "", 0.0)
    color = theme.color(status)
    casing = casing or status is Status.WARNING
    if casing:
        outer = theme.casing_width * weight
        shell = _polyline(
            pts, {"stroke": color, "stroke-width": outer, **_pattern(status, theme, outer)}
        )
        hollow = max(outer - 2 * theme.casing_wall, MIN_HOLLOW)
        if status is Status.WARNING:
            parts = _hatch(line_id, pts, hollow, color, theme)
        else:
            parts = [_polyline(pts, {"stroke": theme.background, "stroke-width": hollow})]
        size = max(ARROW_SIZE, outer * ARROW_CASING_RATIO)
        half = outer / 2
    else:
        width = theme.line_width * weight
        shell = ""
        attrs = {"stroke": color, "stroke-width": width, **_pattern(status, theme, width)}
        parts = [_polyline(pts, attrs)]
        size = ARROW_SIZE * max(1.0, weight)
        half = width / 2
    if flow is not None:
        parts.append(_arrow(pts, flow, size, color))
    return LineParts(shell, "".join(parts), half)
