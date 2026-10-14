"""Groups: layout, scoped ids, derived channels, status and connection rules."""

import textwrap
from pathlib import Path
from typing import ClassVar

import pytest

from mfdhome.conditions import Value
from mfdhome.config import ConfigError, load_page
from mfdhome.model import (
    Aggregate,
    DerivedChannel,
    ElementRef,
    EntityRef,
    Frame,
    GroupElement,
    LineElement,
    Status,
    SymbolElement,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element
from mfdhome.render.alerts import NO_ALERTS
from mfdhome.render.resolve import Resolved, Resolver, derive
from mfdhome.themes import LCD
from tests.support import ha_state

HEADER = "page: p\ntitle: P\ncanvas: {width: 1000, height: 600}\nelements:\n"


def page(tmp_path: Path, elements: str) -> Path:
    path = tmp_path / "p.yaml"
    path.write_text(HEADER + textwrap.indent(textwrap.dedent(elements), "  "))
    return path


ARRAY = """\
- id: array
  type: group
  at: [100, 50]
  layout: {grid: {columns: 2, gap: 8, padding: 10}}
  channels:
    power: {sum: power}
    peak: {max: power}
    offline: {count: unavailable}
  item_defaults: {type: solar_panel}
  items:
    - {id: p1, bind: {power: sensor.p1}}
    - {id: p2, bind: {power: sensor.p2}}
    - {id: p3, bind: {power: sensor.p3}}
"""


def errors(path: Path) -> list[str]:
    with pytest.raises(ConfigError) as info:
        load_page(path)
    return [f"{i.loc}: {i.message}" for i in info.value.issues]


class TestLoading:
    def test_layout_and_scoped_ids(self, tmp_path: Path) -> None:
        [array] = load_page(page(tmp_path, ARRAY)).elements
        assert isinstance(array, GroupElement)
        # cells are the panel box (40 x 60); 2 columns, 2 rows
        assert array.size == (10 + 40 + 8 + 40 + 10, 10 + 60 + 8 + 60 + 10)
        assert [(i.id, i.at) for i in array.items if isinstance(i, SymbolElement)] == [
            ("array.p1", (130, 90)),
            ("array.p2", (178, 90)),
            ("array.p3", (130, 158)),
        ]
        assert array.channels["offline"] == DerivedChannel(Aggregate.COUNT, "unavailable")

    def test_nested_groups_scope_and_move_together(self, tmp_path: Path) -> None:
        path = page(
            tmp_path,
            """\
            - id: farm
              type: group
              at: [0, 0]
              layout: {grid: {columns: 2, padding: 0, gap: 0}}
              channels: {power: {sum: power}}
              items:
                - id: s1
                  type: group
                  layout: {grid: {columns: 1, padding: 0}}
                  channels: {power: {sum: power}}
                  items: [{id: p, type: solar_panel, bind: {power: sensor.a}}]
                - id: s2
                  type: group
                  layout: {grid: {columns: 1, padding: 0}}
                  channels: {power: {sum: power}}
                  items: [{id: p, type: solar_panel, bind: {power: sensor.b}}]
            """,
        )
        [farm] = load_page(path).elements
        assert isinstance(farm, GroupElement)
        s1, s2 = farm.items
        assert isinstance(s1, GroupElement) and isinstance(s2, GroupElement)
        assert (s1.id, s2.id) == ("farm.s1", "farm.s2")
        assert [i.id for i in s2.items] == ["farm.s2.p"]
        panel = s2.items[0]
        assert isinstance(panel, SymbolElement)
        assert s2.at == (40, 0) and panel.at == (60, 30)  # moved with its group

    def test_item_and_channel_errors(self, tmp_path: Path) -> None:
        path = page(
            tmp_path,
            """\
            - id: g
              type: group
              at: [0, 0]
              layout: {grid: {columns: 2}}
              channels:
                watts: {sum: wattage}
                both: {sum: power, max: power}
              status: {thresholds: {caution_low: 1}}
              items:
                - {id: a, type: solar_panel, at: [5, 5], bind: {power: sensor.a}}
                - {id: l, type: line, points: [[0, 0], [1, 1]]}
                - {id: b, type: solar_panel, bind: {power: sensor.b}}
                - {id: b, type: solar_panel, bind: {power: sensor.c}}
            """,
        )
        msgs = errors(path)
        assert "elements[0].items[0].at: items are positioned by the group's layout" in msgs
        assert (
            "elements[0].items[1].type: groups can contain symbols, tiles and groups, not 'line'"
            in msgs
        )
        assert "elements[0].items[3].id: duplicate item id 'b'" in msgs
        assert (
            "elements[0].channels.watts.sum: no item has channel 'wattage'; item channels: power"
            in msgs
        )
        assert any("channels.both: give exactly one of" in m for m in msgs)
        assert "elements[0].status: groups have no primary channel; give 'from'" in msgs

    def test_lines_connect_to_the_group_not_its_items(self, tmp_path: Path) -> None:
        path = page(
            tmp_path,
            ARRAY
            + textwrap.dedent(
                """\
            - {id: ok, type: line, from: array.bottom, to: [0, 0], bind: {power: array.power}}
            - {id: bad, type: line, from: array.p1.top, to: [0, 0]}
            - {id: bad2, type: line, from: array.p1, to: [0, 0]}
            """
            ),
        )
        msgs = errors(path)
        assert len(msgs) == 2
        assert all("items of group 'array' connect only through the group" in m for m in msgs)

    def test_element_channel_bindings(self, tmp_path: Path) -> None:
        path = page(
            tmp_path,
            ARRAY
            + textwrap.dedent(
                """\
            - {id: feed, type: line, points: [[0, 0], [1, 0]], bind: {power: array.power}}
            - {id: entity, type: line, points: [[0, 0], [1, 0]], bind: {power: sensor.grid}}
            """
            ),
        )
        elements = {e.id: e for e in load_page(path).elements}
        feed, entity = elements["feed"], elements["entity"]
        assert isinstance(feed, LineElement) and isinstance(entity, LineElement)
        assert feed.bind == {"power": ElementRef("array", "power")}
        assert entity.bind == {"power": EntityRef("sensor.grid")}

    def test_element_binding_errors(self, tmp_path: Path) -> None:
        path = page(
            tmp_path,
            ARRAY
            + textwrap.dedent(
                """\
            - {id: n, type: node, at: [0, 0]}
            - {id: f1, type: line, points: [[0, 0], [1, 0]], bind: {power: array.voltage}}
            - {id: f2, type: line, points: [[0, 0], [1, 0]], bind: {power: n.power}}
            - {id: bat, type: battery, at: [0, 0], bind: {level: sensor.soc, power: array.power}}
            - {id: f3, type: line, points: [[0, 0], [1, 0]], bind: {power: bat.power}}
            """
            ),
        )
        msgs = errors(path)
        assert (
            "elements[2].bind.power: 'array' has no channel 'voltage'; "
            "expected: offline, peak, power"
        ) in msgs
        assert "elements[3].bind.power: 'n' has no channels to bind to" in msgs
        assert any("bat.power is itself bound to an element" in m for m in msgs)


class TestResolution:
    ITEMS: ClassVar[list[Resolved]] = [
        Resolved(Status.NORMAL, {"power": Value("100", "W")}),
        Resolved(Status.NORMAL, {"power": Value("300", "W")}),
        Resolved(Status.UNAVAILABLE, {"power": Value(None)}),
    ]

    @pytest.mark.parametrize(
        ("aggregate", "source", "expected"),
        [
            (Aggregate.SUM, "power", 400.0),
            (Aggregate.MIN, "power", 100.0),
            (Aggregate.MAX, "power", 300.0),
            (Aggregate.COUNT, "unavailable", 1.0),
            (Aggregate.COUNT, "normal", 2.0),
        ],
    )
    def test_derive(self, aggregate: Aggregate, source: str, expected: float) -> None:
        assert derive(DerivedChannel(aggregate, source), self.ITEMS).number == expected

    def test_derive_keeps_unit_and_handles_no_data(self) -> None:
        assert derive(DerivedChannel(Aggregate.SUM, "power"), self.ITEMS).unit == "W"
        none = [Resolved(Status.UNAVAILABLE, {"power": Value(None)})]
        assert not derive(DerivedChannel(Aggregate.SUM, "power"), none).available

    def _array(self, tmp_path: Path, rule: str = "") -> GroupElement:
        [array] = load_page(page(tmp_path, ARRAY + rule)).elements
        assert isinstance(array, GroupElement)
        return array

    def _status(self, array: GroupElement, *states: tuple[str, str]) -> Status:
        snap = snapshot_from_ha_states([ha_state(e, v) for e, v in states])
        resolved = Resolver(snap, NO_ALERTS).element(array)
        assert resolved is not None
        return resolved.status

    def test_default_group_status(self, tmp_path: Path) -> None:
        array = self._array(tmp_path)
        live = [("sensor.p1", "1"), ("sensor.p2", "2"), ("sensor.p3", "3")]
        assert self._status(array, *live) is Status.NORMAL
        assert self._status(array, *live[:2]) is Status.NORMAL  # one dead panel: still normal
        assert self._status(array) is Status.UNAVAILABLE  # every item unavailable

    def test_worst_item_caution_bubbles_up(self, tmp_path: Path) -> None:
        path = page(
            tmp_path,
            """\
            - id: banks
              type: group
              at: [0, 0]
              layout: {grid: {columns: 2}}
              item_defaults: {type: battery, status: {thresholds: {caution_low: 20}}}
              items:
                - {id: a, bind: {level: sensor.a}}
                - {id: b, bind: {level: sensor.b}}
            """,
        )
        [banks] = load_page(path).elements
        assert isinstance(banks, GroupElement)
        assert self._status(banks, ("sensor.a", "90"), ("sensor.b", "15")) is Status.CAUTION

    def test_rules_on_derived_channels(self, tmp_path: Path) -> None:
        rule = textwrap.indent(
            "status:\n  rules: [{level: warning, when: [{channel: offline, ge: 2}]}]\n", "  "
        )
        array = self._array(tmp_path, rule)
        assert self._status(array, ("sensor.p1", "1")) is Status.WARNING


def test_group_frame_reflects_status(tmp_path: Path) -> None:
    [array] = load_page(page(tmp_path, ARRAY)).elements
    live = snapshot_from_ha_states([ha_state(f"sensor.p{i}", "5") for i in (1, 2, 3)])
    normal = render_element(array, live, LCD)
    assert f'stroke="{LCD.dim}"' in normal  # calm frame when normal
    assert normal.count('<g id="array.p') == 3  # items nested inside the group
    assert 'stroke-dasharray="0 6"' in render_element(array, {}, LCD)  # dotted when unavailable


def test_frameless_group_draws_no_frame(tmp_path: Path) -> None:
    from dataclasses import replace

    [array] = load_page(page(tmp_path, ARRAY)).elements
    assert isinstance(array, GroupElement)
    bare = render_element(replace(array, frame=Frame.NONE), {}, LCD)
    assert bare.startswith('<g id="array"><g id="array.p1">')
