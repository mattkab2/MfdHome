"""State snapshot types: the plain-data view of Home Assistant entity states."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

#: HA state strings that mean "no usable value".
UNAVAILABLE_STATES = frozenset({"unavailable", "unknown", "none", ""})


@dataclass(frozen=True)
class EntityState:
    """The state of a single HA entity at snapshot time.

    ``reported`` is when HA last heard from the entity, even if its value did not
    change; ``None`` when unknown (e.g. hand-written fixtures).
    """

    state: str
    attributes: Mapping[str, Any] = field(default_factory=dict)
    reported: datetime | None = None

    @property
    def available(self) -> bool:
        """Whether the entity reports a usable state."""
        return self.state.strip().lower() not in UNAVAILABLE_STATES


#: entity_id -> state. Render code only ever sees this, never a live client.
type StateSnapshot = Mapping[str, EntityState]


def snapshot_from_ha_states(states: Iterable[Mapping[str, Any]]) -> StateSnapshot:
    """Build a snapshot from the HA ``/api/states`` response shape.

    Each item needs ``entity_id`` and ``state``; ``attributes`` is optional.
    The report time comes from ``last_reported`` (HA 2024.3+), falling back to
    ``last_updated``, which HA does not bump when a value is re-reported
    unchanged. Malformed items (missing ``entity_id``) are skipped.
    """
    snapshot: dict[str, EntityState] = {}
    for item in states:
        entity_id = item.get("entity_id")
        if not isinstance(entity_id, str):
            continue
        attributes = item.get("attributes")
        snapshot[entity_id] = EntityState(
            state=str(item.get("state", "unknown")),
            attributes=dict(attributes) if isinstance(attributes, Mapping) else {},
            reported=_timestamp(item.get("last_reported") or item.get("last_updated")),
        )
    return snapshot


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class StalePolicy:
    """How long an entity may go unreported before its data counts as stale.

    ``default`` applies to every entity (``None``: never stale); ``entities``
    overrides it per entity id.
    """

    default: timedelta | None = None
    entities: Mapping[str, timedelta] = field(default_factory=dict)

    def limit(self, entity_id: str) -> timedelta | None:
        """The staleness limit for ``entity_id``, or ``None`` for none."""
        return self.entities.get(entity_id, self.default)


@dataclass(frozen=True)
class AveragingPolicy:
    """Which entities a time-averaging display averages.

    By default, those Home Assistant calls instantaneous measurements
    (``state_class: measurement``: power, flow, temperature, ...), never totals,
    text states or attributes. ``entities`` forces an entity on (``True``) or off.
    """

    entities: Mapping[str, bool] = field(default_factory=dict)

    def averages(self, entity_id: str, entity: EntityState) -> bool:
        """Whether ``entity_id``'s state is averaged."""
        forced = self.entities.get(entity_id)
        if forced is not None:
            return forced
        return entity.attributes.get("state_class") == "measurement"
