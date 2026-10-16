"""HVAC: furnace, damper and thermostat symbols, the HVAC page and its alerts."""

import re
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element, render_page
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import element_box, find_port
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import FIXTURES, config_page, fixture_state, ha_state
from tests.test_water import House

EXAMPLES = Path(__file__).parent.parent / "examples"
TABLET = Target("tablet", 1280, 768)
GREEN = LCD.color(Status.NORMAL)


def furnace(action: str) -> str:
    element = SymbolElement(
        "f",
        "furnace",
        (100, 100),
        bind={"action": EntityRef("climate.main", "hvac_action")},
        params=get_symbol("furnace").params({}),
    )
    snapshot = snapshot_from_ha_states([ha_state("climate.main", "heat", hvac_action=action)])
    return render_element(element, snapshot, LCD)


class TestFurnace:
    def test_flame_while_heating_fan_while_blowing(self) -> None:
        def flame_filled(svg: str) -> bool:
            return f'fill="{GREEN}"' in svg.split("<path")[1].split(">")[0]

        def fan_filled(svg: str) -> bool:
            return f'fill="{GREEN}"' in svg.split("<circle")[1].split(">")[0]

        heating, fan, idle = furnace("heating"), furnace("fan"), furnace("idle")
        assert flame_filled(heating) and fan_filled(heating)
        assert not flame_filled(fan) and fan_filled(fan)
        assert not flame_filled(idle) and not fan_filled(idle)

    def test_ports(self) -> None:
        element = SymbolElement("f", "furnace", (100, 100))
        assert find_port(element, "supply") == Port((100, 52), (0.0, -1.0))
        assert find_port(element, "return") == Port((68, 120), (-1.0, 0.0))
        assert find_port(element, "gas") == Port((132, 134), (1.0, 0.0))


def damper(state: str, params: dict[str, object] | None = None) -> str:
    element = SymbolElement(
        "d",
        "damper",
        (100, 100),
        bind={"state": EntityRef("cover.zone")},
        params=get_symbol("damper").params(params or {}),
    )
    return render_element(element, snapshot_from_ha_states([ha_state("cover.zone", state)]), LCD)


class TestDamper:
    def test_blade_along_the_flow_when_open_across_when_closed(self) -> None:
        assert '<line x1="90" y1="100" x2="110" y2="100"' in damper("open")
        assert '<line x1="100" y1="110" x2="100" y2="90"' in damper("closed")
        assert '<line x1="92.93" y1="107.07" x2="107.07" y2="92.93"' in damper("opening")

    def test_actuated_box_grows(self) -> None:
        plain = SymbolElement("d", "damper", (100, 100), params=get_symbol("damper").params({}))
        actuated = SymbolElement(
            "d", "damper", (100, 100), params=get_symbol("damper").params({"actuated": True})
        )
        assert (element_box(plain).top, element_box(actuated).top) == (88, 72)
        vertical = SymbolElement(
            "d",
            "damper",
            (100, 100),
            orientation=Orientation.VERTICAL,
            params=get_symbol("damper").params({}),
        )
        assert find_port(vertical, "out") == Port((100, 118), (0.0, 1.0))


def thermostat(current: object, setpoint: object, action: str) -> str:
    climate = EntityRef
    element = SymbolElement(
        "t",
        "thermostat",
        (100, 100),
        bind={
            "temperature": climate("climate.main", "current_temperature"),
            "setpoint": climate("climate.main", "temperature"),
            "action": climate("climate.main", "hvac_action"),
        },
        params=get_symbol("thermostat").params({}),
    )
    attributes = {"current_temperature": current, "temperature": setpoint, "hvac_action": action}
    state = ha_state("climate.main", "heat", **{k: v for k, v in attributes.items() if v})
    return render_element(element, snapshot_from_ha_states([state]), LCD)


class TestThermostat:
    def test_temperature_setpoint_and_action(self) -> None:
        svg = thermostat(68.4, 70, "heating")
        assert ">68°<" in svg and ">SET 70°<" in svg
        assert f'fill="{LCD.color(Status.ACTIVE)}">HEAT<' in svg  # running: active color
        assert f'fill="{GREEN}">IDLE<' in thermostat(70.1, 70, "idle")

    def test_no_data(self) -> None:
        svg = thermostat(None, None, "")
        assert ">---<" in svg and "stroke-dasharray" in svg


@pytest.mark.parametrize("theme", [LCD, MIRROR, EINK_MONO, EINK_COLOR], ids=lambda t: t.name)
@pytest.mark.parametrize("name", ["heating", "idle", "cold", "no_data"])
def test_hvac_snapshot(name: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    state = {} if name == "no_data" else fixture_state(f"hvac_{name}")
    svg = render_page(config_page("hvac"), state, theme, TABLET)
    assert svg == svg_snapshot
    assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_test_page_matches_the_example() -> None:
    page = "pages/hvac.yaml"
    assert (FIXTURES / "config" / page).read_text() == (EXAMPLES / "config" / page).read_text()


class TestAlerts:
    def test_a_zone_behind_its_setpoint_for_half_an_hour(self) -> None:
        house = House()
        cold = {"climate__upstairs": "heat"}
        house.states["climate.upstairs"]["attributes"].update(
            current_temperature=63.0, temperature=68, hvac_action="heating"
        )
        assert "upstairs_below_setpoint" not in house.at(0, **cold)
        assert "upstairs_below_setpoint" not in house.at(29, **cold)
        assert "upstairs_below_setpoint" in house.at(30, **cold)

    def test_within_three_degrees_is_fine(self) -> None:
        house = House()
        house.states["climate.upstairs"]["attributes"].update(
            current_temperature=65.5, temperature=68
        )
        house.at(0)
        assert "upstairs_below_setpoint" not in house.at(60)

    def test_freeze_risk_is_a_warning_and_filter_an_advisory(self) -> None:
        house = House()
        house.states["climate.main"]["attributes"].update(current_temperature=47.0)
        house.at(0, sensor__furnace_filter_life="5")
        raised = house.at(15)
        assert {"freeze_risk", "filter_overdue"} <= raised
        alerts = house.runtime.config.alerts.by_id()
        assert alerts["freeze_risk"].severity.value == "warning"
        assert alerts["filter_overdue"].severity.value == "advisory"
