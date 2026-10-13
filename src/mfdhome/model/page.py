"""Page and element definitions, positioned on a logical canvas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from mfdhome.model.binding import BreakerStateMap, EntityRef, Thresholds

type Point = tuple[float, float]


class Orientation(StrEnum):
    """Direction of the conductor through a two-terminal symbol."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass(frozen=True)
class LineElement:
    """A power line between points.

    Positive ``power`` flows from the first point toward the last; negative
    flows backward (e.g. grid export).
    """

    id: str
    points: tuple[Point, ...]
    power: EntityRef | None = None
    flow_threshold: float = 10.0
    unit: str = "W"


@dataclass(frozen=True)
class BatteryElement:
    """A battery centered at (x, y) showing state of charge."""

    id: str
    x: float
    y: float
    soc: EntityRef
    power: EntityRef | None = None
    thresholds: Thresholds = field(
        default_factory=lambda: Thresholds(warning_low=10.0, caution_low=25.0)
    )


@dataclass(frozen=True)
class BreakerElement:
    """A breaker centered at (x, y)."""

    id: str
    x: float
    y: float
    state: EntityRef
    state_map: BreakerStateMap = field(default_factory=BreakerStateMap)
    orientation: Orientation = Orientation.HORIZONTAL


@dataclass(frozen=True)
class TextElement:
    """A static text label anchored at (x, y)."""

    id: str
    x: float
    y: float
    text: str


type Element = LineElement | BatteryElement | BreakerElement | TextElement


@dataclass(frozen=True)
class Page:
    """A page definition on a ``width`` x ``height`` logical canvas."""

    id: str
    title: str
    width: float
    height: float
    elements: tuple[Element, ...] = ()
