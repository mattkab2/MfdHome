"""Declarative bindings from HA entities to visual status."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class Status(StrEnum):
    """Shared visual language across all targets."""

    NORMAL = "normal"  # green
    CAUTION = "caution"  # amber
    WARNING = "warning"  # red
    ACTIVE = "active"  # cyan: flow / active
    UNAVAILABLE = "unavailable"  # gray, dashed


@dataclass(frozen=True)
class EntityRef:
    """A reference to an entity's state, or to one of its attributes."""

    entity_id: str
    attribute: str | None = None


@dataclass(frozen=True)
class Thresholds:
    """Numeric limits; a value at or beyond a limit takes that status.

    Warning limits take precedence over caution limits.
    """

    warning_low: float | None = None
    caution_low: float | None = None
    caution_high: float | None = None
    warning_high: float | None = None

    def classify(self, value: float) -> Status:
        """Return the status for ``value``."""
        if (self.warning_low is not None and value <= self.warning_low) or (
            self.warning_high is not None and value >= self.warning_high
        ):
            return Status.WARNING
        if (self.caution_low is not None and value <= self.caution_low) or (
            self.caution_high is not None and value >= self.caution_high
        ):
            return Status.CAUTION
        return Status.NORMAL


@dataclass(frozen=True)
class StateMap:
    """Maps discrete state strings (case-insensitive) to a status."""

    mapping: Mapping[str, Status]
    default: Status = Status.CAUTION

    def classify(self, state: str) -> Status:
        """Return the status for ``state``, or ``default`` if it is not mapped."""
        return self.mapping.get(state.strip().lower(), self.default)


def _breaker_states() -> Mapping[str, Status]:
    return MappingProxyType({"on": Status.NORMAL, "closed": Status.NORMAL})


@dataclass(frozen=True)
class BreakerStateMap(StateMap):
    """State map for breakers; also decides which states mean "closed"."""

    mapping: Mapping[str, Status] = field(default_factory=_breaker_states)
    closed_states: frozenset[str] = frozenset({"on", "closed"})

    def is_closed(self, state: str) -> bool:
        """Whether ``state`` means the breaker contacts are closed."""
        return state.strip().lower() in self.closed_states
