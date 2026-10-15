"""Tests for alert latching, acknowledgement and attention ordering."""

from datetime import UTC, datetime, timedelta

import pytest

from mfdhome.conditions import TRUE, AnyOf, Condition, Op
from mfdhome.mfd import (
    EMPTY_BOARD,
    AlertState,
    Board,
    Phase,
    acknowledge,
    attention_order,
    evaluate_alerts,
    most_urgent,
    step,
)
from mfdhome.model import AlertDef, EntityRef, Severity, snapshot_from_ha_states
from tests.support import ha_state

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def alert(id_: str, severity: Severity = Severity.WARNING) -> AlertDef:
    return AlertDef(id_, severity, "SYS", id_.upper(), TRUE)


WARN = alert("warn")
ADVISORY = alert("adv", Severity.ADVISORY)


def phases(board: Board) -> dict[str, Phase]:
    return {k: v.phase for k, v in board.items()}


@pytest.mark.parametrize(
    ("definition", "start", "raised", "expected"),
    [
        (WARN, Phase.INACTIVE, True, Phase.ACTIVE_UNACKED),
        (WARN, Phase.INACTIVE, False, Phase.INACTIVE),
        (WARN, Phase.ACTIVE_UNACKED, True, Phase.ACTIVE_UNACKED),
        (WARN, Phase.ACTIVE_UNACKED, False, Phase.CLEARED_UNACKED),  # latches
        (WARN, Phase.ACTIVE_ACKED, True, Phase.ACTIVE_ACKED),
        (WARN, Phase.ACTIVE_ACKED, False, Phase.INACTIVE),
        (WARN, Phase.CLEARED_UNACKED, False, Phase.CLEARED_UNACKED),
        (WARN, Phase.CLEARED_UNACKED, True, Phase.ACTIVE_UNACKED),
        (ADVISORY, Phase.INACTIVE, True, Phase.ACTIVE_UNACKED),
        (ADVISORY, Phase.ACTIVE_UNACKED, False, Phase.INACTIVE),  # no latch
        (ADVISORY, Phase.ACTIVE_ACKED, False, Phase.INACTIVE),
    ],
)
def test_step_transitions(
    definition: AlertDef, start: Phase, raised: bool, expected: Phase
) -> None:
    board = {definition.id: AlertState(start, T0)} if start is not Phase.INACTIVE else {}
    new = step(board, [definition], {definition.id} if raised else set(), at(1))
    assert new.get(definition.id, AlertState()).phase is expected


def test_raise_records_time_and_reraise_updates_it() -> None:
    board = step(EMPTY_BOARD, [WARN], {"warn"}, at(1))
    assert board["warn"].since == at(1)
    board = step(board, [WARN], set(), at(2))
    board = step(board, [WARN], {"warn"}, at(3))
    assert board["warn"] == AlertState(Phase.ACTIVE_UNACKED, at(3))


def test_acknowledge_active_and_cleared() -> None:
    other = alert("other")
    board = step(EMPTY_BOARD, [WARN, other], {"warn", "other"}, at(0))
    board = step(board, [WARN, other], {"warn"}, at(1))  # other clears -> latched
    assert phases(board) == {"warn": Phase.ACTIVE_UNACKED, "other": Phase.CLEARED_UNACKED}

    acked = acknowledge(board, by="workshop", now=at(2))
    assert phases(acked) == {"warn": Phase.ACTIVE_ACKED}
    assert (acked["warn"].acked_by, acked["warn"].acked_at) == ("workshop", at(2))


def test_acknowledge_specific_ids_only() -> None:
    other = alert("other")
    board = step(EMPTY_BOARD, [WARN, other], {"warn", "other"}, at(0))
    acked = acknowledge(board, "tablet", at(1), ids=["other", "unknown"])
    assert phases(acked) == {"warn": Phase.ACTIVE_UNACKED, "other": Phase.ACTIVE_ACKED}


def test_fires_again_after_acknowledged_clear_as_unacknowledged() -> None:
    board = step(EMPTY_BOARD, [WARN], {"warn"}, at(0))
    board = acknowledge(board, "tablet", at(1))
    board = step(board, [WARN], set(), at(2))
    assert board == {}
    board = step(board, [WARN], {"warn"}, at(3))
    assert board["warn"] == AlertState(Phase.ACTIVE_UNACKED, at(3))


def test_removed_definitions_are_dropped() -> None:
    board = {"gone": AlertState(Phase.ACTIVE_UNACKED, T0)}
    assert step(board, [WARN], set(), at(1)) == {}


def test_attention_order() -> None:
    caution_new = alert("caution_new", Severity.CAUTION)
    warn_cleared = alert("warn_cleared")
    warn_old = alert("warn_old")
    warn_new = alert("warn_new")
    warn_acked = alert("warn_acked")
    adv = alert("adv", Severity.ADVISORY)
    defs = [caution_new, warn_cleared, warn_old, warn_new, warn_acked, adv]
    board = {
        "caution_new": AlertState(Phase.ACTIVE_UNACKED, at(9)),
        "warn_cleared": AlertState(Phase.CLEARED_UNACKED, at(8)),
        "warn_old": AlertState(Phase.ACTIVE_UNACKED, at(1)),
        "warn_new": AlertState(Phase.ACTIVE_UNACKED, at(5)),
        "warn_acked": AlertState(Phase.ACTIVE_ACKED, at(7)),
        "adv": AlertState(Phase.ACTIVE_UNACKED, at(10)),
    }
    order = [a.id for a in attention_order(board, defs)]
    assert order == ["warn_new", "warn_old", "warn_cleared", "caution_new", "adv"]
    assert most_urgent(board, defs) == warn_new


def test_advisories_and_acknowledged_are_never_most_urgent() -> None:
    board = {
        "adv": AlertState(Phase.ACTIVE_UNACKED, T0),
        "warn": AlertState(Phase.ACTIVE_ACKED, T0),
    }
    assert most_urgent(board, [ADVISORY, WARN]) is None
    assert most_urgent(EMPTY_BOARD, [WARN]) is None


def test_evaluate_alerts() -> None:
    low = AlertDef(
        "low",
        Severity.CAUTION,
        "BATT",
        "LOW",
        AnyOf.single(Condition(EntityRef("sensor.soc"), Op.LT, 20)),
    )
    snap = snapshot_from_ha_states([ha_state("sensor.soc", "15")])
    assert evaluate_alerts([low, WARN], snap) == {"low", "warn"}
    # Missing data never raises a comparison-based alert.
    assert evaluate_alerts([low], {}) == frozenset()
