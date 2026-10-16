"""Alert history: what changed on the board, and when.

Only changes are recorded, never "still active": an alert raised for hours is
one RAISED event and, later, one CLEARED event. Events come from comparing the
board before and after each step or acknowledgement (pure; the caller
supplies the clock), plus Home Assistant connection changes, which explain
gaps in the history.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from mfdhome.mfd.alerts import INACTIVE, Board, Phase
from mfdhome.model.alert import LoggedEntity
from mfdhome.model.state import StateSnapshot

logger = logging.getLogger(__name__)


class EventKind(StrEnum):
    """What happened."""

    RAISED = "raised"
    CLEARED = "cleared"
    ACKED = "acked"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"
    STATE = "state"  # a logged entity changed state (not an alert)


@dataclass(frozen=True)
class AlertEvent:
    """One history entry. ``alert_id`` is ``None`` for connection and state events;
    ``by`` is the display that acknowledged; ``entity_id`` and ``state`` describe a
    logged entity's change."""

    at: datetime
    kind: EventKind
    alert_id: str | None = None
    by: str | None = None
    entity_id: str | None = None
    state: str | None = None


#: (before, after) phase -> event. Every possible board change maps to exactly one.
_TRANSITIONS = {
    (Phase.INACTIVE, Phase.ACTIVE_UNACKED): EventKind.RAISED,
    (Phase.CLEARED_UNACKED, Phase.ACTIVE_UNACKED): EventKind.RAISED,  # raised again, latched
    (Phase.ACTIVE_UNACKED, Phase.ACTIVE_ACKED): EventKind.ACKED,
    (Phase.CLEARED_UNACKED, Phase.INACTIVE): EventKind.ACKED,  # a latched alert dismissed
    (Phase.ACTIVE_UNACKED, Phase.CLEARED_UNACKED): EventKind.CLEARED,  # latches
    (Phase.ACTIVE_UNACKED, Phase.INACTIVE): EventKind.CLEARED,  # advisory
    (Phase.ACTIVE_ACKED, Phase.INACTIVE): EventKind.CLEARED,
}


def board_events(
    before: Board,
    after: Board,
    now: datetime,
    known: Collection[str],
    by: str | None = None,
) -> list[AlertEvent]:
    """The events that turn ``before`` into ``after``, for alerts in ``known``.

    Alerts no longer defined (dropped from the board when the config changed)
    produce no events. ``by`` is recorded on acknowledgements.
    """
    events = []
    for alert_id in sorted((set(before) | set(after)) & set(known)):
        old = before.get(alert_id, INACTIVE).phase
        new = after.get(alert_id, INACTIVE).phase
        if old is new:
            continue
        kind = _TRANSITIONS.get((old, new))
        if kind is None:
            logger.warning("no history event for %s: %s -> %s", alert_id, old, new)
            continue
        events.append(AlertEvent(now, kind, alert_id, by if kind is EventKind.ACKED else None))
    return events


def state_events(
    previous: Mapping[str, str],
    state: StateSnapshot,
    logged: Iterable[LoggedEntity],
    now: datetime,
) -> tuple[list[AlertEvent], dict[str, str]]:
    """Events for logged entities whose state changed since ``previous``.

    Returns the events and the states to compare against next time. An
    entity seen for the first time sets the baseline without an event, so a
    restart logs nothing; a missing entity counts as ``unavailable``.
    """
    current = {
        e.entity_id: state[e.entity_id].state if e.entity_id in state else "unavailable"
        for e in logged
    }
    events = [
        AlertEvent(now, EventKind.STATE, entity_id=entity_id, state=value)
        for entity_id, value in current.items()
        if entity_id in previous and previous[entity_id] != value
    ]
    return events, current


def prune(events: Iterable[AlertEvent], now: datetime, keep: timedelta) -> list[AlertEvent]:
    """Events no older than ``keep``, in order."""
    cutoff = now - keep
    return [e for e in events if e.at >= cutoff]
