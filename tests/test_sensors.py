"""Point sensors: the on/off sensor diamond and the numeric gauge."""

import pytest

from mfdhome.model import EntityRef, Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.themes import EINK_COLOR, LCD
from tests.support import ha_state

FILLED = f'fill="{LCD.color(Status.NORMAL)}"'
DIAMOND_FILLED = f'86,100" {FILLED}'  # the diamond's own fill, after its points


def render(type_name: str, channel: str, state: str | None, params: dict[str, object]) -> str:
    element = SymbolElement(
        "s",
        type_name,
        (100, 100),
        bind={channel: EntityRef("sensor.x")},
        params=get_symbol(type_name).params(params),
    )
    items = [] if state is None else [ha_state("sensor.x", state, unit_of_measurement="°F")]
    return render_element(element, snapshot_from_ha_states(items), LCD)


class TestSensor:
    def test_diamond_filled_while_tripped(self) -> None:
        dry = render("sensor", "state", "off", {"code": "W"})
        wet = render("sensor", "state", "on", {"code": "W"})
        assert '<polygon points="100,86 114,100 100,114 86,100" fill="none"' in dry
        assert f'<polygon points="100,86 114,100 100,114 86,100" {FILLED}' in wet
        assert ">W<" in dry and f'fill="{LCD.background}">W<' in wet  # code reads on the fill

    def test_active_states_param(self) -> None:
        params = {"code": "M", "active": ["Detected"]}
        assert DIAMOND_FILLED in render("sensor", "state", "detected", params)
        assert DIAMOND_FILLED not in render("sensor", "state", "on", params)

    def test_no_data_is_dotted_and_never_tripped(self) -> None:
        svg = render("sensor", "state", "unavailable", {"code": "CO"})
        assert LCD.color(Status.UNAVAILABLE) in svg and "stroke-dasharray" in svg
        assert DIAMOND_FILLED not in svg

    def test_params(self) -> None:
        with pytest.raises(ValueError, match="up to 3 characters"):
            get_symbol("sensor").params({"code": "SMOKE"})
        assert get_symbol("sensor").params({}) == {"code": "", "active": frozenset({"on"})}


class TestGauge:
    def test_reading_inside_the_box(self) -> None:
        svg = render("gauge", "value", "68.4", {"format": "{:.0f} °F"})
        assert ">68 °F<" in svg and '<rect x="68" y="88" width="64" height="24"' in svg

    def test_no_data(self) -> None:
        svg = render("gauge", "value", "unavailable", {})
        assert ">---<" in svg and "stroke-dasharray" in svg

    def test_format_and_unit_params(self) -> None:
        assert ">55 kPa<" in render("gauge", "value", "55", {"unit": "kPa"})
        with pytest.raises(ValueError, match="unknown format 'fancy'"):
            get_symbol("gauge").params({"format": "fancy"})


def test_caution_text_is_never_pale_yellow_on_paper() -> None:
    from mfdhome.symbols.sensor import gauge, sensor

    for svg in (
        sensor(0, 0, "W", False, Status.CAUTION, EINK_COLOR),
        sensor(0, 0, "W", True, Status.CAUTION, EINK_COLOR),
        gauge(0, 0, "40 psi", Status.CAUTION, EINK_COLOR),
    ):
        assert "<text" in svg and 'fill="#ffff00">' not in svg  # a text fill ends the tag
