"""Snapshot and purity tests for the Electrical page."""

import re

import pytest
from syrupy.assertion import SnapshotAssertion

from mfdhome.model import Status
from mfdhome.render import render_page
from mfdhome.themes import DARK, Target
from tests.pages import electrical_page
from tests.support import fixture_state

TABLET = Target("tablet", 1280, 768)


@pytest.mark.parametrize(
    "fixture", ["electrical_normal", "electrical_export", "electrical_unavailable"]
)
def test_electrical_dark_snapshot(fixture: str, svg_snapshot: SnapshotAssertion) -> None:
    svg = render_page(electrical_page(), fixture_state(fixture), DARK, TABLET)
    assert svg == svg_snapshot


def test_render_is_deterministic() -> None:
    state = fixture_state("electrical_normal")
    assert render_page(electrical_page(), state, DARK, TABLET) == render_page(
        electrical_page(), state, DARK, TABLET
    )


def test_empty_state_renders_everything_unavailable() -> None:
    svg = render_page(electrical_page(), {}, DARK, TABLET)
    colors = set(re.findall(r'(?:stroke|fill)="(#[0-9a-f]{6})"', svg))
    allowed = {DARK.background, DARK.text_color, DARK.color(Status.UNAVAILABLE)}
    # The unbound bus tie has no data source, so it is the only "normal" element.
    allowed.add(DARK.color(Status.NORMAL))
    assert colors <= allowed
    assert svg.count('stroke-dasharray="8 6"') >= 5


def test_target_sets_pixel_size_and_canvas_sets_viewbox() -> None:
    svg = render_page(electrical_page(), {}, DARK, TABLET)
    assert 'viewBox="0 0 1000 600"' in svg
    assert 'width="1280" height="768"' in svg


def test_only_theme_palette_colors_are_emitted() -> None:
    for fixture in ("electrical_normal", "electrical_export", "electrical_unavailable"):
        svg = render_page(electrical_page(), fixture_state(fixture), DARK, TABLET)
        assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= DARK.palette()
