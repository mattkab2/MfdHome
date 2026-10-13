"""Resolve element bindings against a state snapshot into visual properties.

Every function here is pure and total: missing entities, unavailable states,
missing attributes and non-numeric values resolve to ``Status.UNAVAILABLE``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mfdhome.model.binding import EntityRef, Status
from mfdhome.model.page import BatteryElement, BreakerElement, LineElement
from mfdhome.model.state import StateSnapshot
from mfdhome.symbols.line import Flow

NO_DATA = "---"


@dataclass(frozen=True)
class ResolvedLine:
    """Visual properties of a line."""

    status: Status
    flow: Flow | None
    label: str | None


@dataclass(frozen=True)
class ResolvedBattery:
    """Visual properties of a battery."""

    status: Status
    fill_fraction: float | None
    labels: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedBreaker:
    """Visual properties of a breaker."""

    status: Status
    closed: bool | None


def raw_value(ref: EntityRef, state: StateSnapshot) -> object | None:
    """The bound state string or attribute value, or ``None`` if unavailable."""
    entity = state.get(ref.entity_id)
    if entity is None or not entity.available:
        return None
    if ref.attribute is None:
        return entity.state
    return entity.attributes.get(ref.attribute)


def numeric_value(ref: EntityRef, state: StateSnapshot) -> float | None:
    """The bound value as a finite float, or ``None`` if unavailable or non-numeric."""
    value = raw_value(ref, state)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, str)):
        try:
            number = float(value)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def format_power(value: float | None, unit: str = "W") -> str:
    """Format a power reading; watts above 1000 are shown as kW."""
    if value is None:
        return NO_DATA
    if unit == "W" and abs(value) >= 1000:
        return f"{value / 1000:.1f} kW"
    return f"{value:.0f} {unit}"


def resolve_line(element: LineElement, state: StateSnapshot) -> ResolvedLine:
    """Status, flow direction and label for a line."""
    if element.power is None:
        return ResolvedLine(Status.NORMAL, None, None)
    power = numeric_value(element.power, state)
    if power is None:
        return ResolvedLine(Status.UNAVAILABLE, None, NO_DATA)
    label = format_power(abs(power), element.unit)
    if abs(power) <= element.flow_threshold:
        return ResolvedLine(Status.NORMAL, None, label)
    return ResolvedLine(Status.ACTIVE, Flow.FORWARD if power > 0 else Flow.REVERSE, label)


def resolve_battery(element: BatteryElement, state: StateSnapshot) -> ResolvedBattery:
    """Status, fill and labels for a battery."""
    soc = numeric_value(element.soc, state)
    power_label = (
        None if element.power is None else format_power(numeric_value(element.power, state))
    )
    if soc is None:
        labels = (NO_DATA,) if power_label is None else (NO_DATA, power_label)
        return ResolvedBattery(Status.UNAVAILABLE, None, labels)
    soc_label = f"{soc:.0f}%"
    labels = (soc_label,) if power_label is None else (soc_label, power_label)
    return ResolvedBattery(element.thresholds.classify(soc), soc / 100, labels)


def resolve_breaker(element: BreakerElement, state: StateSnapshot) -> ResolvedBreaker:
    """Status and contact position for a breaker."""
    value = raw_value(element.state, state)
    if value is None:
        return ResolvedBreaker(Status.UNAVAILABLE, None)
    text = str(value)
    return ResolvedBreaker(element.state_map.classify(text), element.state_map.is_closed(text))
