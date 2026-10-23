"""Network symbols: router, switch, access point, host and radio."""

import re
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.conditions import StateMap
from mfdhome.conditions.model import ChannelRef
from mfdhome.layout import Box, Port
from mfdhome.model import (
    EntityRef,
    StateSnapshot,
    Status,
    StatusSpec,
    SymbolElement,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element, render_page
from mfdhome.render.alerts import NO_ALERTS
from mfdhome.render.panels import MONO
from mfdhome.render.raster import rasterize
from mfdhome.render.resolve import Resolver
from mfdhome.symbols import get_symbol
from mfdhome.symbols.geometry import element_box, find_port
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import FIXTURES, config_page, fixture_state, ha_state

EXAMPLES = Path(__file__).parent.parent / "examples"

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


# --- the page -------------------------------------------------------------------------

TABLET = Target("tablet", 1280, 768)
PAGE_STATES = ["normal", "degraded", "unreachable", "no_data"]


def page_state(name: str) -> StateSnapshot:
    return {} if name == "no_data" else fixture_state(f"network_{name}")


def resolved(name: str) -> dict[str, Status]:
    resolver = Resolver(page_state(name), NO_ALERTS)
    out = {}
    for element in config_page("network").elements:
        result = resolver.element(element)
        if result is not None:
            out[element.id] = result.status
    return out


@pytest.mark.parametrize("theme", [LCD, MIRROR, EINK_MONO, EINK_COLOR], ids=lambda t: t.name)
@pytest.mark.parametrize("name", PAGE_STATES)
def test_network_snapshot(name: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    svg = render_page(config_page("network"), page_state(name), theme, TABLET)
    assert svg == svg_snapshot
    assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_network_png_snapshot(png_snapshot: SnapshotAssertion) -> None:
    svg = render_page(
        config_page("network"), page_state("degraded"), EINK_MONO, Target("e", 800, 480)
    )
    assert rasterize(svg, MONO, EINK_MONO.background) == png_snapshot


def test_test_page_matches_the_example() -> None:
    page = "pages/network.yaml"
    assert (FIXTURES / "config" / page).read_text() == (EXAMPLES / "config" / page).read_text()


def test_all_quiet() -> None:
    statuses = resolved("normal")
    assert set(statuses.values()) == {Status.NORMAL}


def test_a_switch_down_takes_its_link_and_ap() -> None:
    statuses = resolved("degraded")
    for element_id in ("shop_switch", "to_shop", "to_ap_shop", "ap_shop"):
        assert statuses[element_id] is Status.CAUTION, element_id
    assert statuses["to_core"] is Status.CAUTION  # came up at 100 Mbit/s
    assert statuses["core_switch"] is Status.NORMAL and statuses["ap_house"] is Status.NORMAL


def test_the_mesh_link_shows_the_repeater() -> None:
    assert resolved("degraded")["mesh"] is Status.CAUTION  # quiet past its window
    assert resolved("degraded")["usb"] is Status.NORMAL  # the companion is fine
    assert resolved("no_data")["mesh"] is Status.UNAVAILABLE  # not polled yet


def test_controller_unreachable_grays_unifi_only() -> None:
    statuses = resolved("unreachable")
    for element_id in ("gateway", "to_lan", "core_switch", "shop_switch", "ap_house", "ap_shop"):
        assert statuses[element_id] is Status.UNAVAILABLE, element_id
    assert statuses["wan"] is Status.WARNING
    assert statuses["host"] is Status.NORMAL and statuses["mesh"] is Status.NORMAL
