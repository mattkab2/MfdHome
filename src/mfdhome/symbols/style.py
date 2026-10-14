"""Stroke styling shared by all symbols."""

from __future__ import annotations

from mfdhome.model.binding import Status
from mfdhome.symbols.svg import AttrValue
from mfdhome.themes.theme import Theme


def stroke(status: Status, theme: Theme, width: float) -> dict[str, AttrValue]:
    """Stroke attributes for ``status``: palette color and status weight, dashed if unavailable."""
    return {
        "stroke": theme.color(status),
        "stroke-width": width * theme.weight(status),
        "stroke-dasharray": theme.unavailable_dash if status is Status.UNAVAILABLE else None,
    }


def font(theme: Theme, size: float, fill: str) -> dict[str, AttrValue]:
    """Text attributes for the theme's font."""
    return {"font-family": theme.font_family, "font-size": size, "fill": fill}
