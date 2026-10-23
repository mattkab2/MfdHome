"""A line's ``state`` channel: a link's own state, for lines with nothing to measure."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, Defs, load_page
from mfdhome.model import LineElement, Status, snapshot_from_ha_states
from mfdhome.render.alerts import NO_ALERTS
from mfdhome.render.resolve import Resolver
from tests.support import ha_state


def link(tmp_path: Path, bind: str, extra: str = "") -> LineElement:
    page = tmp_path / "p.yaml"
    page.write_text(
        textwrap.dedent(
            f"""\
            page: p
            title: P
            canvas: {{width: 100, height: 100}}
            elements:
              - id: rf
                type: line
                from: [0, 0]
                to: [10, 0]
                bind: {bind}
                status: {{map: {{"on": normal, "off": caution}}}}
            """
        )
        + textwrap.indent(extra, " " * 4)
    )
    [line] = load_page(page, Defs()).elements
    assert isinstance(line, LineElement)
    return line


def status(line: LineElement, *states: dict[str, object]) -> Status:
    resolved = Resolver(snapshot_from_ha_states(list(states)), NO_ALERTS).element(line)
    assert resolved is not None
    return resolved.status


def test_state_alone_is_the_primary(tmp_path: Path) -> None:
    rf = link(tmp_path, "{state: binary_sensor.repeater_online}")
    assert status(rf, ha_state("binary_sensor.repeater_online", "on")) is Status.NORMAL
    assert status(rf, ha_state("binary_sensor.repeater_online", "off")) is Status.CAUTION
    # Not heard from yet: no data, so the link is drawn gray and dotted.
    assert status(rf, ha_state("binary_sensor.repeater_online", "unknown")) is Status.UNAVAILABLE
    assert status(rf) is Status.UNAVAILABLE


def test_rate_stays_primary_when_both_are_bound(tmp_path: Path) -> None:
    rf = link(tmp_path, "{rate: sensor.port_rx, state: sensor.switch_state}")
    # The map reads the rate (the primary) unless 'from' says otherwise...
    assert status(rf, ha_state("sensor.port_rx", "on")) is Status.NORMAL
    assert status(rf, ha_state("sensor.switch_state", "on")) is Status.UNAVAILABLE


def test_map_from_state_beside_a_rate(tmp_path: Path) -> None:
    page = tmp_path / "p.yaml"
    page.write_text(
        textwrap.dedent(
            """\
            page: p
            title: P
            canvas: {width: 100, height: 100}
            elements:
              - id: uplink
                type: line
                from: [0, 0]
                to: [10, 0]
                bind: {rate: sensor.port_rx, state: sensor.switch_state}
                status: {from: state, map: {connected: normal}, default: warning}
                flow: true
            """
        )
    )
    [uplink] = load_page(page, Defs()).elements
    assert isinstance(uplink, LineElement)
    rx = ha_state("sensor.port_rx", "120")
    assert status(uplink, rx, ha_state("sensor.switch_state", "connected")) is Status.NORMAL
    assert status(uplink, rx, ha_state("sensor.switch_state", "disconnected")) is Status.WARNING


def test_flow_from_a_rate_needs_the_rate(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="channel 'rate' is not bound"):
        link(tmp_path, "{state: binary_sensor.repeater_online}", "flow: true\n")
