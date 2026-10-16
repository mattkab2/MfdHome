"""Tests for YAML page and defs loading."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.conditions import ChannelRef, Condition, EvalContext, Op, holds
from mfdhome.config import ConfigError, Defs, load_config, load_defs, load_page
from mfdhome.layout import Anchor
from mfdhome.model import (
    EntityRef,
    FlowSpec,
    LineElement,
    Name,
    Readout,
    Status,
    SymbolElement,
    TextElement,
    snapshot_from_ha_states,
)
from mfdhome.render.status import element_status
from tests.support import ha_state

HEADER = """\
page: test
title: Test
canvas: {width: 100, height: 100}
"""


def write(tmp_path: Path, body: str, name: str = "page.yaml") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body))
    return path


def page_file(tmp_path: Path, elements: str, defs: str = "") -> Path:
    body = HEADER + (textwrap.dedent(defs) if defs else "") + "elements:\n"
    body += textwrap.indent(textwrap.dedent(elements), "  ")
    return write(tmp_path, body)


def errors(path: Path, defs: Defs | None = None) -> list[str]:
    with pytest.raises(ConfigError) as info:
        load_page(path, defs)
    return [f"{i.line}: {i.loc}: {i.message}" for i in info.value.issues]


class TestValidPages:
    def test_shorthands(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: grid
              type: line
              from: [0, 0]
              to: [10, 0]
              bind: {rate: sensor.grid_power}
              flow: true
              name: GRID
              readouts: [{value: rate, format: power, abs: true}]
            - {id: label, type: text, at: [5, 5], text: Hi, align: start}
            """,
        )
        page = load_page(path)
        line, text = page.elements
        assert line == LineElement(
            "grid",
            ((0, 0), (10, 0)),
            bind={"rate": EntityRef("sensor.grid_power")},
            name=Name("GRID"),
            readouts=(Readout("rate", "power", None, True),),
            flow=FlowSpec("rate", 0.0),  # 'flow: true': any nonzero rate
        )
        assert text == TextElement("label", (5, 5), "Hi", "start")
        assert (page.id, page.width, page.height) == ("test", 100, 100)

    def test_symbol_with_anchors_params_and_attribute(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [50, 50]
              orientation: vertical
              bind:
                state: {entity: sensor.panel, attribute: main}
              params: {closed: [engaged]}
              name: {text: MAIN, anchor: center-left, offset: [-2, 0]}
            """,
        )
        [br] = load_page(path).elements
        assert isinstance(br, SymbolElement)
        assert br.bind == {"state": EntityRef("sensor.panel", "main")}
        assert br.params == {"closed": frozenset({"engaged"})}
        assert br.name == Name("MAIN", Anchor.CENTER_LEFT, 0.5, (-2, 0))

    def test_on_off_stay_strings(self, tmp_path: Path) -> None:
        # YAML 1.1 parsers turn bare on/off into booleans; YAML 1.2 must not.
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [50, 50]
              bind: {state: switch.main}
              status:
                map: {on: normal, off: caution}
                default: warning
            """,
        )
        [br] = load_page(path).elements
        assert isinstance(br, SymbolElement)
        for raw, expected in [
            ("on", Status.NORMAL),
            ("off", Status.CAUTION),
            ("x", Status.WARNING),
        ]:
            context = EvalContext(snapshot_from_ha_states([ha_state("switch.main", raw)]), br.bind)
            assert element_status(br.status, context, "state") is expected

    def test_cross_entity_rules_and_named_conditions(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [50, 50]
              bind: {state: switch.main}
              status:
                rules:
                  - level: warning
                    any:
                      - all:
                          - {channel: state, eq: off}
                          - {use: grid_down}
                      - {channel: state, eq: tripped}
            """,
            defs="""\
            defs:
              conditions:
                grid_down:
                  any:
                    - {entity: sensor.grid_power, unavailable: true}
                    - {entity: sensor.grid_voltage, lt: 50}
            """,
        )
        [br] = load_page(path).elements
        assert isinstance(br, SymbolElement)
        [rule] = br.status.rules
        # (off AND grid unavailable) OR (off AND low voltage) OR tripped
        assert len(rule.when.terms) == 3
        assert rule.when.terms[2].conditions == (Condition(ChannelRef("state"), Op.EQ, "tripped"),)

        def warn(*items: dict[str, object]) -> bool:
            return holds(rule.when, EvalContext(snapshot_from_ha_states(items), br.bind))

        assert warn(ha_state("switch.main", "off"))
        assert warn(
            ha_state("switch.main", "off"),
            ha_state("sensor.grid_power", "0"),
            ha_state("sensor.grid_voltage", "0"),
        )
        assert not warn(
            ha_state("switch.main", "off"),
            ha_state("sensor.grid_power", "0"),
            ha_state("sensor.grid_voltage", "240"),
        )
        assert warn(ha_state("switch.main", "tripped"), ha_state("sensor.grid_power", "0"))

    def test_shared_defs_and_load_config(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            """\
            thresholds:
              soc: {warning_low: 10, caution_low: 25}
            conditions:
              low: {when: [{channel: level, lt: 30}]}
              lower: {when: [{use: low}, {channel: level, lt: 20}]}
            """,
            "defs.yaml",
        )
        for name in ("a", "b"):
            write(
                tmp_path,
                f"""\
                page: {name}
                title: {name}
                canvas: {{width: 10, height: 10}}
                elements:
                  - id: bat
                    type: battery
                    at: [5, 5]
                    bind: {{level: sensor.soc}}
                    status:
                      thresholds: soc
                      rules: [{{level: caution, when: [{{use: lower}}]}}]
                """,
                f"pages/{name}.yaml",
            )
        config = load_config(tmp_path)
        assert sorted(config.pages) == ["a", "b"]
        assert set(config.defs.conditions) == {"low", "lower"}
        assert len(config.defs.conditions["lower"].terms[0].conditions) == 2

    def test_config_without_defs(self, tmp_path: Path) -> None:
        write(tmp_path, HEADER, "pages/test.yaml")
        assert list(load_config(tmp_path).pages) == ["test"]


class TestErrors:
    def test_unknown_key_points_at_line(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: g
              type: line
              from: [0, 0]
              to: [1, 0]
              colour: red
            """,
        )
        assert errors(path) == ["9: elements[0].colour: Extra inputs are not permitted"]

    def test_unknown_and_missing_channels(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [0, 0]
              bind:
                voltage: sensor.v
            """,
        )
        assert errors(path) == [
            "9: elements[0].bind.voltage: unknown channel 'voltage' for breaker; expected: state",
            "8: elements[0].bind: required channel 'state' is not bound",
        ]

    def test_unknown_type(self, tmp_path: Path) -> None:
        path = page_file(tmp_path, "- {id: t, type: teapot, at: [0, 0]}\n")
        [msg] = errors(path)
        assert msg.startswith("5: elements[0].type: unknown type 'teapot'; expected: line, text,")

    def test_reference_errors(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: bat
              type: battery
              at: [0, 0]
              bind: {level: sensor.soc}
              name: {text: B, anchor: upper-left}
              status:
                thresholds: nope
                rules:
                  - {level: warning, when: [{use: missing}, {channel: power, gt: 1}]}
              readouts:
                - {value: power}
                - {value: level, format: bogus}
            """,
        )
        msgs = errors(path)
        assert any("name.anchor: unknown anchor 'upper-left'" in m for m in msgs)
        assert any("status.thresholds: unknown thresholds 'nope'" in m for m in msgs)
        assert any("rules[0].when[0].use: unknown condition 'missing'" in m for m in msgs)
        assert any("rules[0].when[1].channel: channel 'power' is not bound" in m for m in msgs)
        assert any("readouts[0].value: channel 'power' is not bound" in m for m in msgs)
        assert any("readouts[1].format: unknown format 'bogus'" in m for m in msgs)

    def test_condition_shape_errors(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [0, 0]
              bind: {state: switch.main}
              status:
                rules:
                  - level: warning
                    when:
                      - {channel: state, eq: off, ne: on}
                      - all: [{channel: state, eq: off}]
                  - {level: severe, when: []}
                  - {level: caution, any: [], when: []}
            """,
        )
        msgs = errors(path)
        assert any("when[0]: a condition needs exactly one predicate" in m for m in msgs)
        assert any(
            "rules[1].level: Input should be 'normal', 'caution' or 'warning'" in m for m in msgs
        )
        assert any("rules[2]: give exactly one of 'any' or 'when'" in m for m in msgs)

    def test_nested_all_rejected(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [0, 0]
              bind: {state: switch.main}
              status:
                rules:
                  - level: warning
                    when:
                      - all: [{channel: state, eq: off}]
            """,
        )
        [msg] = errors(path)
        assert "when[0].all: 'all' groups are only allowed directly under 'any'" in msg

    def test_condition_cycle(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            "[]\n",
            defs="""\
            defs:
              conditions:
                a: {when: [{use: b}]}
                b: {when: [{use: a}]}
            """,
        )
        assert any("condition cycle: a -> b -> a" in m for m in errors(path))

    def test_bad_entity_and_params(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: br
              type: breaker
              at: [0, 0]
              bind: {state: main_breaker}
              params: {closed: on, colour: red}
            """,
        )
        msgs = errors(path)
        assert any("bind.state.entity: String should match pattern" in m for m in msgs)

    def test_duplicate_ids_and_multiple_errors(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - {id: a, type: text, at: [0, 0], text: x}
            - {id: a, type: text, at: [0, 0], text: y}
            - {id: b, type: text, at: [0, 0]}
            """,
        )
        msgs = errors(path)
        assert "6: elements[1].id: duplicate element id 'a'" in msgs
        assert "7: elements[2].text: Field required" in msgs

    def test_yaml_syntax_and_duplicate_keys(self, tmp_path: Path) -> None:
        assert errors(write(tmp_path, HEADER + "elements: [\n"))[0].startswith("5:")
        dupes = write(tmp_path, HEADER + "title: Again\n", "dupes.yaml")
        assert errors(dupes)[0].startswith("4:")

    def test_page_defs_cannot_redefine_shared(self, tmp_path: Path) -> None:
        shared = write(tmp_path, "thresholds: {soc: {caution_low: 20}}\n", "defs.yaml")
        path = page_file(tmp_path, "[]\n", defs="defs:\n  thresholds: {soc: {caution_low: 30}}\n")
        assert any(
            "thresholds.soc is already defined in shared defs" in m
            for m in errors(path, load_defs(shared))
        )

    def test_defs_file_errors_have_no_prefix(self, tmp_path: Path) -> None:
        path = write(tmp_path, "conditions:\n  a: {when: [{use: zzz}]}\n", "defs.yaml")
        with pytest.raises(ConfigError) as info:
            load_defs(path)
        assert str(info.value) == f"{path}:2: conditions.a.when[0].use: unknown condition 'zzz'"

    def test_load_config_collects_across_files(self, tmp_path: Path) -> None:
        write(tmp_path, HEADER, "pages/one.yaml")
        write(tmp_path, HEADER, "pages/two.yaml")
        write(tmp_path, HEADER + "bogus: 1\n", "pages/three.yaml")
        with pytest.raises(ConfigError) as info:
            load_config(tmp_path)
        messages = [i.message for i in info.value.issues]
        assert "Extra inputs are not permitted" in messages
        assert any(m.startswith("duplicate page id 'test'") for m in messages)

    def test_named_condition_channels_checked_at_use_site(self, tmp_path: Path) -> None:
        path = page_file(
            tmp_path,
            """\
            - id: g
              type: line
              from: [0, 0]
              to: [1, 0]
              status:
                thresholds: {warning_high: 5000}
                rules: [{level: caution, when: [{use: high}]}]
            """,
            defs="defs:\n  conditions:\n    high: {when: [{channel: rate, gt: 4000}]}\n",
        )
        msgs = errors(path)
        assert any("elements[0].status: channel 'rate' is not bound" in m for m in msgs)
        assert any(
            "when[0].use: condition 'high' uses channel 'rate', which is not bound" in m
            for m in msgs
        )
