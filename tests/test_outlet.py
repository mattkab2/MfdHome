"""Outlet symbol: a terminal flag with a tag, and an exterior-wall mark when outdoors."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.symbols.outlet import outlet as draw_outlet
from mfdhome.themes import EINK_COLOR, LCD
from tests.support import ha_state

SPEC = get_symbol("outlet")


def outlet(params: dict[str, object] | None = None, state: str | None = None) -> str:
    element = SymbolElement(
        "o",
        "outlet",
        (100, 100),
        bind={} if state is None else {"state": EntityRef("valve.garden")},
        params=SPEC.params(params or {}),
    )
    items = [] if state is None else [ha_state("valve.garden", state)]
    return render_element(element, snapshot_from_ha_states(items), LCD)


def test_flag_with_tag() -> None:
    svg = outlet({"label": "SINK"})
    assert '<polygon points="86,88 120,88 132,100 120,112 86,112"' in svg  # points away
    assert '<line x1="68" y1="100" x2="86" y2="100"' in svg  # inlet stub
    assert ">SINK<" in svg and svg.count("<line") == 1
    assert ">OUT<" in outlet()  # default tag


def test_outdoor_crosses_the_stub_with_a_wall() -> None:
    svg = outlet({"label": "HB", "outdoor": True})
    assert svg.count("<line") == 3  # stub plus two wall faces
    assert '<line x1="74" y1="92" x2="74" y2="108"' in svg


def test_unbound_is_normal_and_no_data_is_dotted() -> None:
    assert LCD.color(Status.NORMAL) in outlet()
    missing = outlet(state="unavailable")
    assert LCD.color(Status.UNAVAILABLE) in missing and "stroke-dasharray" in missing


def test_inlet_on_the_left() -> None:
    assert find_port(SymbolElement("o", "outlet", (100, 100)), "in") == Port((68, 100), (-1.0, 0.0))


@pytest.mark.parametrize(
    ("params", "error"),
    [
        ({"label": "KITCHEN"}, "1 to 5 characters"),
        ({"outdoor": "yes"}, "'outdoor' must be true or false"),
        ({"indoor": True}, "unknown parameter 'indoor'"),
    ],
)
def test_params_are_validated(params: dict[str, object], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        SPEC.params(params)


def test_tag_is_never_pale_yellow_on_paper() -> None:
    assert 'fill="#ffff00"' not in draw_outlet(0, 0, "HB", False, Status.CAUTION, EINK_COLOR)
