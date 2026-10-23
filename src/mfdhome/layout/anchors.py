"""Anchors: named positions around a bounding box where text is attached.

Nine anchors form a 3x3 grid over the box (rows top/center/bottom, columns
left/center/right). The row and column also set alignment, so text always
grows away from the symbol:

- left column text ends at the anchor, right column text starts there,
  center column text is centered;
- top row text sits above, bottom row text hangs below, center row text is
  vertically centered.

Several labels at one anchor stack away from the box (top row upward, bottom
row downward, center row centered). Positions are pure geometry: the same for
every theme except where they scale with font size.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from mfdhome.layout.path import Point

#: Baseline-to-baseline distance as a multiple of font size.
LINE_SPACING = 1.3
#: Approximate cap height as a fraction of font size, used to hang text below an edge.
ASCENT = 0.75
#: Gap between a symbol's box and attached text.
SYMBOL_GAP = 4.0
#: Gap between a line's path and attached text.
LINE_GAP = 14.0


class Anchor(StrEnum):
    """The nine anchor positions."""

    TOP_LEFT = "top-left"
    TOP_CENTER = "top-center"
    TOP_RIGHT = "top-right"
    CENTER_LEFT = "center-left"
    CENTER = "center"
    CENTER_RIGHT = "center-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_CENTER = "bottom-center"
    BOTTOM_RIGHT = "bottom-right"

    @property
    def row(self) -> str:
        """``top``, ``center`` or ``bottom``."""
        return self.value.split("-")[0]

    @property
    def column(self) -> str:
        """``left``, ``center`` or ``right``."""
        parts = self.value.split("-")
        return parts[1] if len(parts) == 2 else "center"


ALIASES = {
    "top": Anchor.TOP_CENTER,
    "bottom": Anchor.BOTTOM_CENTER,
    "left": Anchor.CENTER_LEFT,
    "right": Anchor.CENTER_RIGHT,
    "middle": Anchor.CENTER,
}


def parse_anchor(name: str) -> Anchor:
    """Parse an anchor name or alias; raises ``ValueError`` for unknown names."""
    key = name.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    return Anchor(key)


def anchor_names() -> list[str]:
    """All accepted anchor names, including aliases."""
    return [a.value for a in Anchor] + list(ALIASES)


@dataclass(frozen=True)
class Box:
    """An axis-aligned bounding box in canvas units."""

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def point(cls, x: float, y: float) -> Box:
        """A zero-size box, used to anchor text to a point on a line."""
        return cls(x, y, x, y)

    @property
    def cx(self) -> float:
        """Horizontal center."""
        return (self.left + self.right) / 2

    @property
    def cy(self) -> float:
        """Vertical center."""
        return (self.top + self.bottom) / 2


@dataclass(frozen=True)
class Placement:
    """Where and how to draw one text label.

    ``baseline`` is an SVG ``dominant-baseline`` value, or ``None`` for the
    default alphabetic baseline at ``y``.
    """

    x: float
    y: float
    text_anchor: str
    baseline: str | None


_TEXT_ANCHOR = {"left": "end", "center": "middle", "right": "start"}


def place_stack(
    box: Box,
    anchor: Anchor,
    font_sizes: Sequence[float],
    gap: float = SYMBOL_GAP,
    offset: tuple[float, float] = (0.0, 0.0),
) -> list[Placement]:
    """Place a stack of labels (in reading order, top to bottom) at ``anchor``.

    ``font_sizes`` has one entry per label. Returns one placement per label.
    """
    if not font_sizes:
        return []
    row, column = anchor.row, anchor.column
    side_gap = gap if row == "center" else 0.0
    x = {"left": box.left - side_gap, "center": box.cx, "right": box.right + side_gap}[column]

    # Baselines relative to the first label, top to bottom.
    rel = [0.0]
    for size in font_sizes[1:]:
        rel.append(rel[-1] + LINE_SPACING * size)

    if row == "top":
        start = box.top - gap - rel[-1]
        baseline = None
    elif row == "bottom":
        start = box.bottom + gap + ASCENT * font_sizes[0]
        baseline = None
    else:
        start = box.cy - rel[-1] / 2
        baseline = "middle"

    dx, dy = offset
    return [Placement(x + dx, start + r + dy, _TEXT_ANCHOR[column], baseline) for r in rel]


def box_point(box: Box, anchor: Anchor) -> Point:
    """The point on ``box`` named by ``anchor``: an edge midpoint, corner or the center."""
    x = {"left": box.left, "center": box.cx, "right": box.right}[anchor.column]
    y = {"top": box.top, "center": box.cy, "bottom": box.bottom}[anchor.row]
    return (x, y)


def default_line_anchor(direction: tuple[float, float], back: bool = False) -> Anchor:
    """Text above mostly-horizontal lines, to the right of mostly-vertical ones;
    ``back`` (a two-way line's other direction): below, or to the left."""
    dx, dy = direction
    if abs(dx) >= abs(dy):
        return Anchor.BOTTOM_CENTER if back else Anchor.TOP_CENTER
    return Anchor.CENTER_LEFT if back else Anchor.CENTER_RIGHT
