"""Theme definition: everything that varies visually between targets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mfdhome.model.binding import Status


@dataclass(frozen=True)
class Theme:
    """Palette, stroke weights and typography for a display target.

    Symbol geometry never depends on the theme; only these values do.
    """

    name: str
    background: str
    colors: Mapping[Status, str]
    text_color: str
    line_width: float
    symbol_stroke_width: float
    unavailable_dash: str
    font_family: str
    font_size: float
    label_font_size: float
    allow_animation: bool

    def color(self, status: Status) -> str:
        """Return the palette color for ``status``."""
        return self.colors[status]

    def palette(self) -> frozenset[str]:
        """All colors this theme may emit."""
        return frozenset({self.background, self.text_color, *self.colors.values()})
