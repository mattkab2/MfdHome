"""Inline fittings: check valve, backflow preventer, pressure reducing valve."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import element_box, find_port
from mfdhome.themes import LCD
from tests.support import ha_state

FITTINGS = ["check_valve", "backflow_preventer", "prv"]
LEFT, RIGHT, UP, DOWN = (-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0)


def element(type_name: str, vertical: bool = False) -> SymbolElement:
    orientation = Orientation.VERTICAL if vertical else Orientation.HORIZONTAL
    return SymbolElement("f", type_name, (100, 100), orientation=orientation)


def test_check_valve_points_downstream_with_a_bar() -> None:
    svg = render_element(element("check_valve"), {}, LCD)
    assert '<polygon points="90,90 90,110 110,100"' in svg  # tip at the outlet side
    assert '<line x1="110" y1="90" x2="110" y2="110"' in svg  # the seat bar


def test_backflow_preventer_is_two_checks_in_a_box() -> None:
    svg = render_element(element("backflow_preventer"), {}, LCD)
    assert svg.count("<polygon") == 2 and svg.count("<rect") == 1


def test_prv_has_a_dome_and_a_taller_box() -> None:
    svg = render_element(element("prv"), {}, LCD)
    assert "<path" in svg and svg.count("<polygon") == 2
    assert element_box(element("prv")).top == 74  # 12 body + 6 stem + 8 dome


@pytest.mark.parametrize(
    ("type_name", "half"), [("check_valve", 16), ("backflow_preventer", 32), ("prv", 20)]
)
def test_ports_on_the_pipe_axis(type_name: str, half: float) -> None:
    assert find_port(element(type_name), "in") == Port((100 - half, 100), LEFT)
    assert find_port(element(type_name), "out") == Port((100 + half, 100), RIGHT)
    vertical = element(type_name, vertical=True)
    assert find_port(vertical, "in") == Port((100, 100 - half), UP)
    assert find_port(vertical, "out") == Port((100, 100 + half), DOWN)


@pytest.mark.parametrize("type_name", FITTINGS)
def test_unbound_is_normal(type_name: str) -> None:
    assert get_symbol(type_name).required == frozenset()
    assert LCD.color(Status.NORMAL) in render_element(element(type_name), {}, LCD)


def test_prv_pressure_reading_and_no_data() -> None:
    prv = SymbolElement("p", "prv", (100, 100), bind={"pressure": EntityRef("sensor.p")})
    missing = render_element(prv, snapshot_from_ha_states([ha_state("sensor.p", "x")]), LCD)
    assert "stroke-dasharray" in missing  # numeric channel with no number: no data
