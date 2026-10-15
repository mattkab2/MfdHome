"""Smart breaker: a breaker with a remote-operation actuator."""

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.themes import LCD
from tests.support import ha_state


def smart(state: str | None, type_name: str = "smart_breaker") -> str:
    element = SymbolElement(
        "sc1",
        type_name,
        (100, 100),
        bind={"state": EntityRef("switch.smart_circuit_1")},
        params=get_symbol(type_name).params({}),
    )
    items = [] if state is None else [ha_state("switch.smart_circuit_1", state)]
    return render_element(element, snapshot_from_ha_states(items), LCD)


def test_actuator_sets_it_apart_from_a_breaker() -> None:
    actuator = '<rect x="94" y="108" width="12" height="8"'
    assert actuator in smart("on") and actuator not in smart("on", "breaker")
    # The actuator stays whatever the contact does, including with no data.
    assert actuator in smart("off") and actuator in smart(None)


def test_contact_follows_state() -> None:
    assert 'x1="80" y1="100" x2="120" y2="100"' in smart("on")  # closed across
    assert 'x1="80" y1="100" x2="116" y2="76"' in smart("off")  # swung open
    no_data = smart("unavailable")
    assert LCD.color(Status.UNAVAILABLE) in no_data and "stroke-dasharray" in no_data


def test_ports_and_channels_match_the_breaker() -> None:
    element = SymbolElement("sc", "smart_breaker", (100, 100), orientation=Orientation.VERTICAL)
    assert find_port(element, "in") == Port((100, 80), (0.0, -1.0))
    assert find_port(element, "out") == Port((100, 120), (0.0, 1.0))
    spec = get_symbol("smart_breaker")
    assert spec.channels == ("state", "power") and spec.required == frozenset({"state"})
    assert spec.params({"closed": ["Enabled"]}) == {"closed": frozenset({"enabled"})}
