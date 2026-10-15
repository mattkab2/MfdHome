"""Ball and globe valve symbols."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.themes import LCD
from tests.support import ha_state

VALVES = ["ball_valve", "globe_valve"]
FILL = f'fill="{LCD.color(Status.NORMAL)}"'


def valve(type_name: str, state: str | None, params: dict[str, object] | None = None) -> str:
    element = SymbolElement(
        "v",
        type_name,
        (100, 100),
        bind={"state": EntityRef("valve.main")},
        params=get_symbol(type_name).params(params or {}),
    )
    items = [] if state is None else [ha_state("valve.main", state)]
    return render_element(element, snapshot_from_ha_states(items), LCD)


def filled_triangles(svg: str) -> int:
    return sum(1 for part in svg.split("<polygon")[1:] if part.split(">")[0].count(FILL))


@pytest.mark.parametrize("type_name", VALVES)
@pytest.mark.parametrize(
    ("state", "filled"),
    [("open", 0), ("on", 0), ("closed", 2), ("off", 2), ("opening", 1), ("closing", 1)],
)
def test_fill_shows_position(type_name: str, state: str, filled: int) -> None:
    assert filled_triangles(valve(type_name, state)) == filled


@pytest.mark.parametrize("type_name", VALVES)
def test_no_data_is_outlined_and_dotted(type_name: str) -> None:
    svg = valve(type_name, "unavailable")
    assert filled_triangles(svg) == 0 and LCD.color(Status.UNAVAILABLE) in svg
    assert "stroke-dasharray" in svg


def test_ball_and_globe_bodies_differ() -> None:
    ball, globe = valve("ball_valve", "closed"), valve("globe_valve", "closed")
    assert f'<circle cx="100" cy="100" r="5" fill="{LCD.background}"' in ball
    # The globe's solid dot is ringed in the background color, visible on a filled valve.
    assert f'r="4" {FILL} stroke="{LCD.background}"' in globe


def test_states_params() -> None:
    assert filled_triangles(valve("ball_valve", "Flowing", {"open": ["flowing"]})) == 0
    assert filled_triangles(valve("ball_valve", "open", {"open": ["flowing"]})) == 2
    assert filled_triangles(valve("ball_valve", "busy", {"moving": ["busy"]})) == 1
    with pytest.raises(ValueError, match="unknown parameter 'closed'"):
        get_symbol("ball_valve").params({"closed": ["off"]})
    with pytest.raises(ValueError, match="'open' must be a list"):
        get_symbol("globe_valve").params({"open": "open"})


@pytest.mark.parametrize("type_name", VALVES)
def test_ports_follow_orientation(type_name: str) -> None:
    horizontal = SymbolElement("v", type_name, (100, 100))
    assert find_port(horizontal, "in") == Port((80, 100), (-1.0, 0.0))
    assert find_port(horizontal, "out") == Port((120, 100), (1.0, 0.0))
    vertical = SymbolElement("v", type_name, (100, 100), orientation=Orientation.VERTICAL)
    assert find_port(vertical, "in") == Port((100, 80), (0.0, -1.0))
    assert find_port(vertical, "out") == Port((100, 120), (0.0, 1.0))
