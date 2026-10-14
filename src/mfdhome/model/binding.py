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
    """A reference to an entity's state, or to one of its attributes."""

    entity_id: str
    attribute: str | None = None


@dataclass(frozen=True)
class ElementRef:
    """A reference to another element's channel (e.g. a group's derived ``power``)."""

    element_id: str
    channel: str


#: What a channel can be bound to.
type Binding = EntityRef | ElementRef
