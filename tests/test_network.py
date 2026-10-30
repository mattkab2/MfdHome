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
from tests.test_water import House

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


class TestGatewayPorts:
    """A router can break out its LAN ports, one line per device on the gateway."""

    def gateway(self, lan: list[int]) -> SymbolElement:
        params = get_symbol("router").params({"lan": lan})
        return SymbolElement("g", "router", (100, 100), params=params)

    def test_ports_down_the_right_edge_in_order(self) -> None:
        gateway = self.gateway([1, 2, 3, 4, 6, 7])
        # six ports 20 apart, 8 in from the top and bottom: 116 tall, 76 wide
        assert element_box(gateway) == Box(62, 42, 138, 158)
        assert find_port(gateway, "lan1") == Port((138, 50), (1.0, 0.0))
        assert find_port(gateway, "lan7") == Port((138, 150), (1.0, 0.0))
        with pytest.raises(ValueError, match="unknown port 'lan5'"):
            find_port(gateway, "lan5")

    def test_each_port_is_drawn_with_its_number(self) -> None:
        svg = render_element(self.gateway([1, 7]), {}, LCD)
        assert svg.count('width="6" height="6"') == 2
        assert ">1<" in svg and ">7<" in svg
        assert box("router") == Box(70, 80, 130, 120)  # without ports, as before

    @pytest.mark.parametrize("lan", [[0], [1, 1], ["1"], [True], list(range(1, 14)), "1,2"])
    def test_lan_is_validated(self, lan: object) -> None:
        with pytest.raises(ValueError, match="'lan' must list up to 12 different port numbers"):
            get_symbol("router").params({"lan": lan})


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


# --- the alerts (example config, quiet example house) ----------------------------------


def test_one_alert_for_a_switch_and_the_ap_behind_it() -> None:
    house = House()
    down = {"sensor__shop_switch_state": "disconnected", "sensor__ap_shop_state": "disconnected"}
    assert house.at(0, **down) == set()
    raised = house.at(5, **down)
    assert "shop_switch_offline" in raised and "ap_shop_offline" not in raised
    lone = House()
    lone.at(0, sensor__ap_shop_state="heartbeat_missed")
    assert "ap_shop_offline" in lone.at(5, sensor__ap_shop_state="heartbeat_missed")


def test_one_alert_when_the_controller_is_unreachable() -> None:
    house = House()
    gone = {
        entity_id.replace(".", "__"): "unavailable"
        for entity_id in house.states
        if entity_id.startswith(("sensor.gateway", "sensor.core_switch", "sensor.shop_switch"))
        or entity_id.startswith("sensor.ap_")
    }
    house.at(0, **gone)
    raised = house.at(10, **gone)
    assert raised == {"gateway_offline"}  # not one per switch and AP


def test_internet_down_waits_two_minutes() -> None:
    house = House()
    assert "wan_down" not in house.at(0, binary_sensor__wan_online="off")
    assert "wan_down" in house.at(2, binary_sensor__wan_online="off")
    alerts = house.runtime.config.alerts.by_id()
    assert alerts["wan_down"].severity.value == "warning"


def test_slow_uplink_is_an_advisory() -> None:
    house = House()
    house.at(0, sensor__shop_switch_port_9_link_speed="1000")  # the fiber at 1G
    assert "uplink_slow" in house.at(5, sensor__shop_switch_port_9_link_speed="1000")
    assert house.runtime.config.alerts.by_id()["uplink_slow"].severity.value == "advisory"


def test_radio_alerts() -> None:
    house = House()
    quiet = {"binary_sensor__meshcore_4d5e6f7a8b_online_yard": "off"}
    assert "repeater_offline" in house.at(0, **quiet)  # its own window already waited
    radio_gone = House()
    lost = {**quiet, "sensor__meshcore_a1b2c3_node_status": "unavailable"}
    assert radio_gone.at(0, **lost) == set()  # the repeater is no news without the radio
    assert radio_gone.at(5, **lost) == {"lora_offline"}
    alerts = house.runtime.config.alerts.by_id()
    assert alerts["repeater_offline"].severity.value == "advisory"
    assert alerts["lora_offline"].severity.value == "caution"
