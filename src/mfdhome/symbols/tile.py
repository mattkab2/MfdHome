"""Annunciator tile and banner symbols."""

from __future__ import annotations

from dataclasses import dataclass

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import dotted, font
from mfdhome.themes.theme import AttentionKind, Theme, TileFill

TILE_WIDTH = 160.0
TILE_HEIGHT = 64.0
RING_OUTSET = 6.0
BANNER_HEIGHT = 40.0
CLEARED_MARK = "CLR"
ATTENTION_CLASS = "attn"


@dataclass(frozen=True)
class TileLook:
    """Resolved tile state.

    ``status`` is the lit color role, or ``None`` for a dark tile. ``cleared``
    means latched but no longer active. ``attention`` means unacknowledged.
    """

    status: Status | None
    cleared: bool = False
    attention: bool = False
    unavailable: bool = False


def tile_box(x: float, y: float) -> Box:
    """Bounding box of a tile centered at (x, y)."""
    return Box(x - TILE_WIDTH / 2, y - TILE_HEIGHT / 2, x + TILE_WIDTH / 2, y + TILE_HEIGHT / 2)


def _attention_group(parts: list[str], attention: bool, theme: Theme) -> str:
    animated = attention and theme.attention.animated
    return svg.element("g", {"class": ATTENTION_CLASS if animated else None}, parts)


def _ring(box: Box, color: str, theme: Theme) -> str:
    return svg.element(
        "rect",
        {
            "x": box.left - RING_OUTSET,
            "y": box.top - RING_OUTSET,
            "width": box.right - box.left + 2 * RING_OUTSET,
            "height": box.bottom - box.top + 2 * RING_OUTSET,
            "fill": "none",
            "stroke": color,
            "stroke-width": theme.symbol_stroke_width,
        },
    )


def _panel(
    box: Box, look: TileLook, theme: Theme, opaque: bool, ring: bool
) -> tuple[list[str], str]:
    """The tile/banner rectangle(s) and the color for text drawn on it.

    ``ring`` allows the static attention ring (on themes that use one).
    """
    rect: dict[str, svg.AttrValue] = {
        "x": box.left,
        "y": box.top,
        "width": box.right - box.left,
        "height": box.bottom - box.top,
    }
    background = theme.background if opaque else "none"
    if look.status is None:
        color = theme.color(Status.UNAVAILABLE)
        attrs = {
            **rect,
            "fill": background,
            "stroke": color if look.unavailable else theme.dim,
            "stroke-width": theme.symbol_stroke_width,
            **(dotted(theme) if look.unavailable else {}),
        }
        return [svg.element("rect", attrs)], color

    color = theme.color(look.status)
    width = theme.symbol_stroke_width * theme.weight(look.status)
    fill = theme.tile_fill.get(look.status, TileFill.OUTLINE)
    parts = []
    if fill is TileFill.FILLED and not look.cleared:
        parts.append(
            svg.element("rect", {**rect, "fill": color, "stroke": color, "stroke-width": width})
        )
        text_color = theme.background
    else:
        parts.append(
            svg.element(
                "rect", {**rect, "fill": background, "stroke": color, "stroke-width": width}
            )
        )
        text_color = color
    if ring and look.attention and theme.attention.kind is AttentionKind.RING:
        parts.append(_ring(box, color, theme))
    return parts, text_color


def tile(x: float, y: float, label: str, look: TileLook, theme: Theme) -> str:
    """Render an annunciator tile centered at (x, y)."""
    box = tile_box(x, y)
    parts, text_color = _panel(box, look, theme, opaque=False, ring=True)
    parts.append(
        svg.element(
            "text",
            {
                "x": x,
                "y": y,
                "text-anchor": "middle",
                "dominant-baseline": "middle",
                **font(theme, theme.label_font_size, text_color),
            },
            [svg.text(label)],
        )
    )
    if look.status is not None and look.cleared:
        parts.append(
            svg.element(
                "text",
                {
                    "x": box.right - 6,
                    "y": box.top + 6,
                    "text-anchor": "end",
                    "dominant-baseline": "hanging",
                    **font(theme, theme.font_size * 0.75, text_color),
                },
                [CLEARED_MARK],
            )
        )
    return _attention_group(parts, look.attention, theme)


def banner(
    width: float, height: float, message: str, others: int, status: Status, theme: Theme
) -> str:
    """Render the annunciator banner across the bottom of a ``width`` x ``height`` canvas.

    The banner is opaque, so it reads cleanly over page content, and always
    carries the attention cue (it only appears for unacknowledged alerts).
    """
    box = Box(0, height - BANNER_HEIGHT, width, height)
    look = TileLook(status, attention=True)
    # No ring: it would fall off the canvas, and the banner itself is the cue.
    parts, text_color = _panel(box, look, theme, opaque=True, ring=False)
    text_attrs = {"dominant-baseline": "middle", **font(theme, theme.label_font_size, text_color)}
    parts.append(
        svg.element(
            "text",
            {"x": 16, "y": box.cy, "text-anchor": "start", **text_attrs},
            [svg.text(message)],
        )
    )
    if others:
        parts.append(
            svg.element(
                "text",
                {"x": width - 16, "y": box.cy, "text-anchor": "end", **text_attrs},
                [f"+{others}"],
            )
        )
    return _attention_group(parts, True, theme)
