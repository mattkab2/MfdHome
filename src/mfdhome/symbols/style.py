"""Stroke styling shared by all symbols."""

from __future__ import annotations

from mfdhome.model.binding import Status
from mfdhome.symbols.svg import AttrValue
from mfdhome.themes.theme import Theme


def dotted(theme: Theme) -> dict[str, AttrValue]:
    """The no-data pattern: round dots."""
    return {"stroke-dasharray": theme.unavailable_dots, "stroke-linecap": "round"}


def stroke(status: Status, theme: Theme, width: float) -> dict[str, AttrValue]:
    """Stroke attributes for ``status``: palette color and status weight, dotted if unavailable."""
    pattern = dotted(theme) if status is Status.UNAVAILABLE else {}
    return {"stroke": theme.color(status), "stroke-width": width * theme.weight(status), **pattern}


def font(theme: Theme, size: float, fill: str) -> dict[str, AttrValue]:
    """Text attributes for the theme's font."""
    return {"font-family": theme.font_family, "font-size": size, "fill": fill}
