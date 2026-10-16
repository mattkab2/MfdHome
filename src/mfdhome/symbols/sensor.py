"""Point sensor symbols: an on/off ``sensor`` and a numeric ``gauge``.

A sensor (leak, smoke, CO, gas, motion, ...) is a small diamond, never a
circle, so it can't be mistaken for a meter, with a 1 to 3 letter code inside.
It is drawn filled while tripped. A gauge is a small box showing a reading
(a room temperature, a pressure), colored by its status.
"""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import font, stroke
from mfdhome.themes.theme import Theme

SENSOR_HALF = 14.0  # half the diamond's diagonal
CODE_SCALE = 0.6  # code size relative to the theme's font size
GAUGE_WIDTH = 64.0
GAUGE_HEIGHT = 24.0
READING_SCALE = 0.75


def sensor_box(x: float, y: float) -> Box:
    """Bounding box of a sensor centered at (x, y)."""
    return Box(x - SENSOR_HALF, y - SENSOR_HALF, x + SENSOR_HALF, y + SENSOR_HALF)


def gauge_box(x: float, y: float) -> Box:
    """Bounding box of a gauge centered at (x, y)."""
    return Box(x - GAUGE_WIDTH / 2, y - GAUGE_HEIGHT / 2, x + GAUGE_WIDTH / 2, y + GAUGE_HEIGHT / 2)


def _centered(x: float, y: float, text: str, size: float, color: str, theme: Theme) -> str:
    return svg.element(
        "text",
        {
            "x": x,
            "y": y,
            "text-anchor": "middle",
            "dominant-baseline": "middle",
            **font(theme, size, color),
        },
        [svg.text(text)],
    )


def sensor(x: float, y: float, code: str, tripped: bool, status: Status, theme: Theme) -> str:
    """Render a sensor centered at (x, y): a diamond, filled while ``tripped``."""
    h = SENSOR_HALF
    color = theme.color(status)
    diamond = svg.element(
        "polygon",
        {
            "points": svg.points(((x, y - h), (x + h, y), (x, y + h), (x - h, y))),
            "fill": color if tripped else "none",
            "stroke-linejoin": "round",
            **stroke(status, theme, theme.symbol_stroke_width),
        },
    )
    if not code:
        return diamond
    ink = theme.filled_text.get(status, theme.background) if tripped else theme.text_in(status)
    return diamond + _centered(x, y, code, theme.font_size * CODE_SCALE, ink, theme)


def gauge(x: float, y: float, reading: str, status: Status, theme: Theme) -> str:
    """Render a gauge centered at (x, y): a box with ``reading`` inside."""
    box = gauge_box(x, y)
    frame = svg.element(
        "rect",
        {
            "x": box.left,
            "y": box.top,
            "width": GAUGE_WIDTH,
            "height": GAUGE_HEIGHT,
            "rx": 3,
            "fill": "none",
            **stroke(status, theme, theme.symbol_stroke_width),
        },
    )
    text = _centered(x, y, reading, theme.font_size * READING_SCALE, theme.text_in(status), theme)
    return frame + text
