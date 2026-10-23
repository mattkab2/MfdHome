"""Displays config, the alert-board store and the live runtime."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest

from mfdhome.config import ConfigError, load_config, load_defs, load_page
from mfdhome.config.load import load_displays
from mfdhome.mfd import AlertState, Display, Phase
from mfdhome.mfd.keys import DEFAULT_ACTIONS, Action
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
            "workshop", "lcd", 1280, 800, "status", ("status", "electrical", "log"), "status"
        )
        hallway = displays["hallway"]
        assert hallway.pages == ("electrical",) and not hallway.controls  # fixed, no keys

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
        assert (
            "displays.a.theme: unknown theme 'plasma'; expected: lcd, mirror, eink_mono, eink_color"
            in msgs
        )
        assert "displays.a.home: unknown page 'nowhere'" in msgs
        assert "displays.a.pages[1]: unknown page 'gone'" in msgs

    def test_panel(self, tmp_path: Path) -> None:
        path = tmp_path / "displays.yaml"
        path.write_text(
            "displays:\n"
            "  kitchen: {theme: eink_color, size: [800, 480], home: status, panel: spectra6}\n"
        )
        assert load_displays(path, {"status"})["kitchen"].panel == "spectra6"
        path.write_text(
            "displays:\n"
            "  a: {theme: eink_mono, size: [800, 480], home: status, panel: plasma}\n"
            "  b: {theme: eink_color, size: [800, 480], home: status, panel: mono}\n"
        )
        with pytest.raises(ConfigError) as info:
            load_displays(path, {"status"})
        msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
        assert msgs[0].startswith("displays.a.panel: unknown panel 'plasma'; expected: mono")
        assert msgs[1].startswith("displays.b.panel: panel 'mono' cannot show theme 'eink_color'")


class TestTiming:
    def load(self, tmp_path: Path, *lines: str) -> dict[str, Display]:
        path = tmp_path / "displays.yaml"
        path.write_text("displays:\n" + "".join(f"  {line}\n" for line in lines))
        return load_displays(path, {"status"})

    def test_panels_average_over_their_refresh(self, tmp_path: Path) -> None:
        panel = "{theme: eink_mono, size: [800, 480], home: status, panel: mono"
        displays = self.load(
            tmp_path,
            f"a: {panel}}}",
            f"b: {panel}, refresh: 2m}}",
            f"c: {panel}, refresh: 2m, average: 1m}}",
            f"d: {panel}, average: 0}}",
        )
        minutes = timedelta(minutes=1)
        assert (displays["a"].refresh, displays["a"].average) == (5 * minutes, 5 * minutes)
        assert (displays["b"].refresh, displays["b"].average) == (2 * minutes, 2 * minutes)
        assert displays["c"].average == minutes
        assert displays["d"].refresh == 5 * minutes and displays["d"].average is None  # live

    def test_browser_displays_are_live_unless_asked(self, tmp_path: Path) -> None:
        displays = self.load(
            tmp_path,
            "a: {theme: lcd, size: [10, 10], home: status}",
            "b: {theme: mirror, size: [10, 10], home: status, average: 30s}",
        )
        assert displays["a"].refresh is None and displays["a"].average is None
        assert displays["b"].average == timedelta(seconds=30)

    def test_limits(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError) as info:
            self.load(
                tmp_path,
                "a: {theme: lcd, size: [10, 10], home: status, refresh: 1m}",
                "b: {theme: eink_mono, size: [10, 10], home: status, panel: mono, refresh: 5s}",
                "c: {theme: lcd, size: [10, 10], home: status, average: 2h}",
            )
        assert [f"{i.loc}: {i.message}" for i in info.value.issues] == [
            "displays.a.refresh: refresh is for e-paper panels, which fetch on a timer",
            "displays.b.refresh: refresh must be at least 10s",
            "displays.c.average: average must be at most 1h",
        ]

    def test_averaging_overrides_are_house_wide(self, tmp_path: Path) -> None:
        defs = tmp_path / "defs.yaml"
        defs.write_text("averaging: {entities: {sensor.soc: false, sensor.tpl: true}}\n")
        assert load_defs(defs).averaging.entities == {"sensor.soc": False, "sensor.tpl": True}
        page = tmp_path / "p.yaml"
        page.write_text(
            "page: p\ntitle: P\ncanvas: {width: 1, height: 1}\n"
            "defs: {averaging: {entities: {sensor.soc: false}}}\n"
        )
        with pytest.raises(ConfigError, match=r"averaging is house-wide: set it in defs\.yaml"):
            load_page(page)


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


class TestSoftKeys:
    def test_display_options(self, tmp_path: Path) -> None:
        path = tmp_path / "displays.yaml"
        path.write_text(
            "displays:\n"
            "  a: {theme: lcd, size: [10, 10], home: electrical, alerts_page: status}\n"
            "  b: {theme: lcd, size: [10, 10], home: status}\n"
        )
        displays = load_displays(path, {"status", "electrical"})
        a, b = displays["a"], displays["b"]
        assert a.pages == ("electrical", "status") and a.controls  # alerts page is selectable
        assert not b.controls  # one page: nothing to change to, no keys
        path.write_text(
            "displays:\n  a: {theme: lcd, size: [1, 1], home: status, controls: none}\n"
        )
        with pytest.raises(ConfigError, match="controls: Extra inputs are not permitted"):
            load_displays(path, {"status"})
        path.write_text(
            "displays:\n  a: {theme: lcd, size: [1, 1], home: status, alerts_page: x}\n"
        )
        with pytest.raises(ConfigError, match="alerts_page: unknown page 'x'"):
            load_displays(path, {"status"})

    def test_step_wraps(self) -> None:
        d = Display("d", "lcd", 1, 1, "a", ("a", "b", "c"))
        assert [d.step("a", 1), d.step("c", 1), d.step("a", -1)] == ["b", "a", "c"]

    def test_press(self, tmp_path: Path) -> None:
        rt = TestRuntime().runtime(tmp_path)

        def press(key: str) -> Action | None:
            return rt.press("workshop", key, T0)

        assert press("1") is Action.PREV and rt.selected["workshop"] == "log"  # wraps back
        assert press("4") is Action.NEXT and rt.selected["workshop"] == "status"  # and forward
        assert press("4") is Action.NEXT and rt.selected["workshop"] == "electrical"
        assert press("2") is Action.ALERTS and rt.selected["workshop"] == "status"
        assert press("2") is None  # ACK on the alerts page, with nothing to acknowledge
        assert press("3") is Action.LOCK and rt.locked["workshop"]
        assert press("4") is None  # locked
        assert rt.selected["workshop"] == "status"
        assert press("3") is Action.LOCK and not rt.locked["workshop"]
        assert press("next") is None and press("5") is None
        assert rt.press("nope", "4", T0) is None

    def test_key_actions_follow_the_page(self, tmp_path: Path) -> None:
        rt = TestRuntime().runtime(tmp_path)
        assert rt.actions("workshop") == (Action.PREV, Action.ACK, Action.LOCK, Action.NEXT)
        rt.press("workshop", "4", T0)
        assert rt.actions("workshop") == DEFAULT_ACTIONS

    def test_ack_key_acknowledges_the_banner_alert(self, tmp_path: Path) -> None:
        rt = TestRuntime().runtime(tmp_path)
        rt.update(states("electrical_islanded"), T0)
        assert rt.press("workshop", "2", T0) is Action.ACK
        assert rt.board["grid_lost"].phase is Phase.ACTIVE_ACKED  # the most urgent first
        assert rt.board["grid_lost"].acked_by == "workshop"
        assert rt.board["battery_low"].phase is Phase.ACTIVE_UNACKED
        assert rt.press("workshop", "2", T0) is Action.ACK  # then the next one
        assert rt.press("workshop", "2", T0) is None  # nothing left

    def test_render_shows_keys_only_where_configured(self, tmp_path: Path) -> None:
        rt = TestRuntime().runtime(tmp_path)
        rt.update(states("electrical_islanded"), T0)
        workshop = rt.render("workshop")
        assert '<g id="controls">' in workshop and '<g id="key-2"><g class="attn">' in workshop
        assert ">ACK<" in workshop  # status is the alerts page
        assert '<g id="controls">' not in rt.render("hallway")
        rt.press("workshop", "4", T0)
        assert ">ALERTS<" in rt.render("workshop")
        rt.press("workshop", "3", T0)
        assert ">LOCKED<" in rt.render("workshop")
