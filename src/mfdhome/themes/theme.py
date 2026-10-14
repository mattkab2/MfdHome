"""Theme definition: everything that varies visually between display types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from mfdhome.model.binding import Status


class AttentionKind(StrEnum):
    """How a display marks something unacknowledged."""

    FLASH = "flash"  # on/off blink (LCD/LED panels)
    PULSE = "pulse"  # slow opacity fade (mirror)
    RING = "ring"  # static outer outline (e-ink: no animation)
    NONE = "none"


#: Maximum flash rate, in flashes per second (WCAG 2.3.1 allows 3; we stay well under).
MAX_FLASH_HZ = 1.0


@dataclass(frozen=True)
class Attention:
    """Attention style. ``period`` is seconds per cycle; ``low_opacity`` is the dim phase."""

    kind: AttentionKind
    period: float = 1.0
    low_opacity: float = 0.25

    def __post_init__(self) -> None:
        if self.kind is AttentionKind.FLASH and 1 / self.period > MAX_FLASH_HZ:
            raise ValueError(f"flash rate above {MAX_FLASH_HZ} Hz is not allowed")

    @property
    def animated(self) -> bool:
        """Whether this style needs CSS animation."""
        return self.kind in (AttentionKind.FLASH, AttentionKind.PULSE)


class TileFill(StrEnum):
    """How a lit annunciator tile is drawn."""

    FILLED = "filled"  # severity-colored fill, text in the background color
    OUTLINE = "outline"  # severity-colored outline and text


def _ones() -> Mapping[Status, float]:
    return MappingProxyType({})


@dataclass(frozen=True)
class Theme:
    """Palette, weights, fill and attention style for a display type.

    Symbol geometry never depends on the theme; only these values do.
    ``status_weight`` multiplies stroke widths per status, giving a non-color
    severity cue on palettes that cannot show color (missing entries are 1).
    ``dim`` draws things that are present but inactive (unlit tiles).
    Line policy: ``casing_allowed`` (``False`` draws every line solid),
    ``casing_width`` (outer width of a cased line at weight 1), ``casing_wall``
    (wall thickness) and ``max_line_weight`` (cap on any line's weight). These
    are applied after page styles, so a theme's limits always hold.
    ``unavailable_dots`` is the dash array for the no-data pattern; drawn with
    round caps, a zero-length dash ("0 6") gives round dots.
    """

    name: str
    background: str
    colors: Mapping[Status, str]
    text_color: str
    dim: str
    line_width: float
    symbol_stroke_width: float
    unavailable_dots: str
    font_family: str
    font_size: float
    label_font_size: float
    attention: Attention
    tile_fill: Mapping[Status, TileFill]
    status_weight: Mapping[Status, float] = field(default_factory=_ones)
    casing_allowed: bool = True
    casing_width: float = 8.0
    casing_wall: float = 2.0
    max_line_weight: float = 3.0

    def color(self, status: Status) -> str:
        """Return the palette color for ``status``."""
        return self.colors[status]

    def weight(self, status: Status) -> float:
        """Stroke width multiplier for ``status``."""
        return self.status_weight.get(status, 1.0)

    def palette(self) -> frozenset[str]:
        """All colors this theme may emit."""
        return frozenset({self.background, self.text_color, self.dim, *self.colors.values()})
