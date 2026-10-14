"""Marking stale entities unavailable before render (render itself reads no clock)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mfdhome.model.state import StalePolicy, StateSnapshot

STALE_STATE = "unavailable"


def mark_stale(state: StateSnapshot, policy: StalePolicy, now: datetime) -> StateSnapshot:
    """A copy of ``state`` with entities unreported for longer than their limit unavailable.

    Entities without a report time are never stale. Stale entities keep their
    attributes, with ``mfd_stale`` set so pages could show why data is missing.
    """
    out = dict(state)
    for entity_id, entity in state.items():
        limit = policy.limit(entity_id)
        if limit is None or entity.reported is None or now - entity.reported <= limit:
            continue
        out[entity_id] = replace(
            entity, state=STALE_STATE, attributes={**entity.attributes, "mfd_stale": True}
        )
    return out
