"""Named state maps in defs: one map shared by many elements (every UniFi device)."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, load_defs, load_page
from mfdhome.model import Status, SymbolElement, snapshot_from_ha_states
from mfdhome.render.alerts import NO_ALERTS
from mfdhome.render.resolve import Resolver
from tests.support import ha_state

DEFS = """\
maps:
  device:
    states: {Connected: normal, disconnected: warning}
    default: caution
"""


def page(tmp_path: Path, status: str, local: str = "") -> SymbolElement:
    (tmp_path / "defs.yaml").write_text(DEFS)
    path = tmp_path / "p.yaml"
    path.write_text(
        textwrap.dedent(
            f"""\
            page: p
            title: P
            canvas: {{width: 100, height: 100}}
            {local}
            elements:
              - id: sw
                type: sensor
                at: [50, 50]
                bind: {{state: sensor.switch_state}}
                status: {status}
            """
        )
    )
    [element] = load_page(path, load_defs(tmp_path / "defs.yaml")).elements
    assert isinstance(element, SymbolElement)
    return element


def status(element: SymbolElement, state: str) -> Status:
    snapshot = snapshot_from_ha_states([ha_state("sensor.switch_state", state)])
    resolved = Resolver(snapshot, NO_ALERTS).element(element)
    assert resolved is not None
    return resolved.status


def test_named_map_with_its_default(tmp_path: Path) -> None:
    sw = page(tmp_path, "{map: device}")
    assert status(sw, "connected") is Status.NORMAL  # states match case-insensitively
    assert status(sw, "disconnected") is Status.WARNING
    assert status(sw, "heartbeat_missed") is Status.CAUTION  # unlisted: the map's default
    assert status(sw, "unavailable") is Status.UNAVAILABLE


def test_default_on_the_element_wins(tmp_path: Path) -> None:
    sw = page(tmp_path, "{map: device, default: normal}")
    assert status(sw, "upgrading") is Status.NORMAL
    assert status(sw, "disconnected") is Status.WARNING


def test_unknown_map(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unknown map 'switch'"):
        page(tmp_path, "{map: switch}")


def test_page_local_maps_and_duplicates(tmp_path: Path) -> None:
    local = "defs: {maps: {link: {states: {up: normal}, default: warning}}}"
    sw = page(tmp_path, "{map: link}", local)
    assert status(sw, "up") is Status.NORMAL and status(sw, "down") is Status.WARNING
    with pytest.raises(ConfigError, match=r"maps\.device"):
        page(tmp_path, "{map: device}", "defs: {maps: {device: {states: {up: normal}}}}")
