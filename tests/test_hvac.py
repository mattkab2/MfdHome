"""HVAC: air handler, furnace, condenser, damper and thermostat symbols; the page and alerts."""

import re
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.layout import Port
from mfdhome.model import (
    EntityRef,
    Orientation,
    Readout,
    Status,
    SymbolElement,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element, render_page
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import element_box, find_port, port_names
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import FIXTURES, config_page, fixture_state, ha_state
from tests.test_water import House

EXAMPLES = Path(__file__).parent.parent / "examples"
TABLET = Target("tablet", 1280, 768)
GREEN = LCD.color(Status.NORMAL)


def cabinet(type_name: str, action: str, params: dict[str, object] | None = None) -> str:
    element = SymbolElement(
        "c",
        type_name,
        (100, 100),
        bind={"action": EntityRef("climate.main", "hvac_action")},
        params=get_symbol(type_name).params(params or {}),
    )
    snapshot = snapshot_from_ha_states([ha_state("climate.main", "heat", hvac_action=action)])
    return render_element(element, snapshot, LCD)


def filled(svg: str, tag: str) -> bool:
    """Whether the first ``tag`` element (a flame path, fan circle or coil rect) is filled."""
    return f'fill="{GREEN}"' in svg.split(f"<{tag}")[1].split(">")[0]


class TestCabinets:
    def test_furnace_flame_while_heating_fan_while_blowing(self) -> None:
        heating, fan, idle = (cabinet("furnace", a) for a in ("heating", "fan", "idle"))
        assert filled(heating, "path") and filled(heating, "circle")
        assert not filled(fan, "path") and filled(fan, "circle")
        assert not filled(idle, "path") and not filled(idle, "circle")
        assert "<polyline" not in heating  # no coil unless asked for

    def test_coil_while_cooling(self) -> None:
        cooling = cabinet("furnace", "cooling", {"coil": True})
        heating = cabinet("furnace", "heating", {"coil": True})
        coil = '<rect x="78" y="54" width="44" height="16"'  # the coil box, under the top
        assert f'{coil} fill="{GREEN}"' in cooling
        assert f'{coil} fill="none"' in heating
        assert f'fill="{GREEN}"' in cabinet("air_handler", "cooling").split("<rect")[2]

    def test_ports_follow_the_sections(self) -> None:
        def ports(type_name: str, params: dict[str, object]) -> dict[str, Port]:
            element = SymbolElement(
                "c", type_name, (100, 100), params=get_symbol(type_name).params(params)
            )
            names = ("supply", "return", "refrigerant", "gas")
            return {n: find_port(element, n) for n in names if n in port_names(element)}

        up, left, right = (0.0, -1.0), (-1.0, 0.0), (1.0, 0.0)
        assert ports("furnace", {}) == {
            "supply": Port((100, 58), up),
            "return": Port((68, 82), left),
            "gas": Port((132, 120), right),
        }
        assert ports("furnace", {"coil": True}) == {
            "supply": Port((100, 46), up),
            "return": Port((68, 94), left),
            "refrigerant": Port((132, 62), right),
            "gas": Port((132, 132), right),
        }
        assert ports("air_handler", {}) == {
            "supply": Port((100, 64), up),
            "return": Port((68, 112), left),
            "refrigerant": Port((132, 80), right),
        }

    def test_condenser_fan_while_the_compressor_runs(self) -> None:
        assert filled(cabinet("condenser", "cooling"), "circle")
        assert not filled(cabinet("condenser", "heating"), "circle")
        element = SymbolElement("c", "condenser", (100, 100))
        assert find_port(element, "refrigerant") == Port((68, 100), (-1.0, 0.0))

    def test_condenser_power_readout(self) -> None:
        element = SymbolElement(
            "c",
            "condenser",
            (100, 100),
            bind={
                "action": EntityRef("climate.main", "hvac_action"),
                "power": EntityRef("sensor.ac_power"),
            },
            params=get_symbol("condenser").params({}),
            readouts=(Readout("power", format="power"),),
        )
        states = [
            ha_state("climate.main", "cool", hvac_action="cooling"),
            ha_state("sensor.ac_power", "2850", unit_of_measurement="W"),
        ]
        svg = render_element(element, snapshot_from_ha_states(states), LCD)
        assert ">2.9 kW<" in svg and filled(svg, "circle")
        bad = [
            ha_state("climate.main", "cool", hvac_action="cooling"),
            ha_state("sensor.ac_power", "x"),
        ]
        assert ">---<" in render_element(element, snapshot_from_ha_states(bad), LCD)

    def test_params(self) -> None:
        with pytest.raises(ValueError, match="'coil' must be true or false"):
            get_symbol("furnace").params({"coil": "yes"})


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
@pytest.mark.parametrize("name", ["heating", "cooling", "idle", "hot", "no_data"])
def test_hvac_snapshot(name: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    state = {} if name == "no_data" else fixture_state(f"hvac_{name}")
    svg = render_page(config_page("hvac"), state, theme, TABLET)
    assert svg == svg_snapshot
    assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_test_page_matches_the_example() -> None:
    page = "pages/hvac.yaml"
    assert (FIXTURES / "config" / page).read_text() == (EXAMPLES / "config" / page).read_text()


class TestAlerts:
    def test_a_system_behind_its_setpoint_for_half_an_hour(self) -> None:
        house = House()
        hot = {"climate__upstairs": "cool"}
        house.states["climate.upstairs"]["attributes"].update(
            current_temperature=79.0, temperature=74, hvac_action="cooling"
        )
        assert "upstairs_not_cooling" not in house.at(0, **hot)
        assert "upstairs_not_cooling" not in house.at(29, **hot)
        assert "upstairs_not_cooling" in house.at(30, **hot)

    def test_within_three_degrees_is_fine(self) -> None:
        house = House()
        house.states["climate.upstairs"]["attributes"].update(
            current_temperature=76.5, temperature=74
        )
        house.at(0, climate__upstairs="cool")
        assert "upstairs_not_cooling" not in house.at(60, climate__upstairs="cool")

    def test_heating_and_cooling_are_judged_by_mode(self) -> None:
        house = House()
        house.states["climate.main"]["attributes"].update(current_temperature=64.0, temperature=70)
        house.at(0, climate__main="heat")
        assert "main_not_heating" in house.at(30, climate__main="heat")
        cooling = House()
        cooling.states["climate.main"]["attributes"].update(
            current_temperature=64.0, temperature=70
        )
        cooling.at(0, climate__main="cool")  # cold while cooling is fine
        assert "main_not_heating" not in cooling.at(30, climate__main="cool")

    def test_freeze_risk_is_a_warning_and_filters_advisories(self) -> None:
        house = House()
        house.states["climate.main"]["attributes"].update(current_temperature=47.0)
        house.at(0, sensor__furnace_filter_life="5", sensor__upstairs_filter_life="4")
        raised = house.at(15)
        assert {"freeze_risk", "furnace_filter_overdue", "upstairs_filter_overdue"} <= raised
        alerts = house.runtime.config.alerts.by_id()
        assert alerts["freeze_risk"].severity.value == "warning"
        assert alerts["upstairs_filter_overdue"].severity.value == "advisory"
