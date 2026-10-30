"""Outlet symbol: a terminal flag with a tag, its flat back flush with the pipe.

Outdoors the back edge is doubled (the wall); a sink takes two inlets; a flag
can point left, fed from the right.
"""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port, port_names
from mfdhome.symbols.outlet import outlet as draw_outlet
from mfdhome.themes import EINK_COLOR, LCD
from tests.support import ha_state

SPEC = get_symbol("outlet")
LEFT = (-1.0, 0.0)


def element(params: dict[str, object] | None = None, bound: bool = False) -> SymbolElement:
    return SymbolElement(
        "o",
        "outlet",
        (100, 100),
        bind={"state": EntityRef("valve.garden")} if bound else {},
        params=SPEC.params(params or {}),
    )


def outlet(params: dict[str, object] | None = None, state: str | None = None) -> str:
    items = [] if state is None else [ha_state("valve.garden", state)]
    snapshot = snapshot_from_ha_states(items)
    return render_element(element(params, bound=state is not None), snapshot, LCD)


def test_flag_with_tag_and_no_stub() -> None:
    svg = outlet({"label": "SINK"})
    assert '<polygon points="72,86 116,86 128,100 116,114 72,114"' in svg  # points away
    assert ">SINK<" in svg and "<line" not in svg
    assert ">OUT<" in outlet()  # default tag


def test_outdoor_doubles_only_the_back_edge() -> None:
    svg = outlet({"label": "HB", "outdoor": True})
    assert svg.count("<polygon") == 1
    assert '<line x1="75.5" y1="86" x2="75.5" y2="114"' in svg  # just inside the back


def test_one_inlet_in_the_middle_of_the_back() -> None:
    assert port_names(element())[0] == "in"
    assert find_port(element(), "in") == Port((72, 100), LEFT)  # flush with the pipe


def test_two_inlets_cold_above_hot_below() -> None:
    sink = element({"label": "SINK", "inlets": 2})
    assert port_names(sink)[:2] == ["cold", "hot"]
    assert find_port(sink, "cold") == Port((72, 93), LEFT)
    assert find_port(sink, "hot") == Port((72, 107), LEFT)
    with pytest.raises(ValueError, match="unknown port 'in'"):
        find_port(sink, "in")


def test_unbound_is_normal_and_no_data_is_dotted() -> None:
    assert LCD.color(Status.NORMAL) in outlet()
    missing = outlet(state="unavailable")
    assert LCD.color(Status.UNAVAILABLE) in missing and "stroke-dasharray" in missing


def test_facing_left_mirrors_the_flag_and_its_inlets() -> None:
    svg = outlet({"label": "AC", "outdoor": True, "facing": "left"})
    assert '<polygon points="128,86 84,86 72,100 84,114 128,114"' in svg  # points left
    assert '<line x1="124.5" y1="86" x2="124.5" y2="114"' in svg  # the wall, on the right
    assert find_port(element({"facing": "left"}), "in") == Port((128, 100), (1.0, 0.0))
    sink = element({"label": "SINK", "inlets": 2, "facing": "left"})
    assert find_port(sink, "cold") == Port((128, 93), (1.0, 0.0))


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({"label": "KITCHEN"}, "1 to 5 characters"),
        ({"outdoor": "yes"}, "'outdoor' must be true or false"),
        ({"inlets": 3}, "'inlets' must be 1 or 2"),
        ({"inlets": True}, "'inlets' must be 1 or 2"),
        ({"indoor": True}, "unknown parameter 'indoor'"),
        ({"facing": "up"}, "'facing' must be right"),
    ],
)
def test_params_are_validated(params: dict[str, object], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        SPEC.params(params)


def test_tag_is_never_pale_yellow_on_paper() -> None:
    assert 'fill="#ffff00"' not in draw_outlet(0, 0, "HB", False, Status.CAUTION, EINK_COLOR)
