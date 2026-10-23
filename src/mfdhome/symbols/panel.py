"""Solar panel symbol: a framed module divided into cells."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

WIDTH = 40.0
HEIGHT = 60.0
ROWS = 3
COLUMNS = 2


def panel_box(x: float, y: float) -> Box:
    """Bounding box of a panel centered at (x, y)."""
    return Box(x - WIDTH / 2, y - HEIGHT / 2, x + WIDTH / 2, y + HEIGHT / 2)


def solar_panel(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a solar panel centered at (x, y): an outline with cell divisions."""
    box = panel_box(x, y)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    inner = stroke(status, theme, theme.symbol_stroke_width / 2)
    parts = [svg.rect(box.left, box.top, WIDTH, HEIGHT, {"fill": "none", **outline})]
    for r in range(1, ROWS):
        yy = box.top + HEIGHT * r / ROWS
        parts.append(svg.line(box.left, yy, box.right, yy, inner))
    for c in range(1, COLUMNS):
        xx = box.left + WIDTH * c / COLUMNS
        parts.append(svg.line(xx, box.top, xx, box.bottom, inner))
    return "".join(parts)
