"""Regular grids of fixed-size cells."""

from __future__ import annotations

from mfdhome.layout.path import Point


def grid_centers(
    origin: Point,
    count: int,
    columns: int,
    cell: tuple[float, float],
    gap: tuple[float, float] = (0.0, 0.0),
) -> list[Point]:
    """Centers of ``count`` cells laid out row by row from top-left ``origin``."""
    if columns < 1:
        raise ValueError("columns must be at least 1")
    (x0, y0), (w, h), (gx, gy) = origin, cell, gap
    return [
        (x0 + (i % columns) * (w + gx) + w / 2, y0 + (i // columns) * (h + gy) + h / 2)
        for i in range(count)
    ]
