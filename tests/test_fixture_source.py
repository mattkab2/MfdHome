"""Tests for the JSON fixture source."""

import json
from pathlib import Path

import pytest

from mfdhome.sources import load_fixture
from tests.support import FIXTURES


def test_load_fixture_parses_ha_states() -> None:
    snap = load_fixture(FIXTURES / "electrical_normal.json")
    assert snap["sensor.grid_power"].state == "300"
    assert snap["sensor.grid_power"].attributes["unit_of_measurement"] == "W"
    assert snap["switch.main_breaker"].available


def test_load_fixture_skips_malformed_items(tmp_path: Path) -> None:
    path = tmp_path / "states.json"
    path.write_text(json.dumps([{"state": "1"}, {"entity_id": "sensor.a", "state": "2"}]))
    snap = load_fixture(path)
    assert list(snap) == ["sensor.a"]
    assert dict(snap["sensor.a"].attributes) == {}


def test_load_fixture_rejects_non_list(tmp_path: Path) -> None:
    path = tmp_path / "states.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="expected a JSON list"):
        load_fixture(path)
