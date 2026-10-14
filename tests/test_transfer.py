"""Transfer switch and load panel symbols."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.symbols.transfer import load_panel, transfer_switch
from mfdhome.themes import LCD
from tests.support import ha_state


def ats(state: str | None, params: dict[str, object] | None = None) -> str:
    element = SymbolElement(
        "ats",
        "transfer_switch",
        (100, 100),
        bind={"state": EntityRef("binary_sensor.grid_connected")},
        params=get_symbol("transfer_switch").params(params or {}),
    )
    items = [] if state is None else [ha_state("binary_sensor.grid_connected", state)]
    snap = snapshot_from_ha_states(items)
    return render_element(element, snap, LCD)


def test_blade_position() -> None:
    assert 'x1="116" y1="100" x2="84" y2="100"' in ats("on")  # across to the grid contact
    assert 'x1="116" y1="100" x2="88.8" y2="85.6"' in ats("off")  # swung open: islanded
    assert "<line" not in ats(None)  # unknown: no blade


def test_connected_states_param() -> None:
    assert 'x2="84" y2="100"' in ats("grid", {"connected": ["Grid"]})
    with pytest.raises(ValueError, match="unknown parameter"):
        get_symbol("transfer_switch").params({"closed": ["on"]})


def test_ports_follow_orientation() -> None:
    horizontal = SymbolElement("a", "transfer_switch", (100, 100))
    assert find_port(horizontal, "grid") == Port((72, 100), (-1.0, 0.0))
    assert find_port(horizontal, "load") == Port((128, 100), (1.0, 0.0))
    vertical = SymbolElement("a", "transfer_switch", (100, 100), orientation=Orientation.VERTICAL)
    assert find_port(vertical, "grid") == Port((100, 72), (0.0, -1.0))
    assert find_port(vertical, "load") == Port((100, 128), (0.0, 1.0))


def test_symbols_draw_in_status_colors() -> None:
    assert LCD.color(Status.CAUTION) in transfer_switch(
        0, 0, False, Status.CAUTION, Orientation.HORIZONTAL, LCD
    )
    panel = load_panel(0, 0, Status.NORMAL, LCD)
    assert panel.count("<line") == 1 + 8  # bus + 4 breakers each side
    spec = get_symbol("load_panel")
    assert spec.required == frozenset() and spec.primary == "power"
