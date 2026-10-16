"""The symbol catalog page: every newer symbol, wired through its named ports."""

import re

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.model import StateSnapshot
from mfdhome.render import render_page
from mfdhome.render.panels import MONO
from mfdhome.render.raster import rasterize
from mfdhome.themes import EINK_COLOR, EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import config_page, fixture_state

TABLET = Target("tablet", 1280, 768)
THEMES = [LCD, MIRROR, EINK_MONO, EINK_COLOR]
SYMBOLS = [
    "electric_meter",
    "water_meter",
    "combiner",
    "smart_breaker",
    "ball_valve",
    "globe_valve",
    "water_heater",
    "outlet",
    "sensor",
    "gauge",
]


def scenario(name: str) -> StateSnapshot:
    return fixture_state("catalog") if name == "live" else {}


def test_catalog_places_every_new_symbol() -> None:
    types = {getattr(e, "type", None) for e in config_page("catalog").elements}
    assert set(SYMBOLS) <= types


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("name", ["live", "no_data"])
def test_catalog_snapshot(name: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    assert render_page(config_page("catalog"), scenario(name), theme, TABLET) == svg_snapshot


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_catalog_uses_only_theme_palette(theme: Theme) -> None:
    for name in ("live", "no_data"):
        svg = render_page(config_page("catalog"), scenario(name), theme, TABLET)
        assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_catalog_png_snapshot(png_snapshot: SnapshotAssertion) -> None:
    svg = render_page(config_page("catalog"), scenario("live"), EINK_MONO, Target("e", 800, 480))
    assert rasterize(svg, MONO, EINK_MONO.background) == png_snapshot
