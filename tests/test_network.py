"""Network symbols: router, switch, access point, host and radio."""

import re

import pytest

from mfdhome.conditions import StateMap
from mfdhome.conditions.model import ChannelRef
from mfdhome.layout import Box, Port
from mfdhome.model import EntityRef, Status, StatusSpec, SymbolElement, snapshot_from_ha_states
from mfdhome.render import render_element
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import element_box, find_port
from mfdhome.themes import EINK_MONO, LCD, Theme
from tests.support import ha_state

TYPES = ["router", "network_switch", "access_point", "host", "radio"]
MAP = {"connected": Status.NORMAL, "disconnected": Status.WARNING}


def device(type_name: str, state: str | None = "connected", theme: Theme = LCD) -> str:
    rules = StateMap(MAP, Status.CAUTION).rules(ChannelRef("state"))
    element = SymbolElement(
        "d",
        type_name,
        (100, 100),
        bind={"state": EntityRef("sensor.device_state")},
        status=StatusSpec(rules),
    )
    items = [] if state is None else [ha_state("sensor.device_state", state)]
    return render_element(element, snapshot_from_ha_states(items), theme)


def widths(svg: str) -> list[float]:
    return [float(w) for w in re.findall(r'stroke-width="([\d.]+)"', svg)]


@pytest.mark.parametrize("type_name", TYPES)
def test_status_colors_and_no_data(type_name: str) -> None:
    assert f'stroke="{LCD.color(Status.NORMAL)}"' in device(type_name)
    assert f'stroke="{LCD.color(Status.WARNING)}"' in device(type_name, "disconnected")
    assert f'stroke="{LCD.color(Status.CAUTION)}"' in device(type_name, "heartbeat_missed")
    gray = device(type_name, None)
    assert f'stroke="{LCD.color(Status.UNAVAILABLE)}"' in gray and "stroke-dasharray" in gray


@pytest.mark.parametrize("type_name", ["router", "network_switch", "access_point", "host"])
def test_only_the_outline_takes_the_status_weight(type_name: str) -> None:
    normal = widths(device(type_name, theme=EINK_MONO))
    warning = widths(device(type_name, "disconnected", theme=EINK_MONO))
    base = EINK_MONO.symbol_stroke_width
    assert warning[0] == base * EINK_MONO.weight(Status.WARNING)  # the outline, drawn first
    assert warning[1:] == normal[1:]  # the marks inside keep their weight


def test_marks_tell_the_types_apart() -> None:
    assert device("router").count("<polyline") == 4  # four routes, each with a chevron
    assert device("network_switch").count("<rect") == 1 + 8  # body and eight ports
    assert device("access_point").count("<path") == 2  # two Wi-Fi arcs
    assert device("host").count("<circle") == 3  # one indicator per bay
    assert "<polygon" in device("radio")  # the antenna


def box(type_name: str) -> Box:
    found = element_box(SymbolElement("d", type_name, (100, 100)))
    assert found is not None
    return found


def test_boxes_reach_over_arcs_and_masts() -> None:
    assert box("router") == Box(70, 80, 130, 120)
    assert box("network_switch") == Box(58, 86, 142, 114)
    assert box("access_point") == Box(78, 76, 122, 108)  # arcs above the body
    assert box("host") == Box(76, 78, 124, 122)
    assert box("radio") == Box(84, 64, 116, 110)  # mast and antenna above the body


@pytest.mark.parametrize("type_name", ["access_point", "radio"])
def test_side_ports_are_level_with_the_body(type_name: str) -> None:
    element = SymbolElement("d", type_name, (100, 100))
    assert find_port(element, "left").point[1] == 100
    assert find_port(element, "right") == Port((box(type_name).right, 100), (1.0, 0.0))


def test_channels() -> None:
    assert get_symbol("router").channels == ("state", "cpu", "memory", "temperature")
    assert "clients" in get_symbol("access_point").numeric
    radio = get_symbol("radio")
    assert radio.channels == ("state", "rssi", "snr", "noise_floor", "hops", "battery")
    assert radio.primary == "state" and "state" not in radio.numeric
    assert not radio.required  # a host or radio can be drawn with nothing bound
