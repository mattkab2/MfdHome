"""Alert history: events from board changes, retention and the JSON Lines store."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mfdhome.conditions import TRUE
from mfdhome.mfd import EMPTY_BOARD, Board, acknowledge, step
from mfdhome.mfd.history import AlertEvent, EventKind, board_events, prune
from mfdhome.model import AlertDef, Severity, snapshot_from_ha_states
from mfdhome.server.history import HistoryStore
from mfdhome.server.runtime import Runtime
from tests.support import ha_state, load_test_config

T0 = datetime(2026, 1, 1, tzinfo=UTC)
WARN = AlertDef("warn", Severity.WARNING, "SYS", "WARN", TRUE)
ADV = AlertDef("adv", Severity.ADVISORY, "SYS", "ADV", TRUE)
ALERTS = (WARN, ADV)
KNOWN = {"warn", "adv"}


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


class Recorder:
    """Drives a board through steps and acknowledgements, collecting events."""

    def __init__(self) -> None:
        self.board: Board = EMPTY_BOARD
        self.events: list[AlertEvent] = []

    def step(self, minute: int, *raised: str) -> None:
        self.apply(step(self.board, ALERTS, set(raised), at(minute)), minute)

    def ack(self, minute: int, *ids: str) -> None:
        self.apply(acknowledge(self.board, "workshop", at(minute), ids or None), minute, "workshop")

    def apply(self, board: Board, minute: int, by: str | None = None) -> None:
        self.events += board_events(self.board, board, at(minute), KNOWN, by)
        self.board = board

    def log(self) -> list[tuple[int, str, str | None, str | None]]:
        return [
            (int((e.at - T0).total_seconds() // 60), e.kind.value, e.alert_id, e.by)
            for e in self.events
        ]


def test_latched_alert_lifecycle() -> None:
    r = Recorder()
    r.step(0, "warn")
    r.step(1, "warn")  # still raised: nothing new
    r.step(2)  # cleared, latched
    r.step(3, "warn")  # raised again while latched
    r.ack(4)
    r.step(5)
    assert r.log() == [
        (0, "raised", "warn", None),
        (2, "cleared", "warn", None),
        (3, "raised", "warn", None),
        (4, "acked", "warn", "workshop"),
        (5, "cleared", "warn", None),
    ]


def test_acknowledging_a_cleared_alert_is_one_event() -> None:
    r = Recorder()
    r.step(0, "warn")
    r.step(1)
    r.ack(2)
    assert r.log()[-1] == (2, "acked", "warn", "workshop") and not r.board


def test_advisory_start_and_end() -> None:
    r = Recorder()
    r.step(0, "adv")
    r.step(9, "adv")
    r.step(10)
    assert r.log() == [(0, "raised", "adv", None), (10, "cleared", "adv", None)]


def test_ongoing_alerts_add_nothing() -> None:
    r = Recorder()
    for minute in range(100):
        r.step(minute, "warn", "adv")
    assert len(r.events) == 2


def test_alerts_no_longer_defined_are_ignored() -> None:
    before = step(
        EMPTY_BOARD, (*ALERTS, AlertDef("gone", Severity.WARNING, "S", "G", TRUE)), {"gone"}, T0
    )
    assert board_events(before, EMPTY_BOARD, at(1), KNOWN) == []


def test_prune_keeps_the_window() -> None:
    events = [AlertEvent(at(m), EventKind.RAISED, "warn") for m in (0, 10, 20)]
    assert prune(events, at(25), timedelta(minutes=15)) == events[1:]


def test_store_round_trip_and_bad_lines(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.jsonl")
    assert store.load() == []
    events = [
        AlertEvent(at(0), EventKind.RAISED, "warn"),
        AlertEvent(at(1), EventKind.ACKED, "warn", "workshop"),
        AlertEvent(at(2), EventKind.CONNECTION_LOST),
    ]
    store.append(events[:2])
    store.append(events[2:])
    with store.path.open("a") as f:
        f.write("not json\n")
        f.write(json.dumps({"at": "2026-01-01T00:00:00", "kind": "raised"}) + "\n")  # naive time
        f.write(json.dumps({"at": T0.isoformat(), "kind": "exploded"}) + "\n")
    assert store.load() == events
    first = json.loads(store.path.read_text().splitlines()[2])
    assert first == {"at": "2026-01-01T00:02:00+00:00", "kind": "connection_lost"}
    store.replace(events[1:])
    assert store.load() == events[1:]


def test_runtime_records_and_prunes_daily(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.jsonl")
    old = AlertEvent(T0 - timedelta(days=20), EventKind.RAISED, "grid_lost")
    store.append([old])
    runtime = Runtime(load_test_config(), history_store=store)
    assert runtime.history == [old]
    grid_down = snapshot_from_ha_states([ha_state("binary_sensor.grid_connected", "off")])
    runtime.update(grid_down, T0)
    assert old not in runtime.history  # pruned on the first update of the day
    raised = [e for e in runtime.history if e.kind is EventKind.RAISED]
    assert "grid_lost" in {e.alert_id for e in raised}
    assert store.load() == runtime.history  # file and memory agree
    runtime.acknowledge("workshop", at(1), ids=["grid_lost"])
    assert runtime.history[-1] == AlertEvent(at(1), EventKind.ACKED, "grid_lost", "workshop")
