"""Displays config, the alert-board store and the live runtime."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest

from mfdhome.config import ConfigError, load_config
from mfdhome.config.load import load_displays
from mfdhome.mfd import AlertState, Display, Phase
from mfdhome.model import StateSnapshot, snapshot_from_ha_states
from mfdhome.server.runtime import Runtime
from mfdhome.server.store import BoardStore, board_from_json, board_to_json
from tests.support import CONFIG, FIXTURES

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def states(name: str, minutes_ago: float | None = None) -> StateSnapshot:
    items = json.loads((FIXTURES / f"{name}.json").read_text())
    if minutes_ago is not None:
        for item in items:
            item["last_reported"] = (T0 - timedelta(minutes=minutes_ago)).isoformat()
    return snapshot_from_ha_states(items)


class TestDisplays:
    def test_load(self) -> None:
        displays = load_config(CONFIG).displays
        assert displays["workshop"] == Display(
            "workshop", "lcd", 1280, 800, "status", ("status", "electrical")
        )
        assert displays["hallway"].pages == ("electrical",)  # fixed to its home page

    def test_errors(self, tmp_path: Path) -> None:
        path = tmp_path / "displays.yaml"
        path.write_text(
            "displays:\n"
            "  a: {theme: plasma, size: [10, 10], home: nowhere, pages: [status, gone]}\n"
            "  b: {theme: lcd, size: [0, 10], home: status}\n"
        )
        with pytest.raises(ConfigError) as info:
            load_displays(path, {"status"})
        msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
        assert any(m.startswith("displays.b.size[0]: Input should be greater than 0") for m in msgs)
        path.write_text(
            "displays:\n"
            "  a: {theme: plasma, size: [10, 10], home: nowhere, pages: [status, gone]}\n"
        )
        with pytest.raises(ConfigError) as info:
            load_displays(path, {"status"})
        msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
        assert "displays.a.theme: unknown theme 'plasma'; expected: lcd, mirror, eink_mono" in msgs
        assert "displays.a.home: unknown page 'nowhere'" in msgs
        assert "displays.a.pages[1]: unknown page 'gone'" in msgs


class TestStore:
    BOARD: ClassVar[dict[str, AlertState]] = {
        "grid_lost": AlertState(Phase.ACTIVE_ACKED, T0, "workshop", T0 + timedelta(minutes=1)),
        "leak": AlertState(Phase.CLEARED_UNACKED, T0),
    }

    def test_round_trip(self, tmp_path: Path) -> None:
        store = BoardStore(tmp_path / "state" / "board.json")
        assert store.load() == {}  # nothing saved yet
        store.save(self.BOARD)
        assert store.load() == self.BOARD
        assert board_from_json(board_to_json(self.BOARD)) == self.BOARD

    def test_unreadable_or_malformed(self, tmp_path: Path) -> None:
        path = tmp_path / "board.json"
        path.write_text("{not json")
        assert BoardStore(path).load() == {}
        assert board_from_json({"x": {"phase": "bogus"}, "y": {"phase": "active_unacked"}}) == {
            "y": AlertState(Phase.ACTIVE_UNACKED)
        }


class TestRuntime:
    def runtime(self, tmp_path: Path) -> Runtime:
        return Runtime(load_config(CONFIG), BoardStore(tmp_path / "board.json"))

    def test_update_raises_and_persists(self, tmp_path: Path) -> None:
        rt = self.runtime(tmp_path)
        assert rt.update(states("electrical_islanded"), T0)
        assert rt.board["grid_lost"].phase is Phase.ACTIVE_UNACKED
        assert not rt.update(states("electrical_islanded"), T0)  # no change, no save
        assert Runtime(load_config(CONFIG), BoardStore(tmp_path / "board.json")).board == rt.board

    def test_acknowledge_by_system_and_all(self, tmp_path: Path) -> None:
        rt = self.runtime(tmp_path)
        rt.update(states("electrical_islanded"), T0)
        assert rt.acknowledge("workshop", T0, system="GRID")
        assert rt.board["grid_lost"].phase is Phase.ACTIVE_ACKED
        assert rt.board["battery_low"].phase is Phase.ACTIVE_UNACKED
        assert rt.acknowledge("workshop", T0)
        assert rt.board["battery_low"].acked_by == "workshop"
        assert not rt.acknowledge("workshop", T0)  # nothing left

    def test_stale_data_counts_as_missing(self, tmp_path: Path) -> None:
        rt = self.runtime(tmp_path)
        rt.update(states("electrical_normal", minutes_ago=1), T0)
        assert rt.state["sensor.grid_power"].available
        later = T0 + timedelta(hours=1)
        rt.update(states("electrical_normal", minutes_ago=1), later)  # same reports, an hour on
        assert not rt.state["sensor.grid_power"].available  # stale (test config: 15m)
        assert rt.board["grid_lost"].phase is Phase.ACTIVE_UNACKED

    def test_select_and_render(self, tmp_path: Path) -> None:
        rt = self.runtime(tmp_path)
        rt.update(states("electrical_islanded"), T0)
        assert 'data-page="status"' in rt.render("workshop")
        assert rt.select("workshop", "electrical")
        svg = rt.render("workshop")
        assert 'data-page="electrical"' in svg and 'width="1280" height="800"' in svg
        assert 'id="banner"' in svg and "GRID POWER LOST" in svg  # banner overlays any page
        assert not rt.select("hallway", "status")  # the mirror is fixed
        assert not rt.select("nope", "status")
        assert 'data-theme="mirror"' in rt.render("hallway")
