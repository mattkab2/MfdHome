"""Hose bib and faucet symbols."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.themes import LCD
from tests.support import ha_state

TAPS = ["hose_bib", "faucet"]
DROP = 'stroke="none"'  # the drop is the only unstroked shape


def tap(type_name: str, state: str | None, bound: bool = True) -> str:
    element = SymbolElement(
        "t",
        type_name,
        (100, 100),
        bind={"state": EntityRef("valve.garden")} if bound else {},
        params=get_symbol(type_name).params({}),
    )
    items = [] if state is None else [ha_state("valve.garden", state)]
    return render_element(element, snapshot_from_ha_states(items), LCD)


@pytest.mark.parametrize("type_name", TAPS)
def test_drop_shows_only_while_open(type_name: str) -> None:
    assert DROP in tap(type_name, "open") and DROP in tap(type_name, "on")
    assert DROP not in tap(type_name, "closed")
    assert DROP not in tap(type_name, None, bound=False)  # a plain tap, no data source


@pytest.mark.parametrize("type_name", TAPS)
def test_unbound_is_normal_and_no_data_is_dotted(type_name: str) -> None:
    assert LCD.color(Status.NORMAL) in tap(type_name, None, bound=False)
    missing = tap(type_name, "unavailable")
    assert LCD.color(Status.UNAVAILABLE) in missing and "stroke-dasharray" in missing
    assert DROP not in missing


def test_inlets() -> None:
    assert find_port(SymbolElement("t", "hose_bib", (100, 100)), "in") == Port(
        (80, 100), (-1.0, 0.0)
    )
    assert find_port(SymbolElement("t", "faucet", (100, 100)), "in") == Port((100, 120), (0.0, 1.0))


def test_shapes_differ() -> None:
    assert tap("hose_bib", "closed") != tap("faucet", "closed")
    assert get_symbol("hose_bib").params({"open": ["Running"]}) == {"open": frozenset({"running"})}
