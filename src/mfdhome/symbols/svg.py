"""Deterministic SVG text helpers."""

from __future__ import annotations

from collections.abc import Iterable
from xml.sax.saxutils import escape, quoteattr

type AttrValue = str | float | int | None
type Attrs = dict[str, AttrValue]


def fmt(value: float) -> str:
    """Format a number with at most 2 decimals and no trailing zeros."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def points(pts: Iterable[tuple[float, float]]) -> str:
    """Format a point list for ``points``/path attributes."""
    return " ".join(f"{fmt(x)},{fmt(y)}" for x, y in pts)


def element(tag: str, attrs: dict[str, AttrValue], children: Iterable[str] = ()) -> str:
    """Render one SVG element. Attributes keep insertion order; ``None`` values are dropped."""
    parts = [tag]
    for key, value in attrs.items():
        if value is None:
            continue
        text = fmt(value) if isinstance(value, (int, float)) else value
        parts.append(f"{key}={quoteattr(text)}")
    body = "".join(children)
    if not body:
        return f"<{' '.join(parts)}/>"
    return f"<{' '.join(parts)}>{body}</{tag}>"


def text(content: str) -> str:
    """Escape text content."""
    return escape(content)


# Shapes: their geometry attributes first, then ``attrs`` in order.


def rect(x: float, y: float, width: float, height: float, attrs: Attrs | None = None) -> str:
    """A ``rect`` with its top-left corner at (x, y)."""
    return element("rect", {"x": x, "y": y, "width": width, "height": height, **(attrs or {})})


def line(x1: float, y1: float, x2: float, y2: float, attrs: Attrs | None = None) -> str:
    """A ``line`` from (x1, y1) to (x2, y2)."""
    return element("line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, **(attrs or {})})


def circle(cx: float, cy: float, r: float, attrs: Attrs | None = None) -> str:
    """A ``circle`` of radius ``r`` centered at (cx, cy)."""
    return element("circle", {"cx": cx, "cy": cy, "r": r, **(attrs or {})})


def polygon(pts: Iterable[tuple[float, float]], attrs: Attrs | None = None) -> str:
    """A closed ``polygon`` through ``pts``."""
    return element("polygon", {"points": points(pts), **(attrs or {})})


def polyline(pts: Iterable[tuple[float, float]], attrs: Attrs | None = None) -> str:
    """An open ``polyline`` through ``pts``."""
    return element("polyline", {"points": points(pts), **(attrs or {})})
