"""Rasterization for e-paper: SVG to PNG, quantized to a panel's palette."""

from __future__ import annotations

import io
from pathlib import Path

import resvg_py
from PIL import Image

from mfdhome.render.panels import RGB, PanelProfile

#: Fonts bundled with the library, so renders are identical on every machine.
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"


def rasterize(svg: str, panel: PanelProfile, background: str) -> bytes:
    """Render ``svg`` (at its own pixel size) for ``panel`` and return PNG bytes.

    Only the bundled fonts are used, never system fonts. ``background`` fills
    any margin around a page whose shape differs from the display's. Panels
    without intermediate tones are drawn without antialiasing, so edges never
    quantize to unrelated colors.
    """
    smooth = panel.antialias
    png = resvg_py.svg_to_bytes(
        svg_string=svg,
        background=background,
        skip_system_fonts=True,
        font_dirs=[str(FONT_DIR)],
        monospace_family="DejaVu Sans Mono",
        shape_rendering="geometric_precision" if smooth else "crisp_edges",
        text_rendering="geometric_precision" if smooth else "optimize_speed",
    )
    return encode_png(quantize(Image.open(io.BytesIO(png)), panel))


def quantize(image: Image.Image, panel: PanelProfile) -> Image.Image:
    """Map every pixel of ``image`` to the nearest ``panel`` color, without dithering.

    Returns a palette (``P`` mode) image whose palette is exactly the panel's
    colors, so the PNG encoder can use 1, 2 or 4 bits per pixel.
    """
    # Exact nearest color (Pillow's own palette quantizer only approximates),
    # computed once per distinct color: rendered pages have few of them.
    rgb = image.convert("RGB")
    palette = panel.rgb()
    data = rgb.tobytes()
    index: dict[bytes, int] = {}
    out = bytearray(rgb.width * rgb.height)
    for i in range(len(out)):
        pixel = data[3 * i : 3 * i + 3]
        found = index.get(pixel)
        if found is None:
            found = index[pixel] = _nearest(pixel, palette)
        out[i] = found
    result = Image.frombytes("P", rgb.size, bytes(out))
    result.putpalette([v for color in palette for v in color])
    return result


def _nearest(pixel: bytes, palette: tuple[RGB, ...]) -> int:
    """Index of the palette color closest to ``pixel`` (Euclidean RGB; first wins ties)."""
    distances = [sum((a - b) ** 2 for a, b in zip(color, pixel, strict=True)) for color in palette]
    return distances.index(min(distances))


def encode_png(image: Image.Image) -> bytes:
    """Encode ``image`` as PNG, with no timestamps or other varying metadata."""
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
