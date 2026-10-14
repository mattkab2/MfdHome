"""Power line symbol: a polyline, solid or cased, with an optional flow chevron."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from mfdhome.layout.path import Point, point_along
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

ARROW_SIZE = 10.0
#: Arrow half-length relative to a cased line's outer width.
ARROW_CASING_RATIO = 1.25
#: Inner (hollow) width never drops below this, so a cased line stays visibly hollow.
MIN_HOLLOW = 1.0


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
    (mx, my), (dx, dy) = point_along(pts, 0.5)
    if flow is Flow.REVERSE:
        dx, dy = -dx, -dy
    tip = (mx + dx * size, my + dy * size)
    left = (mx - dx * size - dy * size, my - dy * size + dx * size)
    right = (mx - dx * size + dy * size, my - dy * size - dx * size)
    return svg.element("polygon", {"points": svg.points((tip, left, right)), "fill": color})


def line(
    pts: Sequence[Point],
    status: Status,
    flow: Flow | None,
    theme: Theme,
    weight: float = 1.0,
    casing: bool = False,
) -> LineParts:
    """Render a power line.

    A solid line is ``theme.line_width * weight`` wide. A cased line is a
    hollow pipe ``theme.casing_width * weight`` wide with ``theme.casing_wall``
    walls; when unavailable, its outer dots are spaced to their size, so the
    hollow cuts each dot into a pair of edge marks. ``flow`` draws a chevron at
    the midpoint pointing along (FORWARD) or against (REVERSE) the point order.
    """
    if len(pts) < 2:
        return LineParts("", "", 0.0)
    color = theme.color(status)
    if casing:
        outer = theme.casing_width * weight
        attrs = stroke(status, theme, outer)
        if status is Status.UNAVAILABLE:
            attrs["stroke-dasharray"] = f"0 {svg.fmt(2 * outer)}"
        hollow = max(outer - 2 * theme.casing_wall, MIN_HOLLOW)
        shell = _polyline(pts, attrs)
        parts = [_polyline(pts, {"stroke": theme.background, "stroke-width": hollow})]
        size = max(ARROW_SIZE, outer * ARROW_CASING_RATIO)
        half = outer / 2
    else:
        width = theme.line_width * weight
        shell = ""
        parts = [_polyline(pts, stroke(status, theme, width))]
        size = ARROW_SIZE * max(1.0, weight)
        half = width / 2
    if flow is not None:
        parts.append(_arrow(pts, flow, size, color))
    return LineParts(shell, "".join(parts), half)
