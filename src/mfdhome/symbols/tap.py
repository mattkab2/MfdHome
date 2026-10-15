"""Tap symbols: an outdoor hose bib and an indoor faucet.

Both show a drop under the spout while open (only when a state is bound and
says so). The hose bib is fed from the left, the faucet from below.
"""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.layout.path import Point
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

SIZE = 40.0
DROP_HEIGHT = 6.0
DROP_RADIUS = 3.0


def tap_box(x: float, y: float) -> Box:
    """Bounding box of a hose bib or faucet centered at (x, y)."""
    half = SIZE / 2
    return Box(x - half, y - half, x + half, y + half)


def hose_bib_inlet(at: Point) -> Port:
    """A hose bib's supply: the left edge."""
    return Port((at[0] - SIZE / 2, at[1]), (-1.0, 0.0))


def faucet_inlet(at: Point) -> Port:
    """A faucet's supply: the bottom edge (through the counter)."""
    return Port((at[0], at[1] + SIZE / 2), (0.0, 1.0))


def _drop(x: float, top: float, status: Status, theme: Theme) -> str:
    f, r, h = svg.fmt, DROP_RADIUS, DROP_HEIGHT
    d = (
        f"M{f(x)} {f(top)}"
        f" C{f(x + 1)} {f(top + 2)} {f(x + r)} {f(top + 3.5)} {f(x + r)} {f(top + h - 1)}"
        f" A{f(r)} {f(r)} 0 0 1 {f(x - r)} {f(top + h - 1)}"
        f" C{f(x - r)} {f(top + 3.5)} {f(x - 1)} {f(top + 2)} {f(x)} {f(top)} Z"
    )
    return svg.element("path", {"d": d, "fill": theme.color(status), "stroke": "none"})


def _line(x1: float, y1: float, x2: float, y2: float, outline: dict[str, svg.AttrValue]) -> str:
    return svg.element("line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, **outline})


def hose_bib(x: float, y: float, running: bool, status: Status, theme: Theme) -> str:
    """Render a hose bib centered at (x, y): inlet, body with a T handle, threaded spout."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    f = svg.fmt
    spout = f"M{f(x + 8)} {f(y)} L{f(x + 11)} {f(y)} Q{f(x + 15)} {f(y)} {f(x + 15)} {f(y + 4)}"
    spout += f" L{f(x + 15)} {f(y + 11)}"
    parts = [
        _line(x - SIZE / 2, y, x - 6, y, outline),
        svg.element(
            "rect",
            {"x": x - 6, "y": y - 6, "width": 14, "height": 12, "rx": 2, "fill": "none", **outline},
        ),
        svg.element("path", {"d": spout, "fill": "none", **outline}),
        _line(x + 12, y + 7, x + 18, y + 7, outline),  # hose threads
        _line(x + 12, y + 10, x + 18, y + 10, outline),
        _line(x + 1, y - 6, x + 1, y - 13, outline),  # handle stem
        _line(x - 6, y - 13, x + 8, y - 13, outline),  # T handle
    ]
    if running:
        parts.append(_drop(x + 15, y + 13, status, theme))
    return "".join(parts)


def faucet(x: float, y: float, running: bool, status: Status, theme: Theme) -> str:
    """Render a faucet centered at (x, y): riser, base, gooseneck spout and side lever."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    f = svg.fmt
    neck = f"M{f(x)} {f(y + 4)} L{f(x)} {f(y - 6)}"
    neck += f" A8 8 0 0 1 {f(x + 16)} {f(y - 6)} L{f(x + 16)} {f(y - 1)}"
    parts = [
        _line(x, y + SIZE / 2, x, y + 10, outline),
        svg.element(
            "rect",
            {"x": x - 7, "y": y + 4, "width": 14, "height": 6, "rx": 1, "fill": "none", **outline},
        ),
        svg.element("path", {"d": neck, "fill": "none", **outline}),
        _line(x - 7, y + 6, x - 15, y + 1, outline),  # lever
    ]
    if running:
        parts.append(_drop(x + 16, y + 2, status, theme))
    return "".join(parts)
