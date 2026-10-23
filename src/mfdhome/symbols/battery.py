"""Battery symbol: outlined cell with terminal nub and charge fill bar."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

WIDTH = 60.0
HEIGHT = 100.0
NUB_WIDTH = 24.0
NUB_HEIGHT = 8.0
INSET = 5.0


def battery_box(x: float, y: float) -> Box:
    """Bounding box of a battery centered at (x, y), including the nub."""
    return Box(x - WIDTH / 2, y - HEIGHT / 2 - NUB_HEIGHT, x + WIDTH / 2, y + HEIGHT / 2)


def battery(x: float, y: float, fill_fraction: float | None, status: Status, theme: Theme) -> str:
    """Render a battery centered at (x, y).

    ``fill_fraction`` (0..1, clamped) sets the charge bar height; ``None`` draws no bar.
    """
    left, top = x - WIDTH / 2, y - HEIGHT / 2
    outline = stroke(status, theme, theme.symbol_stroke_width)
    parts = [
        svg.rect(left, top, WIDTH, HEIGHT, {"fill": "none", **outline}),
        svg.rect(
            x - NUB_WIDTH / 2, top - NUB_HEIGHT, NUB_WIDTH, NUB_HEIGHT, {"fill": "none", **outline}
        ),
    ]
    if fill_fraction is not None:
        inner = HEIGHT - 2 * INSET
        bar = inner * min(max(fill_fraction, 0.0), 1.0)
        parts.append(
            svg.rect(
                left + INSET,
                top + INSET + inner - bar,
                WIDTH - 2 * INSET,
                bar,
                {"fill": theme.color(status)},
            )
        )
    return "".join(parts)
