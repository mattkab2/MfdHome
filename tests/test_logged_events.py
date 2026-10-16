"""Logged entities: state changes (arming, disarming) shown in the alert log."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, Defs, load_alerts
from mfdhome.config.inventory import entity_uses
from mfdhome.mfd.history import AlertEvent, EventKind, state_events
from mfdhome.model import LogElement, LoggedEntity, StateSnapshot, snapshot_from_ha_states
from mfdhome.render.alerts import AlertView
from mfdhome.render.log import alert_log, event_text, log_rows
from mfdhome.server.history import HistoryStore
from mfdhome.server.runtime import Runtime
from mfdhome.themes import LCD
from tests.support import ha_state, load_test_config

T0 = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)
PANEL = LoggedEntity("alarm_control_panel.house", "ALARM PANEL", "SEC")


def panel(state: str) -> StateSnapshot:
    return snapshot_from_ha_states([ha_state("alarm_control_panel.house", state)])


def test_first_sight_is_a_baseline_then_changes_are_events() -> None:
    events, seen = state_events({}, panel("disarmed"), [PANEL], T0)
    assert events == [] and seen == {"alarm_control_panel.house": "disarmed"}
    events, seen = state_events(seen, panel("armed_away"), [PANEL], T0)
    assert events == [
        AlertEvent(T0, EventKind.STATE, entity_id="alarm_control_panel.house", state="armed_away")
    ]
    events, _ = state_events(seen, {}, [PANEL], T0)  # gone: unavailable
    assert events[0].state == "unavailable"


def test_runtime_logs_changes_but_not_startup_or_while_disconnected() -> None:
    runtime = Runtime(load_test_config())
    runtime.update(panel("disarmed"), T0)
    runtime.update(panel("arming"), T0 + timedelta(minutes=1))
    runtime.update({}, T0 + timedelta(minutes=2), connected=False)  # frozen: no event
    runtime.update(panel("armed_away"), T0 + timedelta(minutes=3))
    states = [e.state for e in runtime.history if e.kind is EventKind.STATE]
    assert states == ["arming", "armed_away"]


def test_log_rows_and_rendering() -> None:
    events = [
        AlertEvent(T0, EventKind.STATE, entity_id=PANEL.entity_id, state="armed_away"),
        AlertEvent(T0, EventKind.STATE, entity_id="sensor.retired", state="on"),  # not logged
    ]
    logged = {PANEL.entity_id: PANEL}
    [row] = log_rows(events, {}, (), logged)
    assert event_text(row) == "ARMED AWAY"
    assert log_rows(events, {}, ("WATER",), logged) == []  # filtered by system
    config = load_test_config()
    view = AlertView(config.alerts.alerts, config.alerts.systems, history=events, logged=logged)
    svg = alert_log(LogElement("log", (0, 0), (900, 200)), view, LCD)
    assert ">ALARM PANEL<" in svg and ">ARMED AWAY<" in svg and ">SEC<" in svg


def test_store_round_trip(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "h.jsonl")
    event = AlertEvent(T0, EventKind.STATE, entity_id=PANEL.entity_id, state="triggered")
    store.append([event])
    assert store.load() == [event]
    line = json.loads(store.path.read_text())
    assert line["entity"] == PANEL.entity_id and line["state"] == "triggered"


def test_config(tmp_path: Path) -> None:
    config = load_test_config()
    assert PANEL in config.alerts.logged
    assert "alerts:log" in entity_uses(config)["alarm_control_panel.house"]
    path = tmp_path / "alerts.yaml"
    path.write_text("log:\n  - {entity: switch.x, label: X, system: NOPE}\n")
    with pytest.raises(ConfigError, match=r"log\[0\]\.system: unknown system 'NOPE'"):
        load_alerts(path, Defs())
