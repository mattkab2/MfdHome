"""The water page and its alerts (example config): municipal supply, gas, detectors."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.config import load_config
from mfdhome.model import StateSnapshot, snapshot_from_ha_states
from mfdhome.render import render_page
from mfdhome.server.runtime import Runtime
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import FIXTURES, config_page, fixture_state

EXAMPLES = Path(__file__).parent.parent / "examples"
TABLET = Target("tablet", 1280, 768)
THEMES = [LCD, MIRROR, EINK_MONO, EINK_COLOR]
T0 = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)


def scenario(name: str) -> StateSnapshot:
    return {} if name == "no_data" else fixture_state(f"water_{name}")


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("name", ["normal", "irrigation", "leak", "no_data"])
def test_water_snapshot(name: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    svg = render_page(config_page("water"), scenario(name), theme, TABLET)
    assert svg == svg_snapshot
    assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_test_page_matches_the_example() -> None:
    page = "pages/water.yaml"
    assert (FIXTURES / "config" / page).read_text() == (EXAMPLES / "config" / page).read_text()


class House:
    """The example config's runtime, fed from the quiet example house plus changes."""

    def __init__(self) -> None:
        self.runtime = Runtime(load_config(EXAMPLES / "config"))
        items = json.loads((EXAMPLES / "scenarios" / "house_normal.json").read_text())
        self.states = {item["entity_id"]: item for item in items}

    def at(self, minutes: float, **changes: str) -> set[str]:
        """Apply state changes at ``minutes``; the ids of alerts raised on the board."""
        for entity_id, state in changes.items():
            entity_id = entity_id.replace("__", ".")
            self.states[entity_id] = {
                **self.states.get(entity_id, {}),
                "entity_id": entity_id,
                "state": state,
            }
        snapshot = snapshot_from_ha_states(list(self.states.values()))
        self.runtime.update(snapshot, T0 + timedelta(minutes=minutes))
        return set(self.runtime.board)


def test_a_leak_is_a_warning_at_once() -> None:
    house = House()
    assert house.at(0) == set()
    assert "leak_detected" in house.at(1, binary_sensor__leak_water_heater="on")


def test_continuous_flow_waits_half_an_hour_and_ignores_irrigation() -> None:
    house = House()
    assert "continuous_flow" not in house.at(0, sensor__water_flow="0.4")
    assert "continuous_flow" not in house.at(29, sensor__water_flow="0.4")
    assert "continuous_flow" in house.at(30, sensor__water_flow="0.4")
    watering = House()
    watering.at(0, sensor__water_flow="6.5", valve__irrigation="open")
    raised = watering.at(45, sensor__water_flow="6.5", valve__irrigation="open")
    assert "continuous_flow" not in raised and "irrigation_running" in raised


def test_dead_detectors_are_cautions_after_ten_minutes() -> None:
    house = House()
    house.at(
        0, binary_sensor__leak_basement="unavailable", binary_sensor__co_detector="unavailable"
    )
    assert not {"leak_sensor_offline", "gas_detector_offline"} & house.at(9)
    assert {"leak_sensor_offline", "gas_detector_offline"} <= house.at(10)


def test_gas_and_co_are_warnings() -> None:
    house = House()
    raised = house.at(0, binary_sensor__gas_leak="on", binary_sensor__co_detector="on")
    alerts = house.runtime.config.alerts.by_id()
    assert {"gas_detected", "co_detected"} <= raised
    assert {alerts[a].severity.value for a in ("gas_detected", "co_detected")} == {"warning"}
