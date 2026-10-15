"""Combiner symbol: branch inputs set by a param."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import Orientation, Status, SymbolElement
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port, port_names
from mfdhome.themes import LCD

SPEC = get_symbol("combiner")


def combiner(inputs: int | None = None, vertical: bool = False) -> SymbolElement:
    return SymbolElement(
        "c",
        "combiner",
        (100, 100),
        params=SPEC.params({} if inputs is None else {"inputs": inputs}),
        orientation=Orientation.VERTICAL if vertical else Orientation.HORIZONTAL,
    )


def test_ports_follow_input_count() -> None:
    assert port_names(combiner())[:3] == ["in1", "in2", "out"]
    assert port_names(combiner(4))[:5] == ["in1", "in2", "in3", "in4", "out"]
    with pytest.raises(ValueError, match="unknown port 'in3'"):
        find_port(combiner(2), "in3")


def test_inputs_are_evenly_spaced_on_the_input_side() -> None:
    three = combiner(3)
    assert [find_port(three, f"in{i}").point for i in (1, 2, 3)] == [
        (70, pytest.approx(73.33, abs=0.01)),
        (70, 100),
        (70, pytest.approx(126.67, abs=0.01)),
    ]
    assert find_port(three, "in1").direction == (-1.0, 0.0)
    assert find_port(three, "out") == Port((130, 100), (1.0, 0.0))


def test_vertical_puts_inputs_on_top() -> None:
    two = combiner(2, vertical=True)
    assert find_port(two, "in1") == Port((120, 70), (0.0, -1.0))
    assert find_port(two, "in2") == Port((80, 70), (0.0, -1.0))
    assert find_port(two, "out") == Port((100, 130), (0.0, 1.0))


def test_draws_one_breaker_mark_per_input() -> None:
    for inputs in (1, 2, 4):
        svg = render_element(combiner(inputs), {}, LCD)
        assert svg.count("<rect") == 1 + inputs  # the box and one mark per branch
        assert LCD.color(Status.NORMAL) in svg


@pytest.mark.parametrize("bad", [0, 5, 2.5, True, "3"])
def test_inputs_param_is_validated(bad: object) -> None:
    with pytest.raises(ValueError, match="whole number from 1 to 4"):
        SPEC.params({"inputs": bad})
