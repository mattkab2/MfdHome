"""The mfdhome command line."""

import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from aiohttp.test_utils import TestServer
from PIL import Image

from mfdhome.cli import SUPERVISOR_WEBSOCKET, fetch_states, ha_credentials, load_dotenv, main, scrub
from mfdhome.config import load_config
from mfdhome.config.inventory import entity_uses
from tests.fake_ha import TOKEN, FakeHA
from tests.support import CONFIG, FIXTURES, image_colors

type ServerFactory = Callable[[Any], Awaitable[TestServer]]


def test_check_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(CONFIG)]) == 0
    assert "config ok: 8 pages, 26 alerts" in capsys.readouterr().out


def test_check_reports_unknown_entities(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(CONFIG), "--states", str(FIXTURES / "electrical_normal.json")]) == 1
    out = capsys.readouterr().out
    assert "unknown entity sensor.wind_speed: used by alert:high_wind" in out
    assert "sensor.grid_power" not in out


def test_check_passes_when_every_entity_exists(tmp_path: Path) -> None:
    every = sorted(entity_uses(load_config(CONFIG)))
    dump = tmp_path / "states.json"
    dump.write_text(json.dumps([{"entity_id": e, "state": "1"} for e in every]))
    assert main(["check", str(CONFIG), "--states", str(dump)]) == 0


def test_check_config_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "p.yaml").write_text("page: p\ntitle: P\ncanvas: {width: 1}\n")
    assert main(["check", str(tmp_path)]) == 1
    assert "canvas.height: Field required" in capsys.readouterr().err


def test_entity_uses_cover_bindings_rules_alerts_and_groups() -> None:
    uses = entity_uses(load_config(CONFIG))
    grid = uses["sensor.grid_power"]
    assert {
        "electrical:grid",
        "electrical:grid_link",
        "alert:grid_lost",
        "alert:grid_exporting",
        "defs:conditions.grid_lost",
    } <= set(grid)
    assert uses["sensor.pv_p3_power"] == ["electrical:array"]  # inside the solar group
    assert uses["binary_sensor.wan_online"] == ["alert:wan_down", "network:wan"]


def test_scrub() -> None:
    states = [
        {
            "entity_id": "sensor.p",
            "state": "5",
            "attributes": {"unit_of_measurement": "W", "friendly_name": "Garage panel"},
        },
        {
            "entity_id": "climate.main",
            "state": "heat",
            "attributes": {
                "hvac_action": "heating",
                "current_temperature": 68.5,
                "temperature": 70,
                "friendly_name": "Hallway",
            },
        },
        {"entity_id": "person.someone", "state": "home", "attributes": {}},
        {"entity_id": "device_tracker.phone", "state": "home", "attributes": {"latitude": 1}},
    ]
    assert scrub(states) == [
        {"entity_id": "sensor.p", "state": "5", "attributes": {"unit_of_measurement": "W"}},
        {
            "entity_id": "climate.main",
            "state": "heat",
            "attributes": {
                "hvac_action": "heating",
                "current_temperature": 68.5,
                "temperature": 70,
            },
        },
    ]


def test_dotenv_does_not_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nMFD_TEST_A='from file'\nMFD_TEST_B=file\n")
    monkeypatch.setenv("MFD_TEST_B", "from env")
    monkeypatch.delenv("MFD_TEST_A", raising=False)
    load_dotenv(env)
    assert os.environ["MFD_TEST_A"] == "from file"
    assert os.environ["MFD_TEST_B"] == "from env"
    monkeypatch.delenv("MFD_TEST_A")


class TestCredentials:
    """HA_URL and HA_TOKEN when set; in an add-on, the Supervisor's proxy and token."""

    @pytest.fixture(autouse=True)
    def clean(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)  # no .env here
        for name in ("HA_URL", "HA_TOKEN", "SUPERVISOR_TOKEN"):
            monkeypatch.delenv(name, raising=False)

    def test_explicit_url_and_token_win(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HA_URL", "http://ha.local:8123")
        monkeypatch.setenv("HA_TOKEN", "long-lived")
        monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor")
        assert ha_credentials() == ("http://ha.local:8123", "long-lived")

    def test_add_on_uses_the_supervisor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor")
        assert ha_credentials() == (SUPERVISOR_WEBSOCKET, "supervisor")
        assert SUPERVISOR_WEBSOCKET == "ws://supervisor/core/websocket"

    def test_half_set_is_an_error_not_a_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HA_URL", "http://ha.local:8123")
        monkeypatch.setenv("SUPERVISOR_TOKEN", "supervisor")
        with pytest.raises(SystemExit, match="set HA_URL and HA_TOKEN"):
            ha_credentials()

    def test_nothing_set(self) -> None:
        with pytest.raises(SystemExit, match="or run as an add-on"):
            ha_credentials()


async def test_fetch_states(aiohttp_server: ServerFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    server = await aiohttp_server(FakeHA([{"entity_id": "sensor.a", "state": "1"}]).app())
    monkeypatch.setenv("HA_URL", str(server.make_url("")))
    monkeypatch.setenv("HA_TOKEN", TOKEN)
    assert await fetch_states() == [{"entity_id": "sensor.a", "state": "1", "attributes": {}}]


def test_render_panel_display_to_png(tmp_path: Path) -> None:
    out = tmp_path / "frame.png"
    states = str(FIXTURES / "electrical_islanded.json")
    args = ["render", str(CONFIG), "main_floor", "--states", states, "--page", "electrical"]
    assert main([*args, "-o", str(out)]) == 0
    image = Image.open(out)
    assert image.size == (800, 480)
    assert image_colors(image) == {"#000000", "#ffffff"}


def test_render_live_display_to_svg(tmp_path: Path) -> None:
    out = tmp_path / "frame.svg"
    assert main(["render", str(CONFIG), "workshop", "-o", str(out)]) == 0
    assert 'data-page="status"' in out.read_text() and 'id="as-of"' not in out.read_text()


def test_render_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", str(CONFIG), "attic"]) == 1
    assert "no display 'attic'; expected: workshop" in capsys.readouterr().err
    assert main(["render", str(CONFIG), "hallway", "--page", "status"]) == 1
    assert "display 'hallway' cannot show page 'status'" in capsys.readouterr().err
