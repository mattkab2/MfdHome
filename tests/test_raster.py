"""Rasterization to e-paper PNGs: palette compliance, fonts, margins, snapshots."""

import io

import pytest
from PIL import Image
from syrupy.assertion import SnapshotAssertion

from mfdhome.render import render_page
from mfdhome.render.panels import GRAY16, MONO, PANELS, PanelProfile
from mfdhome.render.raster import image_colors, rasterize
from mfdhome.themes import EINK_MONO, Target
from tests.support import board_from, config_page, fixture_state, view

#: A common 7.5" panel.
PANEL_800 = Target("eink", 800, 480)


def _electrical(target: Target = PANEL_800) -> str:
    """Islanded, with the alerts that brings: hatching, a dashed core and the banner."""
    board = board_from("electrical_islanded")
    state = fixture_state("electrical_islanded")
    return render_page(config_page("electrical"), state, EINK_MONO, target, view(board))


def _image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png))


@pytest.mark.parametrize("panel", [MONO, GRAY16], ids=lambda p: p.name)
def test_electrical_png_snapshot(panel: PanelProfile, png_snapshot: SnapshotAssertion) -> None:
    assert rasterize(_electrical(), panel, EINK_MONO.background) == png_snapshot


@pytest.mark.parametrize("panel", PANELS.values(), ids=lambda p: p.name)
def test_rasterized_page_uses_only_panel_colors(panel: PanelProfile) -> None:
    image = _image(rasterize(_electrical(), panel, EINK_MONO.background))
    assert image.size == (800, 480)
    assert image_colors(image) <= {c.lower() for c in panel.colors}


def test_panels_without_tones_are_not_antialiased() -> None:
    # Gray panels keep smoothed edges; on a 1-bit panel every pixel is a page color.
    assert len(image_colors(_image(rasterize(_electrical(), GRAY16, "#ffffff")))) > 2
    assert len(image_colors(_image(rasterize(_electrical(), MONO, "#ffffff")))) == 2


def test_rasterize_is_deterministic() -> None:
    svg = _electrical()
    assert rasterize(svg, GRAY16, "#ffffff") == rasterize(svg, GRAY16, "#ffffff")


def test_text_uses_the_bundled_font() -> None:
    # System fonts are skipped, so text only renders if the bundled font loads.
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="40">'
        '<rect width="200" height="40" fill="#ffffff"/>'
        '<text x="10" y="30" font-family="DejaVu Sans Mono, monospace" font-size="24"'
        ' fill="#000000">MFD</text></svg>'
    )
    assert "#000000" in image_colors(_image(rasterize(svg, MONO, "#ffffff")))


def test_margins_take_the_background_color() -> None:
    # A 5:3 page on a 4:3 panel is centered, with 60 px bands above and below.
    image = _image(rasterize(_electrical(Target("eink", 800, 600)), MONO, "#000000"))
    assert image.size == (800, 600)
    rgb = image.convert("RGB")
    assert image_colors(rgb.crop((0, 0, 800, 58))) == {"#000000"}
    assert image_colors(rgb.crop((0, 62, 40, 100))) == {"#ffffff"}  # the page's own paper
