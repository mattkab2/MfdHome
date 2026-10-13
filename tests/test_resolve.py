"""Edge cases for binding resolution."""

import pytest

from mfdhome.model import (
    BatteryElement,
    BreakerElement,
    EntityRef,
    LineElement,
    Status,
    snapshot_from_ha_states,
)
from mfdhome.render.resolve import (
    NO_DATA,
    format_power,
    numeric_value,
    resolve_battery,
    resolve_breaker,
    resolve_line,
)
from mfdhome.symbols import Flow
from tests.support import ha_state

GRID = LineElement("grid", ((0, 0), (10, 0)), power=EntityRef("sensor.grid_power"))
BATTERY = BatteryElement("b", 0, 0, soc=EntityRef("sensor.soc"))
BREAKER = BreakerElement("br", 0, 0, state=EntityRef("switch.main"))


def test_missing_entity_is_unavailable() -> None:
    assert resolve_line(GRID, {}).status is Status.UNAVAILABLE
    assert resolve_battery(BATTERY, {}).status is Status.UNAVAILABLE
    assert resolve_breaker(BREAKER, {}).status is Status.UNAVAILABLE


def test_unavailable_and_unknown_states() -> None:
    for raw in ("unavailable", "unknown", "Unavailable", ""):
        snap = snapshot_from_ha_states([ha_state("sensor.grid_power", raw)])
        resolved = resolve_line(GRID, snap)
        assert resolved.status is Status.UNAVAILABLE
        assert resolved.label == NO_DATA
        assert resolved.flow is None


def test_non_numeric_and_non_finite_values() -> None:
    for raw in ("abc", "nan", "inf"):
        snap = snapshot_from_ha_states([ha_state("sensor.grid_power", raw)])
        assert resolve_line(GRID, snap).status is Status.UNAVAILABLE


def test_missing_attribute_is_unavailable() -> None:
    snap = snapshot_from_ha_states([ha_state("sensor.bat", "ok", level=55)])
    assert numeric_value(EntityRef("sensor.bat", "level"), snap) == 55
    assert numeric_value(EntityRef("sensor.bat", "missing"), snap) is None
    battery = BatteryElement("b", 0, 0, soc=EntityRef("sensor.bat", "missing"))
    assert resolve_battery(battery, snap).status is Status.UNAVAILABLE


def test_boolean_attribute_is_not_numeric() -> None:
    snap = snapshot_from_ha_states([ha_state("sensor.x", "ok", flag=True)])
    assert numeric_value(EntityRef("sensor.x", "flag"), snap) is None


def test_positive_power_flows_forward() -> None:
    snap = snapshot_from_ha_states([ha_state("sensor.grid_power", "1500")])
    resolved = resolve_line(GRID, snap)
    assert (resolved.status, resolved.flow, resolved.label) == (
        Status.ACTIVE,
        Flow.FORWARD,
        "1.5 kW",
    )


def test_negative_grid_power_reverses_flow() -> None:
    snap = snapshot_from_ha_states([ha_state("sensor.grid_power", "-2800")])
    resolved = resolve_line(GRID, snap)
    assert resolved.flow is Flow.REVERSE
    assert resolved.label == "2.8 kW"


def test_power_below_threshold_is_idle() -> None:
    snap = snapshot_from_ha_states([ha_state("sensor.grid_power", "-5")])
    resolved = resolve_line(GRID, snap)
    assert (resolved.status, resolved.flow) == (Status.NORMAL, None)


def test_unbound_line_is_normal() -> None:
    resolved = resolve_line(LineElement("tie", ((0, 0), (1, 0))), {})
    assert resolved.status is Status.NORMAL


def test_soc_thresholds() -> None:
    expected = {
        "80": Status.NORMAL,
        "25": Status.CAUTION,
        "12": Status.CAUTION,
        "8": Status.WARNING,
    }
    for raw, status in expected.items():
        snap = snapshot_from_ha_states([ha_state("sensor.soc", raw)])
        assert resolve_battery(BATTERY, snap).status is status, raw


def test_battery_fill_and_labels() -> None:
    battery = BatteryElement(
        "b", 0, 0, soc=EntityRef("sensor.soc"), power=EntityRef("sensor.bat_power")
    )
    snap = snapshot_from_ha_states([ha_state("sensor.soc", "64.6")])
    resolved = resolve_battery(battery, snap)
    assert resolved.fill_fraction == pytest.approx(0.646)
    assert resolved.labels == ("65%", NO_DATA)


def test_extreme_soc_is_clamped_by_symbol_not_resolver() -> None:
    snap = snapshot_from_ha_states([ha_state("sensor.soc", "140")])
    assert resolve_battery(BATTERY, snap).fill_fraction == 1.4


def test_breaker_states() -> None:
    cases = {
        "on": (Status.NORMAL, True),
        "ON": (Status.NORMAL, True),
        "off": (Status.CAUTION, False),
        "tripped": (Status.CAUTION, False),
        "unavailable": (Status.UNAVAILABLE, None),
    }
    for raw, expected in cases.items():
        snap = snapshot_from_ha_states([ha_state("switch.main", raw)])
        resolved = resolve_breaker(BREAKER, snap)
        assert (resolved.status, resolved.closed) == expected, raw


def test_format_power() -> None:
    assert format_power(None) == NO_DATA
    assert format_power(850) == "850 W"
    assert format_power(-1250) == "-1.2 kW"
    assert format_power(12, "A") == "12 A"
