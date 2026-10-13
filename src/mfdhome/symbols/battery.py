"""Battery symbol: outlined cell with terminal nub and charge fill bar."""

from __future__ import annotations

from collections.abc import Sequence

from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import font, stroke
from mfdhome.themes.theme import Theme

WIDTH = 60.0
HEIGHT = 100.0
NUB_WIDTH = 24.0
NUB_HEIGHT = 8.0
INSET = 5.0
LINE_SPACING = 1.3


def battery(
    x: float,
    y: float,
    fill_fraction: float | None,
    status: Status,
    labels: Sequence[str],
    theme: Theme,
) -> str:
    """Render a battery centered at (x, y).

    ``fill_fraction`` (0..1) sets the charge bar height; ``None`` draws no bar.
    ``labels`` are stacked below the cell.
    """
    color = theme.color(status)
    left, top = x - WIDTH / 2, y - HEIGHT / 2
    outline = stroke(status, theme, theme.symbol_stroke_width)
    parts = [
        svg.element(
            "rect",
            {"x": left, "y": top, "width": WIDTH, "height": HEIGHT, "fill": "none", **outline},
        ),
        svg.element(
            "rect",
            {
                "x": x - NUB_WIDTH / 2,
                "y": top - NUB_HEIGHT,
                "width": NUB_WIDTH,
                "height": NUB_HEIGHT,
                "fill": "none",
                **outline,
            },
        ),
    ]
    if fill_fraction is not None:
        inner = HEIGHT - 2 * INSET
        bar = inner * min(max(fill_fraction, 0.0), 1.0)
        parts.append(
            svg.element(
                "rect",
                {
                    "x": left + INSET,
                    "y": top + INSET + inner - bar,
                    "width": WIDTH - 2 * INSET,
                    "height": bar,
                    "fill": color,
                },
            )
        )
    for i, label in enumerate(labels):
        parts.append(
            svg.element(
                "text",
                {
                    "x": x,
                    "y": y + HEIGHT / 2 + theme.font_size * (1 + i * LINE_SPACING),
                    "text-anchor": "middle",
                    **font(theme, theme.font_size, color),
                },
                [svg.text(label)],
            )
        )
    return "".join(parts)
