"""Connection routing: straight lines or a single orthogonal elbow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mfdhome.layout.path import Point

#: Coordinates closer than this count as aligned.
EPSILON = 1e-9


@dataclass(frozen=True)
class Port:
    """A connection point and, if it has one, the outward direction a line leaves it in."""

    point: Point
    direction: Point | None = None

    @property
    def horizontal(self) -> bool | None:
        """Whether the direction is horizontal; ``None`` without a direction."""
        if self.direction is None:
            return None
        return abs(self.direction[0]) >= abs(self.direction[1])


class Elbow(StrEnum):
    """Which leg of an elbowed connection comes first."""

    HORIZONTAL_FIRST = "horizontal-first"
    VERTICAL_FIRST = "vertical-first"


def route(start: Port, end: Port, elbow: Elbow | None = None) -> tuple[Point, ...]:
    """Points for a connection with at most one elbow.

    Aligned endpoints get a straight line. Otherwise the first leg follows
    ``elbow`` if given, else the start port's direction; failing that, the last
    leg enters the end port head-on; failing that, horizontal first.
    """
    (x0, y0), (x1, y1) = start.point, end.point
    if abs(x0 - x1) < EPSILON or abs(y0 - y1) < EPSILON:
        return (start.point, end.point)
    if elbow is not None:
        horizontal_first = elbow is Elbow.HORIZONTAL_FIRST
    elif start.horizontal is not None:
        horizontal_first = start.horizontal
    elif end.horizontal is not None:
        horizontal_first = not end.horizontal
    else:
        horizontal_first = True
    corner = (x1, y0) if horizontal_first else (x0, y1)
    return (start.point, corner, end.point)
