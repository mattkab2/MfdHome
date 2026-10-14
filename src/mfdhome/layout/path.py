"""Polyline geometry."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

type Point = tuple[float, float]


def point_along(pts: Sequence[Point], t: float) -> tuple[Point, Point]:
    """The point at fraction ``t`` (0..1) of the polyline's length, and the unit direction there.

    Zero-length polylines return the first point and a rightward direction.
    """
    segments = [(a, b, math.dist(a, b)) for a, b in itertools.pairwise(pts)]
    remaining = sum(length for _, _, length in segments) * min(max(t, 0.0), 1.0)
    for (ax, ay), (bx, by), length in segments:
        if length == 0:
            continue
        if remaining <= length:
            f = remaining / length
            point = (ax + (bx - ax) * f, ay + (by - ay) * f)
            return point, ((bx - ax) / length, (by - ay) / length)
        remaining -= length
    for (ax, ay), (bx, by), length in reversed(segments):
        if length:
            return (bx, by), ((bx - ax) / length, (by - ay) / length)
    return pts[0], (1.0, 0.0)
