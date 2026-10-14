"""Shared visual status vocabulary and entity references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    """Shared visual language across all targets."""

    NORMAL = "normal"  # green
    CAUTION = "caution"  # amber
    WARNING = "warning"  # red
    ACTIVE = "active"  # cyan: flow / active
    UNAVAILABLE = "unavailable"  # gray, dotted


@dataclass(frozen=True)
class EntityRef:
    """A reference to an entity's state, or to one of its attributes.

    ``scale`` multiplies numeric values when read (e.g. ``-1`` for an inverter
    that reports export as positive, ``1000`` for kW to W); ``unit`` replaces
    the entity's own unit of measurement (give it when scaling changes units).
    """

    entity_id: str
    attribute: str | None = None
    scale: float = 1.0
    unit: str | None = None


@dataclass(frozen=True)
class ElementRef:
    """A reference to another element's channel (e.g. a group's derived ``power``)."""

    element_id: str
    channel: str


#: What a channel can be bound to.
type Binding = EntityRef | ElementRef
