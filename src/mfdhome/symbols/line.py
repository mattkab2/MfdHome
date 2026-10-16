"""Line symbol: a polyline, cased (hollow pipe) or plain, with an optional flow arrow.

Line severity is carried by pattern as well as color, so it survives palettes
without color: solid = normal/active (solid core while flowing), dashed core =
caution, hatched = warning, dotted = unavailable. Widths come from the theme
alone; the theme's per-status weights apply to symbols, not lines.
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
from mfdhome.symbols.style import dotted, font, stroke
from mfdhome.themes.theme import Theme

#: The flow arrow's proportions, as multiples of the line's drawn width (at
#: least ``ARROW_MIN_WIDTH``): gap from the line's edge, overall length, head
#: length, head depth and shaft thickness.
ARROW_MIN_WIDTH = 8.0
ARROW_GAP = 0.4
ARROW_LENGTH = 3.0
ARROW_HEAD = 1.4
ARROW_DEPTH = 0.8
ARROW_SHAFT = 0.2
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


def _arrow_spot(
    pts: Sequence[Point], at: float | None, length: float, margin: float
) -> tuple[Point, Point]:
    """Where the flow arrow goes: its center and the segment's direction (in point order).

    At fraction ``at`` of the line's length if given, slid along that segment
    so the arrow (``length`` long, kept ``margin`` from either end) never
    wraps a bend; otherwise, or if that segment is too short, the middle of
    the longest segment.
    """
    segments = [(a, b) for a, b in pairwise(pts) if math.dist(a, b) > 0]
    if at is not None:
        (px, py), _ = point_along(pts, at)
        for (ax, ay), (bx, by) in segments:
            seg = math.dist((ax, ay), (bx, by))
            dx, dy = (bx - ax) / seg, (by - ay) / seg
            u = (px - ax) * dx + (py - ay) * dy
            on_segment = abs((px - ax) * dy - (py - ay) * dx) < 1e-6 and -1e-6 <= u <= seg + 1e-6
            room = length / 2 + margin
            if on_segment and seg >= 2 * room:
                u = min(max(u, room), seg - room)
                return (ax + dx * u, ay + dy * u), (dx, dy)
    a, b = max(segments, key=lambda s: math.dist(*s), default=(pts[0], pts[-1]))
    return point_along((a, b), 0.5)


def _arrow(
    pts: Sequence[Point],
    flow: Flow,
    half: float,
    color: str,
    at: float | None,
    avoid: Point | None,
) -> str:
    """A harpoon beside the line: a shaft parallel to it, set off from its edge,
    with a half-arrowhead at the downstream end flaring away from the line.

    It sits on the side away from ``avoid`` (the direction of the line's
    labels; by default above horizontal lines and right of vertical ones),
    so it never covers the line's core or its labels.
    """
    width = max(2 * half, ARROW_MIN_WIDTH)
    length = width * ARROW_LENGTH
    (cx, cy), (dx, dy) = _arrow_spot(pts, at, length, half + width * ARROW_GAP)
    nx, ny = -dy, dx
    default = (0.0, -1.0) if abs(dx) >= abs(dy) else (1.0, 0.0)
    ax, ay = avoid if avoid is not None and abs(nx * avoid[0] + ny * avoid[1]) > 1e-9 else default
    if nx * ax + ny * ay > 0:
        nx, ny = -nx, -ny
    if flow is Flow.REVERSE:
        dx, dy = -dx, -dy

    def at_(u: float, v: float) -> Point:
        return (cx + dx * u + nx * v, cy + dy * u + ny * v)

    inner = half + width * ARROW_GAP
    head, depth = width * ARROW_HEAD, width * ARROW_DEPTH
    shaft = max(1.0, width * ARROW_SHAFT)
    tail, tip = at_(-length / 2, inner + shaft / 2), at_(length / 2 - head, inner + shaft / 2)
    return svg.element(
        "line",
        {
            "x1": tail[0],
            "y1": tail[1],
            "x2": tip[0],
            "y2": tip[1],
            "stroke": color,
            "stroke-width": shaft,
        },
    ) + svg.element(
        "polygon",
        {
            "points": svg.points(
                (
                    at_(length / 2, inner),
                    at_(length / 2 - head, inner),
                    at_(length / 2 - head, inner + depth),
                )
            ),
            "fill": color,
        },
    )


#: Service tag plate: text size relative to the theme's font, padding, height.
TAG_SCALE = 0.75
TAG_PAD = 4.0
TAG_HEIGHT = 16.0


def tag_plate(at: Point, text: str, status: Status, theme: Theme) -> str:
    """A small plate centered on the line at ``at`` naming what it carries (``HW``)."""
    size = theme.font_size * TAG_SCALE
    width = len(text) * size * 0.6 + 2 * TAG_PAD
    x, y = at
    plate = svg.element(
        "rect",
        {
            "x": x - width / 2,
            "y": y - TAG_HEIGHT / 2,
            "width": width,
            "height": TAG_HEIGHT,
            "rx": 2,
            "fill": theme.background,
            **stroke(status, theme, theme.symbol_stroke_width),
        },
    )
    label = svg.element(
        "text",
        {
            "x": x,
            "y": y,
            "text-anchor": "middle",
            "dominant-baseline": "middle",
            **font(theme, size, theme.text_in(status)),
        },
        [svg.text(text)],
    )
    return plate + label


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
    casing: bool,
    line_id: str = "line",
    arrow_at: float | None = None,
    arrow_avoid: Point | None = None,
) -> LineParts:
    """Render a line.

    A plain line is ``theme.line_width`` wide. A cased line is a hollow pipe
    ``theme.casing_width`` wide with ``theme.casing_wall`` walls; while
    ``flow`` is set (rate above the flow threshold) its hollow gets a solid
    core, and a blank hollow means no flow. Severity patterns:
    caution dashes the core (shown even without flow; an uncased line's stroke
    is dashed instead);
    warning hatches the pipe's interior, forcing casing on so stripes have
    room; unavailable is dotted. ``flow`` draws a harpoon beside the line
    pointing along (FORWARD) or against (REVERSE) the point order, at
    fraction ``arrow_at`` of its length (default: the middle of the longest
    segment) on the side away from ``arrow_avoid`` (see ``_arrow``).
    ``line_id`` keeps hatch pattern ids unique on the page.
    """
    if len(pts) < 2:
        return LineParts("", "", 0.0)
    color = theme.color(status)
    casing = casing or status is Status.WARNING
    if casing:
        outer = theme.casing_width
        # Walls are solid except when unavailable (dotted); caution lives in the core.
        walls = _pattern(status, theme, outer) if status is Status.UNAVAILABLE else {}
        shell = _polyline(pts, {"stroke": color, "stroke-width": outer, **walls})
        hollow = max(outer - 2 * theme.casing_wall, MIN_HOLLOW)
        if status is Status.WARNING:
            parts = _hatch(line_id, pts, hollow, color, theme)
        else:
            parts = [_polyline(pts, {"stroke": theme.background, "stroke-width": hollow})]
            core = hollow - 2 * theme.core_inset
            if core > 0 and status is Status.CAUTION:
                # Dashed core: caution, whether or not anything flows (the arrow
                # shows flow). Dashes scale with the pipe so they stay legible.
                dash, gap = (outer * k for k in CAUTION_DASH)
                parts.append(
                    _polyline(
                        pts,
                        {
                            "stroke": color,
                            "stroke-width": core,
                            "stroke-dasharray": f"{svg.fmt(dash)} {svg.fmt(gap)}",
                        },
                    )
                )
            elif core > 0 and flow is not None:
                # Solid core: something is flowing. A blank pipe means no flow.
                parts.append(_polyline(pts, {"stroke": color, "stroke-width": core}))
        half = outer / 2
    else:
        width = theme.line_width
        shell = ""
        attrs = {"stroke": color, "stroke-width": width, **_pattern(status, theme, width)}
        parts = [_polyline(pts, attrs)]
        half = width / 2
    if flow is not None:
        parts.append(_arrow(pts, flow, half, color, arrow_at, arrow_avoid))
    return LineParts(shell, "".join(parts), half)
