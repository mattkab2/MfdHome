"""Theme definition: everything that varies visually between display types."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

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


@dataclass(frozen=True)
class Theme:
    """Palette, weights, fill and attention style for a display type.

    Symbol geometry never depends on the theme; only these values do.
    ``status_weight`` multiplies stroke widths per status, giving a non-color
    severity cue on palettes that cannot show color (missing entries are 1).
    ``dim`` draws things that are present but inactive (unlit tiles).
    Lines: ``line_width`` is a plain line's width, ``casing_width`` a cased
    line's (hollow pipe's) outer width and ``casing_wall`` its wall thickness.
    ``hatch_spacing`` is the stripe period of a warning line's hatching.
    ``core_inset`` is the gap between a flowing cased line's walls and its
    solid core.
    ``structure`` draws what doesn't report (floorplan walls and rooms),
    receding behind status colors; ``None`` uses ``text_color``.
    ``filled_text`` is the text color on a filled tile per status (default:
    the background); ``faint`` lists statuses too pale for text on the
    background, so text that would be drawn in their color (outlined tiles,
    readouts) uses ``text_color`` instead.
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
    status_weight: Mapping[Status, float] = field(default_factory=dict)
    filled_text: Mapping[Status, str] = field(default_factory=dict)
    structure: str | None = None
    faint: frozenset[Status] = frozenset()
    casing_width: float = 10.0
    casing_wall: float = 2.0
    hatch_spacing: float = 4.0
    core_inset: float = 1.0

    def color(self, status: Status) -> str:
        """Return the palette color for ``status``."""
        return self.colors[status]

    def text_in(self, status: Status) -> str:
        """Color for text drawn in ``status``'s color on the background."""
        return self.text_color if status in self.faint else self.colors[status]

    def weight(self, status: Status) -> float:
        """Stroke width multiplier for ``status``."""
        return self.status_weight.get(status, 1.0)

    def palette(self) -> frozenset[str]:
        """All colors this theme may emit."""
        return frozenset(
            {
                self.background,
                self.text_color,
                self.dim,
                *self.colors.values(),
                *self.filled_text.values(),
                self.structure_color,
            }
        )

    @property
    def structure_color(self) -> str:
        """The color for structure: walls and rooms."""
        return self.structure or self.text_color
