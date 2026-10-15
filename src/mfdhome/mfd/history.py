"""Alert history: what changed on the board, and when.

Only changes are recorded, never "still active": an alert raised for hours is
one RAISED event and, later, one CLEARED event. Events come from comparing the
board before and after each step or acknowledgement (pure; the caller
supplies the clock), plus Home Assistant connection changes, which explain
gaps in the history.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from mfdhome.mfd.alerts import INACTIVE, Board, Phase

logger = logging.getLogger(__name__)


class EventKind(StrEnum):
    """What happened."""

    RAISED = "raised"
    CLEARED = "cleared"
    ACKED = "acked"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"


@dataclass(frozen=True)
class AlertEvent:
    """One history entry. ``alert_id`` is ``None`` for connection events; ``by`` is the
    display that acknowledged."""

    at: datetime
    kind: EventKind
    alert_id: str | None = None
    by: str | None = None


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


def prune(events: Iterable[AlertEvent], now: datetime, keep: timedelta) -> list[AlertEvent]:
    """Events no older than ``keep``, in order."""
    cutoff = now - keep
    return [e for e in events if e.at >= cutoff]
