"""State snapshot types: the plain-data view of Home Assistant entity states."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

#: HA state strings that mean "no usable value".
UNAVAILABLE_STATES = frozenset({"unavailable", "unknown", "none", ""})


@dataclass(frozen=True)
class EntityState:
    """The state of a single HA entity at snapshot time."""

    state: str
    attributes: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def available(self) -> bool:
        """Whether the entity reports a usable state."""
        return self.state.strip().lower() not in UNAVAILABLE_STATES


#: entity_id -> state. Render code only ever sees this, never a live client.
type StateSnapshot = Mapping[str, EntityState]


def snapshot_from_ha_states(states: Iterable[Mapping[str, Any]]) -> StateSnapshot:
    """Build a snapshot from the HA ``/api/states`` response shape.

    Each item needs ``entity_id`` and ``state``; ``attributes`` is optional.
    Malformed items (missing ``entity_id``) are skipped.
    """
    snapshot: dict[str, EntityState] = {}
    for item in states:
        entity_id = item.get("entity_id")
        if not isinstance(entity_id, str):
            continue
        attributes = item.get("attributes")
        snapshot[entity_id] = EntityState(
            state=str(item.get("state", "unknown")),
            attributes=MappingProxyType(
                dict(attributes) if isinstance(attributes, Mapping) else {}
            ),
        )
    return MappingProxyType(snapshot)
