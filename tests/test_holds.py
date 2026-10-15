"""Alert hold times (`for:`): conditions must last before raising or clearing."""

import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mfdhome.conditions import TRUE
from mfdhome.config import ConfigError, Defs, load_alerts
from mfdhome.mfd import EMPTY_BOARD, Board, Pending, Phase, apply_holds, step
from mfdhome.model import AlertDef, Severity

T0 = datetime(2026, 1, 1, tzinfo=UTC)
LOW = AlertDef("low", Severity.CAUTION, "BATT", "LOW", TRUE, hold=timedelta(seconds=30))
NOW = AlertDef("now", Severity.WARNING, "GRID", "NOW", TRUE)
ALERTS = (LOW, NOW)


class Sampler:
    """Feeds condition samples through holds and steps, one per call."""

    def __init__(self) -> None:
        self.board: Board = EMPTY_BOARD
        self.pending: Pending = {}

    def sample(self, seconds: int, *holding: str) -> dict[str, Phase]:
        now = T0 + timedelta(seconds=seconds)
        raised, self.pending = apply_holds(ALERTS, set(holding), self.board, self.pending, now)
        self.board = step(self.board, ALERTS, raised, now)
        return {k: v.phase for k, v in self.board.items()}


def test_raise_waits_for_the_hold() -> None:
    b = Sampler()
    assert b.sample(0, "low", "now") == {"now": Phase.ACTIVE_UNACKED}  # no hold: at once
    assert b.sample(29, "low", "now") == {"now": Phase.ACTIVE_UNACKED}
    assert b.sample(30, "low", "now")["low"] is Phase.ACTIVE_UNACKED
    assert b.board["low"].since == T0 + timedelta(seconds=30)


def test_a_blip_resets_the_wait() -> None:
    b = Sampler()
    b.sample(0, "low")
    b.sample(20)  # condition dropped: start over
    b.sample(25, "low")
    assert "low" not in b.sample(50, "low")
    assert b.sample(55, "low")["low"] is Phase.ACTIVE_UNACKED


def test_clear_waits_for_the_hold_too() -> None:
    b = Sampler()
    b.sample(0, "low")
    b.sample(30, "low")
    assert b.sample(40)["low"] is Phase.ACTIVE_UNACKED  # stopped holding 0 s ago
    assert b.sample(60, "low")["low"] is Phase.ACTIVE_UNACKED  # back before 30 s: no clear
    b.sample(70)
    assert b.sample(99)["low"] is Phase.ACTIVE_UNACKED
    assert b.sample(100)["low"] is Phase.CLEARED_UNACKED  # latched after 30 s clear


def test_flapping_condition_never_raises() -> None:
    b = Sampler()
    for second in range(0, 300, 10):
        state = b.sample(second, *(["low"] if second % 20 == 0 else []))
        assert "low" not in state


def test_for_in_alerts_yaml(tmp_path: Path) -> None:
    path = tmp_path / "alerts.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            systems: {BATT: {label: BATT}}
            alerts:
              - {id: low, severity: caution, system: BATT, message: LOW, for: 30s,
                 when: [{entity: sensor.soc, lt: 20}]}
              - {id: now, severity: caution, system: BATT, message: NOW,
                 when: [{entity: sensor.soc, lt: 5}]}
            """
        )
    )
    alerts = load_alerts(path, Defs())
    assert [a.hold for a in alerts.alerts] == [timedelta(seconds=30), timedelta(0)]
    path.write_text(path.read_text().replace("for: 30s", "for: soon"))
    with pytest.raises(ConfigError, match=r"alerts\[0\]\.for"):
        load_alerts(path, Defs())
