"""Snapshot and purity tests for the Electrical page."""

import re

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.model import Status
from mfdhome.render import render_page
from mfdhome.themes import EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import config_page, fixture_state

TABLET = Target("tablet", 1280, 768)
FIXTURES = [
    "electrical_normal",
    "electrical_export",
    "electrical_unavailable",
    "electrical_islanded",
]
THEMES = [LCD, MIRROR, EINK_MONO]


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_electrical_snapshot(fixture: str, theme: Theme, svg_snapshot: SnapshotAssertion) -> None:
    svg = render_page(config_page("electrical"), fixture_state(fixture), theme, TABLET)
    assert svg == svg_snapshot


def test_render_is_deterministic() -> None:
    state = fixture_state("electrical_normal")
    page = config_page("electrical")
    assert render_page(page, state, LCD, TABLET) == render_page(page, state, LCD, TABLET)


def test_empty_state_renders_everything_unavailable() -> None:
    svg = render_page(config_page("electrical"), {}, LCD, TABLET)
    colors = set(re.findall(r'(?:stroke|fill)="(#[0-9a-f]{6})"', svg))
    allowed = {LCD.background, LCD.text_color, LCD.color(Status.UNAVAILABLE)}
    # The unbound bus tie has no data source, so it is the only "normal" element.
    allowed.add(LCD.color(Status.NORMAL))
    assert colors <= allowed
    assert svg.count('stroke-dasharray="0 6" stroke-linecap="round"') >= 5


def test_target_sets_pixel_size_and_canvas_sets_viewbox() -> None:
    svg = render_page(config_page("electrical"), {}, LCD, TABLET)
    assert 'viewBox="0 0 1000 600"' in svg
    assert 'width="1280" height="768"' in svg


@pytest.mark.parametrize("theme", THEMES, ids=lambda t: t.name)
def test_only_theme_palette_colors_are_emitted(theme: Theme) -> None:
    for fixture in FIXTURES:
        svg = render_page(config_page("electrical"), fixture_state(fixture), theme, TABLET)
        assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= theme.palette()


def test_eink_mono_shows_severity_by_weight() -> None:
    svg = render_page(
        config_page("electrical"), fixture_state("electrical_islanded"), EINK_MONO, TABLET
    )
    # warning breaker (3x), caution battery (2x), normal lines (1x)
    assert 'stroke-width="6"' in _group(svg, "main_breaker")
    assert 'stroke-width="4"' in _group(svg, "battery")


def _group(svg: str, element_id: str) -> str:
    start = svg.index(f'<g id="{element_id}">')
    end = svg.find('<g id="', start + 1)
    return svg[start : end if end != -1 else len(svg)]


def test_open_breaker_with_grid_lost_is_warning() -> None:
    page = config_page("electrical")
    islanded = render_page(page, fixture_state("electrical_islanded"), LCD, TABLET)
    assert LCD.color(Status.WARNING) in _group(islanded, "main_breaker")
    # Breaker off but grid still reporting: only the map's caution applies.
    state = dict(fixture_state("electrical_normal"))
    state["switch.main_breaker"] = fixture_state("electrical_islanded")["switch.main_breaker"]
    opened = render_page(page, state, LCD, TABLET)
    assert LCD.color(Status.CAUTION) in _group(opened, "main_breaker")
