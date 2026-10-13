"""Deterministic SVG text helpers."""

from __future__ import annotations

from collections.abc import Iterable
from xml.sax.saxutils import escape, quoteattr

type AttrValue = str | float | int | None


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
