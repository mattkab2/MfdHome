"""Stroke and text styling shared by all symbols."""

from __future__ import annotations

from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.svg import AttrValue
from mfdhome.themes.theme import Theme


def dotted(theme: Theme) -> dict[str, AttrValue]:
    """The no-data pattern: round dots."""
    return {"stroke-dasharray": theme.unavailable_dots, "stroke-linecap": "round"}


def stroke(status: Status, theme: Theme, width: float) -> dict[str, AttrValue]:
    """Stroke attributes for ``status``: palette color and status weight, dotted if unavailable."""
    pattern = dotted(theme) if status is Status.UNAVAILABLE else {}
    return {"stroke": theme.color(status), "stroke-width": width * theme.weight(status), **pattern}


def detail(status: Status, theme: Theme, width: float) -> dict[str, AttrValue]:
    """Stroke attributes for fine marks inside a symbol: palette color, dotted if
    unavailable, but never the status weight, which would fill them in. The
    outline around them carries the weight."""
    pattern = dotted(theme) if status is Status.UNAVAILABLE else {}
    return {"stroke": theme.color(status), "stroke-width": width, **pattern}


def font(theme: Theme, size: float, fill: str) -> dict[str, AttrValue]:
    """Text attributes for the theme's font."""
    return {"font-family": theme.font_family, "font-size": size, "fill": fill}


def text_at(
    x: float,
    y: float,
    content: str,
    theme: Theme,
    size: float,
    fill: str,
    anchor: str = "middle",
) -> str:
    """One line of text in the theme's font, vertically centered on ``y``;
    ``anchor`` (``start``, ``middle``, ``end``) places it horizontally on ``x``."""
    return svg.element(
        "text",
        {
            "x": x,
            "y": y,
            "text-anchor": anchor,
            "dominant-baseline": "middle",
            **font(theme, size, fill),
        },
        [svg.text(content)],
    )
