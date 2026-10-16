"""Tank (softener, filter, expansion tank), pump and gas meter symbols."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port, port_names
from mfdhome.themes import LCD
from tests.support import ha_state

UP, DOWN, LEFT, RIGHT = (0.0, -1.0), (0.0, 1.0), (-1.0, 0.0), (1.0, 0.0)


def tank(params: dict[str, object]) -> SymbolElement:
    return SymbolElement("t", "tank", (100, 100), params=get_symbol("tank").params(params))


def test_tank_tag_and_body() -> None:
    svg = render_element(tank({"tag": "SOFT"}), {}, LCD)
    assert '<rect x="80" y="72" width="40" height="56" rx="8"' in svg and ">SOFT<" in svg


@pytest.mark.parametrize(
    ("connections", "ports"),
    [
        ("top", {"in": Port((91, 72), UP), "out": Port((109, 72), UP)}),
        ("sides", {"in": Port((80, 100), LEFT), "out": Port((120, 100), RIGHT)}),
        ("bottom", {"port": Port((100, 128), DOWN)}),
    ],
)
def test_tank_connections(connections: str, ports: dict[str, Port]) -> None:
    element = tank({"connections": connections})
    assert [n for n in port_names(element) if n in ports] == list(ports)
    for name, port in ports.items():
        assert find_port(element, name) == port


def test_tank_params() -> None:
    with pytest.raises(ValueError, match="up to 4 characters"):
        get_symbol("tank").params({"tag": "SOFTENER"})
    with pytest.raises(ValueError, match="'connections' must be one of: top, sides, bottom"):
        get_symbol("tank").params({"connections": "front"})


def pump_svg(state: str, vertical: bool = False) -> str:
    element = SymbolElement(
        "p",
        "pump",
        (100, 100),
        bind={"state": EntityRef("switch.recirc")},
        params=get_symbol("pump").params({}),
        orientation=Orientation.VERTICAL if vertical else Orientation.HORIZONTAL,
    )
    return render_element(element, snapshot_from_ha_states([ha_state("switch.recirc", state)]), LCD)


def test_pump_triangle_points_downstream_and_fills_while_running() -> None:
    running, stopped = pump_svg("on"), pump_svg("off")
    assert '<polygon points="92,92 92,108 108,100" fill="#' in running
    assert '<polygon points="92,92 92,108 108,100" fill="none"' in stopped
    assert '<polygon points="92,92 108,92 100,108"' in pump_svg("on", vertical=True)


def test_gas_meter_is_a_meter_in_ccf() -> None:
    element = SymbolElement("g", "gas_meter", (100, 100), params=get_symbol("gas_meter").params({}))
    assert ">CCF<" in render_element(element, {}, LCD)
    assert get_symbol("gas_meter").channels == ("flow", "total")
