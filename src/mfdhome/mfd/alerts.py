"""Alert latching, house-wide acknowledgement and attention ordering.

Everything here is pure: the caller supplies the clock (``now``) and keeps the
returned board. One board is shared by every display, so one acknowledgement
counts for the whole house.

Phases::

    INACTIVE --raised--> ACTIVE_UNACKED --ack--> ACTIVE_ACKED --cleared--> INACTIVE
                              |  ^
                      cleared |  | raised again
                              v  |
                         CLEARED_UNACKED --ack--> INACTIVE

Cautions and warnings latch through CLEARED_UNACKED; advisories don't latch, so
an unacknowledged advisory that clears goes straight back to INACTIVE.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from mfdhome.conditions.evaluate import EvalContext, holds
from mfdhome.model.alert import AlertDef
from mfdhome.model.state import StateSnapshot

logger = logging.getLogger(__name__)


class Phase(StrEnum):
    """Where an alert is in its lifecycle."""

    INACTIVE = "inactive"
    ACTIVE_UNACKED = "active_unacked"
    ACTIVE_ACKED = "active_acked"
    CLEARED_UNACKED = "cleared_unacked"

    @property
    def unacknowledged(self) -> bool:
        """Needs attention."""
        return self in (Phase.ACTIVE_UNACKED, Phase.CLEARED_UNACKED)

    @property
    def lit(self) -> bool:
        """Shown on the annunciator (active, or latched after clearing)."""
        return self is not Phase.INACTIVE


@dataclass(frozen=True)
class AlertState:
    """One alert's runtime state. ``since`` is when it was last raised."""

    phase: Phase = Phase.INACTIVE
    since: datetime | None = None
    acked_by: str | None = None
    acked_at: datetime | None = None


INACTIVE = AlertState()

#: alert id -> state. Missing ids are INACTIVE.
type Board = Mapping[str, AlertState]

EMPTY_BOARD: Board = {}


def evaluate_alerts(alerts: Iterable[AlertDef], state: StateSnapshot) -> frozenset[str]:
    """Ids of alerts whose condition currently holds."""
    ctx = EvalContext(state)
    return frozenset(a.id for a in alerts if holds(a.condition, ctx))


#: alert id -> when its condition started disagreeing with the board (pending a hold).
type Pending = Mapping[str, datetime]

_ACTIVE = (Phase.ACTIVE_UNACKED, Phase.ACTIVE_ACKED)


def apply_holds(
    alerts: Iterable[AlertDef],
    raised: Collection[str],
    board: Board,
    pending: Pending,
    now: datetime,
) -> tuple[frozenset[str], Pending]:
    """Debounce ``raised`` through each alert's ``hold``.

    An alert whose condition disagrees with the board (holds while the alert
    isn't active, or stopped holding while it is) only changes once the
    disagreement has lasted ``hold``; a blip in between resets the wait.
    Returns the ids to treat as raised and the updated pending times.
    """
    effective = set()
    out = {}
    for alert in alerts:
        holds_now = alert.id in raised
        active = board.get(alert.id, INACTIVE).phase in _ACTIVE
        if holds_now != active and alert.hold:
            start = pending.get(alert.id, now)
            if now - start < alert.hold:
                out[alert.id] = start
                holds_now = active  # not yet: keep the board as it is
        if holds_now:
            effective.add(alert.id)
    return frozenset(effective), out


def _step_one(alert: AlertDef, current: AlertState, raised: bool, now: datetime) -> AlertState:
    match current.phase, raised:
        case Phase.INACTIVE, True:
            return AlertState(Phase.ACTIVE_UNACKED, now)
        case Phase.CLEARED_UNACKED, True:
            return AlertState(Phase.ACTIVE_UNACKED, now)
        case Phase.ACTIVE_UNACKED, False:
            if alert.severity.needs_ack:
                return replace(current, phase=Phase.CLEARED_UNACKED)
            return INACTIVE
        case Phase.ACTIVE_ACKED, False:
            return INACTIVE
        case _:
            return current


def step(board: Board, alerts: Iterable[AlertDef], raised: Collection[str], now: datetime) -> Board:
    """Advance every alert given the ids currently ``raised``.

    States for alerts no longer defined are dropped.
    """
    out = {}
    for alert in alerts:
        new = _step_one(alert, board.get(alert.id, INACTIVE), alert.id in raised, now)
        if new.phase is not Phase.INACTIVE:
            out[alert.id] = new
    return out


def acknowledge(board: Board, by: str, now: datetime, ids: Iterable[str] | None = None) -> Board:
    """Acknowledge ``ids`` (all unacknowledged alerts if ``None``) on behalf of ``by``.

    Active alerts become acknowledged; latched (cleared) alerts are dismissed.
    Ids that are not unacknowledged are ignored.
    """
    targets = set(board) if ids is None else set(ids)
    out = dict(board)
    for alert_id in targets:
        current = board.get(alert_id, INACTIVE)
        if current.phase is Phase.ACTIVE_UNACKED:
            out[alert_id] = replace(current, phase=Phase.ACTIVE_ACKED, acked_by=by, acked_at=now)
        elif current.phase is Phase.CLEARED_UNACKED:
            del out[alert_id]
        else:
            logger.debug("ignoring acknowledgement of %s in phase %s", alert_id, current.phase)
    return out


def _priority(alert: AlertDef, state: AlertState) -> tuple[int, int, int, float]:
    """Sort key, smallest first: severity, then life safety first, then active
    before cleared, then newest."""
    since = state.since.timestamp() if state.since else 0.0
    cleared = 1 if state.phase is Phase.CLEARED_UNACKED else 0
    return (-alert.severity.rank, 0 if alert.life_safety else 1, cleared, -since)


def attention_order(board: Board, alerts: Iterable[AlertDef]) -> list[AlertDef]:
    """Unacknowledged alerts, most urgent first (advisories included, last)."""
    pending = [a for a in alerts if board.get(a.id, INACTIVE).phase.unacknowledged]
    return sorted(pending, key=lambda a: _priority(a, board[a.id]))


def most_urgent(board: Board, alerts: Iterable[AlertDef]) -> AlertDef | None:
    """The unacknowledged caution/warning the banner should name, if any.

    Order: warning before caution; life-safety alerts first within a
    severity; active before cleared-but-unacknowledged; most recently raised
    first. Advisories never qualify.
    """
    for alert in attention_order(board, alerts):
        if alert.severity.needs_ack:
            return alert
    return None
