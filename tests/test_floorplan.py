"""Floorplans: rooms, walls, doors and windows, the alarm panel, and the security page."""

import re
import textwrap
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.config import ConfigError, Defs, load_page
from mfdhome.model import (
    EntityRef,
    Orientation,
    Page,
    RoomElement,
    Status,
    SymbolElement,
    WallElement,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element, render_page
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import element_box
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import config_page, fixture_state, ha_state

SQUARE = ((0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0))
TABLET = Target("tablet", 1280, 768)


def write_page(tmp_path: Path, elements: str) -> Page:
    path = tmp_path / "p.yaml"
    body = "page: p\ntitle: P\ncanvas: {width: 1000, height: 600}\nelements:\n"
    path.write_text(body + textwrap.indent(textwrap.dedent(elements), "  "))
    return load_page(path, Defs())


class TestStructure:
    def test_quiet_room_is_structure_colored_with_its_name_in_the_middle(self) -> None:
        svg = render_element(RoomElement("r", SQUARE, "DEN"), {}, LCD)
        assert f'stroke="{LCD.structure_color}"' in svg and ">DEN<" in svg
        assert '<text x="50" y="40"' in svg
        moved = render_element(RoomElement("r", SQUARE, "DEN", label_at=(20, 10)), {}, LCD)
        assert '<text x="20" y="10"' in moved

    def test_room_takes_a_status_color_when_its_rules_say_so(self, tmp_path: Path) -> None:
        page = write_page(
            tmp_path,
            """\
            - id: den
              type: room
              points: [[0, 0], [100, 0], [100, 80], [0, 80]]
              name: DEN
              status: {rules: [{level: warning, when: [{entity: binary_sensor.smoke, eq: "on"}]}]}
            """,
        )
        [den] = page.elements
        smoke = snapshot_from_ha_states([ha_state("binary_sensor.smoke", "on")])
        assert f'stroke="{LCD.color(Status.WARNING)}"' in render_element(den, smoke, LCD)

    def test_rooms_have_no_channels(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="channel 'state' is not bound"):
            write_page(
                tmp_path,
                """\
                - id: den
                  type: room
                  points: [[0, 0], [100, 0], [100, 80]]
                  status: {rules: [{level: caution, when: [{channel: state, eq: "on"}]}]}
                """,
            )

    def test_exterior_walls_are_heavier(self) -> None:
        inner = render_element(WallElement("w", SQUARE), {}, LCD)
        outer = render_element(WallElement("w", SQUARE, exterior=True), {}, LCD)
        assert 'stroke-width="2"' in inner and 'stroke-width="5"' in outer
        assert f'stroke="{LCD.structure_color}"' in outer


def opening(
    state: str | None, params: dict[str, object] | None = None, vertical: bool = False
) -> SymbolElement:
    return SymbolElement(
        "o",
        "opening",
        (100, 100),
        bind={} if state is None else {"state": EntityRef("binary_sensor.door")},
        params=get_symbol("opening").params(params or {}),
        orientation=Orientation.VERTICAL if vertical else Orientation.HORIZONTAL,
    )


def draw(element: SymbolElement, state: str | None) -> str:
    items = [] if state is None else [ha_state("binary_sensor.door", state)]
    return render_element(element, snapshot_from_ha_states(items), LCD)


class TestOpenings:
    def test_door_closed_across_the_gap_and_open_with_its_swing(self) -> None:
        closed = draw(opening("off"), "off")
        assert '<line x1="82" y1="100" x2="118" y2="100"' in closed  # the leaf, hinge to frame
        assert "<path" not in closed
        swung = draw(opening("on"), "on")
        assert '<line x1="82" y1="100" x2="82" y2="64"' in swung  # leaf up at 90 degrees
        assert '<path d="M82 64 A36 36 0 0 1 118 100"' in swung  # arc back to the frame

    def test_hinge_and_swing_side(self) -> None:
        other = draw(opening("on", {"hinge": "end", "swing": "down"}), "on")
        assert '<line x1="118" y1="100" x2="118" y2="136"' in other
        assert '<path d="M118 136 A36 36 0 0 1 82 100"' in other
        vertical = draw(opening("on", {"swing": "right"}, vertical=True), "on")
        assert '<line x1="100" y1="82" x2="136" y2="82"' in vertical

    def test_window_double_line_closed_and_a_slid_sash_open(self) -> None:
        params = {"kind": "window", "length": 40}
        closed = draw(opening("off", params), "off")
        assert closed.count(f'stroke="{LCD.color(Status.NORMAL)}"') == 2
        opened = draw(opening("on", params), "on")
        assert '<line x1="80" y1="97.5" x2="100" y2="97.5"' in opened  # half, aside

    def test_wall_is_cut_under_the_opening(self) -> None:
        assert f'stroke="{LCD.background}" stroke-width="7"' in draw(opening("off"), "off")

    def test_box_covers_the_swing(self) -> None:
        assert element_box(opening(None)).top == 64
        assert element_box(opening(None, {"swing": "down"})).bottom == 136
        assert element_box(opening(None, {"kind": "window"})).top == 95

    def test_no_data_is_dotted_and_unbound_is_closed(self) -> None:
        assert "stroke-dasharray" in draw(opening("unavailable"), "unavailable")
        assert "<path" not in draw(opening(None), None)

    @pytest.mark.parametrize(
        ("params", "error"),
        [
            ({"kind": "hatch"}, "'kind' must be door or window"),
            ({"length": 4}, "'length' must be a number from 8 to 400"),
            ({"swing": "inward"}, "'swing' must be one of: up, left, down, right"),
            ({"hinge": "middle"}, "'hinge' must be start or end"),
        ],
    )
    def test_params(self, params: dict[str, object], error: str) -> None:
        with pytest.raises(ValueError, match=error):
            get_symbol("opening").params(params)


class TestAlarmPanel:
    def panel(self, state: str) -> str:
        element = SymbolElement(
            "a", "alarm_panel", (100, 100), bind={"state": EntityRef("alarm_control_panel.h")}
        )
        snapshot = snapshot_from_ha_states([ha_state("alarm_control_panel.h", state)])
        return render_element(element, snapshot, LCD)

    def test_states_in_words(self) -> None:
        assert ">DISARMED<" in self.panel("disarmed")
        assert ">ENTRY DELAY<" in self.panel("pending")
        assert ">SOMETHING NEW<" in self.panel("something_new")

    def test_armed_is_drawn_in_the_active_color(self) -> None:
        assert f'stroke="{LCD.color(Status.ACTIVE)}"' in self.panel("armed_home")
        assert f'stroke="{LCD.color(Status.NORMAL)}"' in self.panel("disarmed")

    def test_no_data(self) -> None:
        svg = self.panel("unavailable")
        assert ">---<" in svg and "stroke-dasharray" in svg


@pytest.mark.parametrize("theme", [LCD, MIRROR, EINK_MONO, EINK_COLOR], ids=lambda t: t.name)
@pytest.mark.parametrize("name", ["disarmed", "armed", "triggered"])
def test_security_snapshot(name: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    svg = render_page(config_page("security"), fixture_state(f"security_{name}"), theme, TABLET)
    assert svg == svg_snapshot
    assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_open_while_armed_is_a_caution() -> None:
    page = config_page("security")
    caution = LCD.color(Status.CAUTION)
    window = next(e for e in page.elements if e.id == "kitchen_window")
    assert caution in render_element(window, fixture_state("security_armed"), LCD)
    assert caution not in render_element(window, fixture_state("security_disarmed"), LCD)
