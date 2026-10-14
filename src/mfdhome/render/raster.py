"""Rasterization for e-paper: quantize to a panel's palette and encode PNG."""

from __future__ import annotations

import io

from PIL import Image

from mfdhome.render.panels import RGB, PanelProfile


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


def image_colors(image: Image.Image) -> frozenset[str]:
    """Every distinct color in ``image``, as ``#rrggbb``."""
    rgb = image.convert("RGB")
    data = rgb.tobytes()
    return frozenset(f"#{data[i : i + 3].hex()}" for i in range(0, len(data), 3))
