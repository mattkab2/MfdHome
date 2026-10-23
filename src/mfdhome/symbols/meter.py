"""Meter symbol: a circle with its unit inside (electric ``kWh``, water ``GAL``)."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke, text_at
from mfdhome.themes.theme import Theme

RADIUS = 20.0
LABEL_SCALE = 0.75  # label size relative to the theme's font size


def meter_box(x: float, y: float) -> Box:
    """Bounding box of a meter centered at (x, y), in either orientation."""
    return Box(x - RADIUS, y - RADIUS, x + RADIUS, y + RADIUS)


def meter(x: float, y: float, label: str, status: Status, theme: Theme) -> str:
    """Render a meter centered at (x, y): a circle with ``label`` across its middle.

    The circle is the same in both orientations and the label always reads
    upright; only the ports move.
    """
    return svg.circle(
        x, y, RADIUS, {"fill": "none", **stroke(status, theme, theme.symbol_stroke_width)}
    ) + text_at(x, y, label, theme, theme.font_size * LABEL_SCALE, theme.text_in(status))
