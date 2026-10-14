"""Pure page rendering: (page, state, theme, target) -> SVG string."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mfdhome.conditions.evaluate import EvalContext
from mfdhome.conditions.model import ChannelRef
from mfdhome.conditions.values import Value
from mfdhome.layout.anchors import (
    LINE_GAP,
    SYMBOL_GAP,
    Anchor,
    Box,
    Placement,
    default_line_anchor,
    place_stack,
)
from mfdhome.layout.path import point_along
from mfdhome.model.binding import Status
from mfdhome.model.page import (
    Element,
    LineElement,
    Name,
    Page,
    Readout,
    SymbolElement,
    TextElement,
)
from mfdhome.model.state import StateSnapshot
from mfdhome.render.format import format_value
from mfdhome.render.status import element_status
from mfdhome.symbols import svg
from mfdhome.symbols.line import Flow, line
from mfdhome.symbols.registry import (
    LINE_CHANNELS,
    LINE_NUMERIC,
    LINE_PRIMARY,
    SymbolInput,
    get_symbol,
)
from mfdhome.symbols.style import font
from mfdhome.themes.target import Target
from mfdhome.themes.theme import Theme

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class _Label:
    text: str
    size: float
    color: str
    anchor: Anchor
    along: float
    offset: tuple[float, float]


def _text(placement: Placement, content: str, size: float, color: str, theme: Theme) -> str:
    return svg.element(
        "text",
        {
            "x": placement.x,
            "y": placement.y,
            "text-anchor": placement.text_anchor,
            "dominant-baseline": placement.baseline,
            **font(theme, size, color),
        },
        [svg.text(content)],
    )


def _collect_labels(
    name: Name | None,
    readouts: Sequence[Readout],
    values: Mapping[str, Value],
    status: Status,
    theme: Theme,
    default_name: Callable[[float], Anchor],
    default_readout: Callable[[float], Anchor],
) -> list[_Label]:
    labels = []
    if name is not None:
        anchor = name.anchor or default_name(name.along)
        labels.append(
            _Label(
                name.text, theme.label_font_size, theme.text_color, anchor, name.along, name.offset
            )
        )
    for r in readouts:
        text = format_value(values[r.channel], r.format, r.unit, r.absolute)
        anchor = r.anchor or default_readout(r.along)
        labels.append(_Label(text, theme.font_size, theme.color(status), anchor, r.along, r.offset))
    return labels


def _draw_labels(
    labels: Sequence[_Label], box_at: Callable[[float], Box], gap: float, theme: Theme
) -> list[str]:
    """Stack labels sharing an anchor (and position along a line), in order."""
    groups: dict[tuple[Anchor, float], list[_Label]] = {}
    for label in labels:
        groups.setdefault((label.anchor, label.along), []).append(label)
    parts = []
    for (anchor, along), group in groups.items():
        placements = place_stack(box_at(along), anchor, [g.size for g in group], gap)
        for label, p in zip(group, placements, strict=True):
            dx, dy = label.offset
            moved = Placement(p.x + dx, p.y + dy, p.text_anchor, p.baseline)
            parts.append(_text(moved, label.text, label.size, label.color, theme))
    return parts


def _render_symbol(element: SymbolElement, state: StateSnapshot, theme: Theme) -> str:
    spec = get_symbol(element.type)
    ctx = EvalContext(state, element.bind)
    values = {channel: ctx.value(ChannelRef(channel)) for channel in spec.channels}
    status = element_status(element.status, ctx, spec.primary, spec.primary in spec.numeric)
    body = spec.draw(
        SymbolInput(element.at, element.orientation, status, values, element.params), theme
    )
    box = spec.box(element.at, element.orientation)
    labels = _collect_labels(
        element.name,
        element.readouts,
        values,
        status,
        theme,
        default_name=lambda _: Anchor.TOP_CENTER,
        default_readout=lambda _: Anchor.BOTTOM_CENTER,
    )
    return body + "".join(_draw_labels(labels, lambda _: box, SYMBOL_GAP, theme))


def _flow(element: LineElement, ctx: EvalContext) -> Flow | None:
    if element.flow is None:
        return None
    power = ctx.value(ChannelRef(element.flow.channel)).number
    if power is None or abs(power) <= element.flow.threshold:
        return None
    return Flow.FORWARD if power > 0 else Flow.REVERSE


def _render_line(element: LineElement, state: StateSnapshot, theme: Theme) -> str:
    ctx = EvalContext(state, element.bind)
    values = {channel: ctx.value(ChannelRef(channel)) for channel in LINE_CHANNELS}
    status = element_status(element.status, ctx, LINE_PRIMARY, LINE_PRIMARY in LINE_NUMERIC)
    flow = _flow(element, ctx)
    if flow is not None and status is Status.NORMAL:
        status = Status.ACTIVE
    body = line(element.points, status, flow, theme)

    def default_anchor(along: float) -> Anchor:
        return default_line_anchor(point_along(element.points, along)[1])

    def box_at(along: float) -> Box:
        return Box.point(*point_along(element.points, along)[0])

    labels = _collect_labels(
        element.name, element.readouts, values, status, theme, default_anchor, default_anchor
    )
    return body + "".join(_draw_labels(labels, box_at, LINE_GAP, theme))


def render_element(element: Element, state: StateSnapshot, theme: Theme) -> str:
    """Render one element to an SVG group tagged with its id."""
    match element:
        case SymbolElement():
            body = _render_symbol(element, state, theme)
        case LineElement():
            body = _render_line(element, state, theme) if len(element.points) >= 2 else ""
        case TextElement():
            body = _text(
                Placement(element.at[0], element.at[1], element.align, None),
                element.text,
                theme.label_font_size,
                theme.text_color,
                theme,
            )
    return svg.element("g", {"id": element.id}, [body])


def render_page(page: Page, state: StateSnapshot, theme: Theme, target: Target) -> str:
    """Render ``page`` with ``state`` for ``target`` as a standalone SVG document.

    Output is deterministic: no clock, randomness or I/O, and fixed element and
    attribute order.
    """
    logger.debug("rendering page %s for target %s", page.id, target.name)
    children = [
        svg.element(
            "rect",
            {"x": 0, "y": 0, "width": page.width, "height": page.height, "fill": theme.background},
        ),
        *(render_element(element, state, theme) for element in page.elements),
    ]
    return (
        svg.element(
            "svg",
            {
                "xmlns": SVG_NS,
                "viewBox": f"0 0 {svg.fmt(page.width)} {svg.fmt(page.height)}",
                "width": target.width_px,
                "height": target.height_px,
                "data-page": page.id,
                "data-theme": theme.name,
            },
            children,
        )
        + "\n"
    )
