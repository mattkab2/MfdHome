"""Gas water heater symbol."""

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.themes import LCD
from tests.support import ha_state

SPEC = get_symbol("water_heater")


def heater(
    temperature: str | None, heating: str | None, params: dict[str, object] | None = None
) -> str:
    element = SymbolElement(
        "wh",
        "water_heater",
        (100, 100),
        bind={
            "temperature": EntityRef("water_heater.tank", "current_temperature"),
            "heating": EntityRef("binary_sensor.burner"),
        },
        params=SPEC.params(params or {}),
    )
    items = []
    if temperature is not None:
        items.append(ha_state("water_heater.tank", "eco", current_temperature=temperature))
    if heating is not None:
        items.append(ha_state("binary_sensor.burner", heating))
    return render_element(element, snapshot_from_ha_states(items), LCD)


def flame_fill(svg: str) -> str:
    return svg.split("<path ")[1].split('fill="')[1].split('"')[0]


def test_flame_is_solid_while_heating() -> None:
    assert flame_fill(heater("120", "on")) == LCD.color(Status.NORMAL)
    assert flame_fill(heater("120", "off")) == "none"
    assert flame_fill(heater("120", None)) == "none"  # no burner data: outlined
    assert flame_fill(heater("120", "firing", {"heating": ["Firing"]})) == LCD.color(Status.NORMAL)


def test_temperature_is_the_primary_channel() -> None:
    assert LCD.color(Status.NORMAL) in heater("120", "off")
    missing = heater("unavailable", "on")
    assert LCD.color(Status.UNAVAILABLE) in missing and "stroke-dasharray" in missing
    assert SPEC.required == frozenset() and SPEC.numeric == frozenset({"temperature"})


def test_ports_cold_and_hot_on_top_gas_by_the_burner() -> None:
    element = SymbolElement("wh", "water_heater", (100, 100))
    assert find_port(element, "cold") == Port((88, 60), (0.0, -1.0))
    assert find_port(element, "hot") == Port((112, 60), (0.0, -1.0))
    assert find_port(element, "gas") == Port((78, 126), (-1.0, 0.0))
