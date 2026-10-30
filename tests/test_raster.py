"""Rasterization to e-paper PNGs: palette compliance, fonts, margins, snapshots."""

import io

import pytest
from PIL import Image
from syrupy.assertion import SnapshotAssertion

from mfdhome.model import Status
from mfdhome.render import render_page
from mfdhome.render.controls import Controls
from mfdhome.render.panels import GRAY16, MONO, PANELS, SPECTRA6, PanelProfile
from mfdhome.render.raster import rasterize
from mfdhome.themes import EINK_COLOR, EINK_MONO, Target, Theme
from tests.support import board_from, config_page, fixture_state, image_colors, view

#: A common 7.5" panel.
PANEL_800 = Target("eink", 800, 480)


def _electrical(target: Target = PANEL_800, theme: Theme = EINK_MONO) -> str:
    """An e-ink frame of the islanded house: hatching, a dashed core, the banner
    between the key labels, and the "as of" stamp."""
    board = board_from("electrical_islanded")
    state = fixture_state("electrical_islanded")
    keys = Controls(alerts=Status.WARNING)
    page = config_page("electrical")
    return render_page(page, state, theme, target, view(board), keys, as_of="AS OF 14:05")


def _image(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png))


@pytest.mark.parametrize("panel", [MONO, GRAY16], ids=lambda p: p.name)
def test_electrical_png_snapshot(panel: PanelProfile, png_snapshot: SnapshotAssertion) -> None:
    assert rasterize(_electrical(), panel, EINK_MONO.background) == png_snapshot


def test_color_png_snapshot(png_snapshot: SnapshotAssertion) -> None:
    png = rasterize(_electrical(theme=EINK_COLOR), SPECTRA6, EINK_COLOR.background)
    assert png == png_snapshot
    assert image_colors(_image(png)) <= set(SPECTRA6.colors)


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
    # A 5:3 page on a 2:1 panel is centered, with 67 px bands either side. (A
    # taller panel grows the canvas instead: see the annunciator band.)
    image = _image(rasterize(_electrical(Target("eink", 800, 400)), MONO, "#000000"))
    assert image.size == (800, 400)
    rgb = image.convert("RGB")
    assert image_colors(rgb.crop((0, 0, 64, 400))) == {"#000000"}
    assert image_colors(rgb.crop((70, 0, 100, 40))) == {"#ffffff"}  # the page's own paper
