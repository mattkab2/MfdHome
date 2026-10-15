"""Electric and water meter symbols."""

import pytest

from mfdhome.layout import Port
from mfdhome.model import EntityRef, Orientation, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import find_port
from mfdhome.symbols.meter import meter as draw_meter
from mfdhome.themes import EINK_COLOR, LCD
from tests.support import ha_state


def meter(
    type_name: str, channel: str, state: str | None, params: dict[str, object] | None = None
) -> str:
    element = SymbolElement(
        "m",
        type_name,
        (100, 100),
        bind={channel: EntityRef("sensor.meter")},
        params=get_symbol(type_name).params(params or {}),
    )
    items = [] if state is None else [ha_state("sensor.meter", state)]
    return render_element(element, snapshot_from_ha_states(items), LCD)


@pytest.mark.parametrize(
    ("type_name", "channel", "label"),
    [("electric_meter", "power", "kWh"), ("water_meter", "flow", "GAL")],
)
def test_meter_draws_circle_and_unit(type_name: str, channel: str, label: str) -> None:
    svg = meter(type_name, channel, "1200")
    assert '<circle cx="100" cy="100" r="20"' in svg and f">{label}<" in svg
    assert LCD.color(Status.NORMAL) in svg
    # Export (negative) is still a reading, not missing data.
    assert LCD.color(Status.NORMAL) in meter(type_name, channel, "-800")
    unavailable = meter(type_name, channel, "unavailable")
    assert LCD.color(Status.UNAVAILABLE) in unavailable and "stroke-dasharray" in unavailable


def test_label_param() -> None:
    assert ">m³<" in meter("water_meter", "flow", "3", {"label": "m³"})
    spec = get_symbol("electric_meter")
    with pytest.raises(ValueError, match="1 to 5 characters"):
        spec.params({"label": "KILOWATT"})
    with pytest.raises(ValueError, match="unknown parameter"):
        spec.params({"unit": "kWh"})


def test_meters_need_no_binding() -> None:
    for type_name in ("electric_meter", "water_meter"):
        assert get_symbol(type_name).required == frozenset()
    static = SymbolElement(
        "m", "electric_meter", (0, 0), params=get_symbol("electric_meter").params({})
    )
    assert LCD.color(Status.NORMAL) in render_element(static, {}, LCD)


def test_ports_follow_orientation() -> None:
    horizontal = SymbolElement("m", "water_meter", (100, 100))
    assert find_port(horizontal, "in") == Port((80, 100), (-1.0, 0.0))
    assert find_port(horizontal, "out") == Port((120, 100), (1.0, 0.0))
    vertical = SymbolElement("m", "water_meter", (100, 100), orientation=Orientation.VERTICAL)
    assert find_port(vertical, "in") == Port((100, 80), (0.0, -1.0))
    assert find_port(vertical, "out") == Port((100, 120), (0.0, 1.0))


def test_label_is_never_pale_yellow_on_paper() -> None:
    svg = draw_meter(0, 0, "kWh", Status.CAUTION, EINK_COLOR)
    assert 'stroke="#ffff00"' in svg and "<text" in svg
    assert 'fill="#ffff00"' not in svg
