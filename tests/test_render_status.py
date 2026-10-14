"""Element status, readout formatting and symbol registry behavior."""

import pytest

from mfdhome.conditions import (
    AllOf,
    AnyOf,
    ChannelRef,
    Condition,
    EvalContext,
    Op,
    Rule,
    Thresholds,
    Value,
)
from mfdhome.model import (
    EntityRef,
    FlowSpec,
    LineElement,
    Readout,
    Status,
    StatusSpec,
    SymbolElement,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element
from mfdhome.render.format import NO_DATA, format_value, is_valid_format
from mfdhome.render.status import element_status
from mfdhome.symbols import get_symbol
from mfdhome.themes import LCD
from tests.support import ha_state

GRAY = LCD.color(Status.UNAVAILABLE)


def ctx(*items: dict[str, object], **channels: str) -> EvalContext:
    return EvalContext(
        snapshot_from_ha_states(items), {k: EntityRef(v) for k, v in channels.items()}
    )


class TestElementStatus:
    def test_unbound_primary_is_normal(self) -> None:
        assert element_status(StatusSpec(), ctx(), "power") is Status.NORMAL

    def test_bound_primary_without_data_is_unavailable(self) -> None:
        assert element_status(StatusSpec(), ctx(power="sensor.p"), "power") is Status.UNAVAILABLE

    def test_numeric_primary_with_text_is_unavailable(self) -> None:
        context = ctx(ha_state("sensor.p", "abc"), power="sensor.p")
        assert element_status(StatusSpec(), context, "power", numeric=True) is Status.UNAVAILABLE
        assert element_status(StatusSpec(), context, "power", numeric=False) is Status.NORMAL

    def test_explicit_rule_beats_no_data(self) -> None:
        rule = Rule(
            Status.WARNING,
            AnyOf((AllOf((Condition(ChannelRef("state"), Op.UNAVAILABLE, True),)),)),
        )
        context = ctx(state="switch.main")
        assert element_status(StatusSpec((rule,)), context, "state") is Status.WARNING

    def test_thresholds(self) -> None:
        spec = StatusSpec(Thresholds(warning_low=10, caution_low=25).rules(ChannelRef("level")))
        for raw, expected in [("80", Status.NORMAL), ("20", Status.CAUTION), ("5", Status.WARNING)]:
            context = ctx(ha_state("sensor.soc", raw), level="sensor.soc")
            assert element_status(spec, context, "level", numeric=True) is expected, raw


class TestFormat:
    @pytest.mark.parametrize(
        ("value", "fmt", "unit", "absolute", "expected"),
        [
            (Value(None), "power", None, False, NO_DATA),
            (Value("850", "W"), "power", None, False, "850 W"),
            (Value("-1250", "W"), "power", None, False, "-1.2 kW"),
            (Value("-1250", "W"), "power", None, True, "1.2 kW"),
            (Value("1.5", "kW"), "power", None, False, "1.5 kW"),
            (Value("0.4", "kW"), "power", None, False, "400 W"),
            (Value("12"), "power", "A", False, "12 A"),
            (Value("64.6", "%"), "percent", None, False, "65%"),
            (Value("21.456", "°C"), "number", None, False, "21.46 °C"),
            (Value("3"), "number", None, False, "3"),
            (Value("21.456"), "{:.1f} °C", None, False, "21.5 °C"),
            (Value("abc"), "number", None, False, NO_DATA),
            (Value("heating"), "raw", None, False, "heating"),
        ],
    )
    def test_format_value(
        self, value: Value, fmt: str, unit: str | None, absolute: bool, expected: str
    ) -> None:
        assert format_value(value, fmt, unit, absolute) == expected

    def test_is_valid_format(self) -> None:
        assert is_valid_format("power")
        assert is_valid_format("{:.1f} V")
        assert not is_valid_format("bogus")
        assert not is_valid_format("{:d}")
        assert not is_valid_format("{0[x]}")


class TestRegistry:
    def test_battery_spec(self) -> None:
        spec = get_symbol("battery")
        assert spec.channels == ("level", "power")
        assert spec.required == {"level"}
        assert spec.primary == "level"

    def test_breaker_params(self) -> None:
        spec = get_symbol("breaker")
        assert spec.params({}) == {"closed": frozenset({"on", "closed"})}
        assert spec.params({"closed": ["ON", "Engaged"]}) == {"closed": {"on", "engaged"}}
        with pytest.raises(ValueError, match="unknown parameter 'x'"):
            spec.params({"x": 1})
        with pytest.raises(ValueError, match="list"):
            spec.params({"closed": "on"})

    def test_battery_rejects_params(self) -> None:
        with pytest.raises(ValueError, match="unknown parameter"):
            get_symbol("battery").params({"x": 1})

    def test_unknown_type(self) -> None:
        with pytest.raises(KeyError):
            get_symbol("teapot")


class TestElements:
    def test_breaker_custom_closed_states(self) -> None:
        element = SymbolElement(
            "br",
            "breaker",
            (0, 0),
            bind={"state": EntityRef("switch.main")},
            params=get_symbol("breaker").params({"closed": ["engaged"]}),
        )
        state = snapshot_from_ha_states([ha_state("switch.main", "engaged")])
        assert 'x2="20" y2="0"' in render_element(element, state, LCD)

    def test_line_flow_on_caution_line_keeps_caution_color(self) -> None:
        rule = Rule(
            Status.CAUTION,
            AnyOf((AllOf((Condition(ChannelRef("power"), Op.GT, 5000),)),)),
        )
        element = LineElement(
            "l",
            ((0, 0), (100, 0)),
            bind={"power": EntityRef("sensor.p")},
            status=StatusSpec((rule,)),
            flow=FlowSpec(),
        )
        state = snapshot_from_ha_states([ha_state("sensor.p", "6000")])
        svg = render_element(element, state, LCD)
        assert "<polygon" in svg
        assert LCD.color(Status.CAUTION) in svg
        assert LCD.color(Status.ACTIVE) not in svg

    def test_readout_on_unbound_channel_shows_no_data(self) -> None:
        element = LineElement("l", ((0, 0), (100, 0)), readouts=(Readout("power"),))
        assert f">{NO_DATA}<" in render_element(element, {}, LCD)

    def test_readouts_stack_at_shared_anchor(self) -> None:
        element = SymbolElement(
            "b",
            "battery",
            (0, 0),
            bind={"level": EntityRef("sensor.soc")},
            readouts=(Readout("level", "percent"), Readout("level", "number")),
        )
        state = snapshot_from_ha_states([ha_state("sensor.soc", "50")])
        svg = render_element(element, state, LCD)
        assert 'y="66"' in svg
        assert 'y="86.8"' in svg
