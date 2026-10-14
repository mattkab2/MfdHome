"""Reading bound values out of a state snapshot."""

from __future__ import annotations

import math
from dataclasses import dataclass

from mfdhome.model.binding import EntityRef
from mfdhome.model.state import StateSnapshot


@dataclass(frozen=True)
class Value:
    """A bound value. ``raw is None`` means unavailable."""

    raw: object | None
    unit: str | None = None

    @property
    def available(self) -> bool:
        """Whether there is usable data."""
        return self.raw is not None

    @property
    def number(self) -> float | None:
        """The value as a finite float, or ``None`` if unavailable or non-numeric."""
        return as_number(self.raw)


MISSING = Value(None)


def as_number(value: object) -> float | None:
    """Convert to a finite float; ``None`` for bools, non-numeric strings and NaN/inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def read(ref: EntityRef, state: StateSnapshot) -> Value:
    """Read the entity state or attribute ``ref`` points at."""
    entity = state.get(ref.entity_id)
    if entity is None or not entity.available:
        return MISSING
    if ref.attribute is None:
        raw: object = entity.state
        unit = entity.attributes.get("unit_of_measurement")
    else:
        raw, unit = entity.attributes.get(ref.attribute), None
        if raw is None:
            return MISSING
    if ref.scale != 1.0 and (number := as_number(raw)) is not None:
        raw = number * ref.scale
    return Value(raw, ref.unit or (unit if isinstance(unit, str) else None))
