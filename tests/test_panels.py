"""Panel profiles and quantization to a panel's palette."""

import io
import random

import pytest
from PIL import Image

from mfdhome.render.panels import GRAY4, MONO, PANELS, SPECTRA6, PanelProfile, hex_rgb
from mfdhome.render.raster import encode_png, image_colors, quantize
from mfdhome.themes.builtin import EINK_COLOR, EINK_MONO, LCD


def _noise(size: int = 48, seed: int = 7) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new("RGB", (size, size))
    image.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(size * size)])
    return image


def _nearest(pixel: tuple[int, int, int], panel: PanelProfile) -> tuple[int, int, int]:
    return min(panel.rgb(), key=lambda c: sum((a - b) ** 2 for a, b in zip(c, pixel, strict=True)))


@pytest.mark.parametrize("panel", PANELS.values(), ids=lambda p: p.name)
def test_quantized_image_uses_only_panel_colors(panel: PanelProfile) -> None:
    out = quantize(_noise(), panel)
    assert image_colors(out) <= {c.lower() for c in panel.colors}


@pytest.mark.parametrize("panel", PANELS.values(), ids=lambda p: p.name)
def test_quantize_maps_to_nearest_color_without_dithering(panel: PanelProfile) -> None:
    source = _noise(16)
    out = quantize(source, panel).convert("RGB")
    for xy in ((x, y) for x in range(16) for y in range(16)):
        pixel = source.getpixel(xy)
        assert isinstance(pixel, tuple)
        expected = _nearest((pixel[0], pixel[1], pixel[2]), panel)
        got = out.getpixel(xy)
        assert isinstance(got, tuple)
        # Ties may go either way; the chosen color must be as close as the nearest.
        dist = [sum((a - b) ** 2 for a, b in zip(c, pixel, strict=True)) for c in (expected, got)]
        assert dist[0] == dist[1]


def test_flat_regions_stay_flat() -> None:
    # A solid color between palette entries must not be dithered into a pattern.
    image = Image.new("RGB", (20, 20), (120, 120, 120))
    assert len(image_colors(quantize(image, MONO))) == 1


@pytest.mark.parametrize(("panel", "bits"), [(MONO, 1), (GRAY4, 2), (SPECTRA6, 4)])
def test_png_uses_indexed_color_at_minimal_depth(panel: PanelProfile, bits: int) -> None:
    png = encode_png(quantize(_noise(), panel))
    assert png[24] == bits  # IHDR bit depth
    assert png[25] == 3  # IHDR color type: indexed
    assert image_colors(Image.open(io.BytesIO(png))) <= {c.lower() for c in panel.colors}


def test_png_encoding_is_deterministic() -> None:
    image = quantize(_noise(), SPECTRA6)
    assert encode_png(image) == encode_png(image)


def test_theme_support() -> None:
    assert MONO.unsupported(EINK_MONO) == frozenset()
    assert SPECTRA6.unsupported(EINK_MONO) == frozenset()
    assert LCD.palette() & MONO.unsupported(LCD) == MONO.unsupported(LCD)
    assert MONO.unsupported(LCD)
    assert SPECTRA6.unsupported(EINK_COLOR) == frozenset()
    assert MONO.unsupported(EINK_COLOR) == {"#ff0000", "#ffff00", "#0000ff", "#00ff00"}


def test_hex_rgb() -> None:
    assert hex_rgb("#FF8000") == (255, 128, 0)
    with pytest.raises(ValueError, match="#rrggbb"):
        hex_rgb("#fff")
