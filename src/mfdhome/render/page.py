"""Pure page rendering: (page, state, theme, target) -> SVG string."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from mfdhome.conditions.evaluate import holds
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
from mfdhome.layout.path import Point, point_along
from mfdhome.model.binding import Status
from mfdhome.model.page import (
    Element,
    Frame,
    GroupElement,
    LineElement,
    LogElement,
    Name,
    NodeElement,
    Page,
    Readout,
    RoomElement,
    SymbolElement,
    TextElement,
    TileElement,
    WallElement,
)
from mfdhome.model.state import StateSnapshot
from mfdhome.render.alerts import NO_ALERTS, SEVERITY_STATUS, AlertView
from mfdhome.render.controls import Controls, banner_box, soft_keys
from mfdhome.render.log import alert_log
from mfdhome.render.resolve import Resolver
from mfdhome.symbols import svg
from mfdhome.symbols.floorplan import room, wall
from mfdhome.symbols.format import format_value
from mfdhome.symbols.geometry import element_box
from mfdhome.symbols.line import Flow, line, tag_plate
from mfdhome.symbols.registry import (
    SymbolInput,
    get_symbol,
)
from mfdhome.symbols.style import dotted, font
from mfdhome.symbols.tile import (
    ATTENTION_CLASS,
    STAMP_WIDTH,
    TileLook,
    banner,
    banner_strip,
    stamp,
    tile,
)
from mfdhome.themes.target import Target
from mfdhome.themes.theme import AttentionKind, Theme

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


@dataclass(frozen=True)
class _Ctx:
    """Everything element rendering needs."""

    state: StateSnapshot
    theme: Theme
    alerts: AlertView
    resolver: Resolver


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
        labels.append(
            _Label(text, theme.font_size, theme.text_in(status), anchor, r.along, r.offset)
        )
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


def _render_symbol(element: SymbolElement, c: _Ctx) -> str:
    theme = c.theme
    spec = get_symbol(element.type)
    resolved = c.resolver.element(element)
    assert resolved is not None
    status, values = resolved.status, resolved.values
    body = spec.draw(
        SymbolInput(element.at, element.orientation, status, values, element.params), theme
    )
    box = spec.bounds(element.at, element.orientation, element.params)
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


def _flow(element: LineElement, values: Mapping[str, Value], c: _Ctx) -> Flow | None:
    """Which way the line flows now: from its condition, or from its rate's sign."""
    spec = element.flow
    if spec is None:
        return None
    if spec.when is not None:
        if not holds(spec.when, c.resolver.context(element.bind)):
            return None
        forward = True
    else:
        rate = values[spec.channel].number
        if rate is None or abs(rate) <= spec.threshold:
            return None
        forward = rate > 0
    return Flow.FORWARD if forward != spec.reverse else Flow.REVERSE


def _render_line(element: LineElement, c: _Ctx) -> tuple[str, str]:
    """The line's casing layer and its body (inner stroke, arrow, labels)."""
    theme = c.theme
    resolved = c.resolver.element(element)
    assert resolved is not None
    status, values = resolved.status, resolved.values
    flow = _flow(element, values, c)
    if flow is not None and status is Status.NORMAL:
        status = Status.ACTIVE
    # The flow arrow sits level with the first readout, on the other side of the
    # line; with no readout but a service tag, in the other half from the tag.
    readout = element.readouts[0] if element.readouts else None
    arrow_at = readout.along if readout else None
    if readout is None and element.tag is not None:
        arrow_at = 0.75 if element.tag.along < 0.5 else 0.25
    parts = line(
        element.points,
        status,
        flow,
        theme,
        element.casing,
        element.id,
        arrow_at=arrow_at,
        arrow_avoid=_toward(readout.anchor) if readout and readout.anchor else None,
    )

    def default_anchor(along: float) -> Anchor:
        return default_line_anchor(point_along(element.points, along)[1])

    def box_at(along: float) -> Box:
        return Box.point(*point_along(element.points, along)[0])

    labels = _collect_labels(
        element.name, element.readouts, values, status, theme, default_anchor, default_anchor
    )
    gap = max(LINE_GAP, parts.half_width + LABEL_CLEARANCE)
    tag = (
        tag_plate(
            point_along(element.points, element.tag.along)[0], element.tag.text, status, theme
        )
        if element.tag is not None and len(element.points) >= 2
        else ""
    )
    return parts.casing, parts.body + tag + "".join(_draw_labels(labels, box_at, gap, theme))


def _toward(anchor: Anchor) -> Point:
    """The direction from a line to text at ``anchor`` (e.g. up for ``top``)."""
    x = {"left": -1.0, "center": 0.0, "right": 1.0}[anchor.column]
    y = {"top": -1.0, "center": 0.0, "bottom": 1.0}[anchor.row]
    return (x, y)


#: Minimum space between a line's edge and its labels.
LABEL_CLEARANCE = 8.0


def _render_tile(element: TileElement, c: _Ctx) -> str:
    theme, alerts = c.theme, c.alerts
    view = alerts.system(element.system, c.state)
    system = alerts.systems.get(element.system)
    label = element.label or (system.label if system else element.system)
    look = TileLook(
        status=None if view.severity is None else SEVERITY_STATUS[view.severity],
        cleared=view.cleared,
        attention=view.unacknowledged,
        unavailable=view.unavailable,
    )
    return tile(element.at[0], element.at[1], label, look, theme)


def _render_group(element: GroupElement, c: _Ctx) -> str:
    """Frame (status-colored when not normal), items, then name and readouts."""
    theme = c.theme
    resolved = c.resolver.element(element)
    assert resolved is not None
    status = resolved.status
    box = element_box(element)
    assert box is not None
    parts = []
    if element.frame is Frame.OUTLINE:
        calm = status in (Status.NORMAL, Status.ACTIVE)
        parts.append(
            svg.element(
                "rect",
                {
                    "x": box.left,
                    "y": box.top,
                    "width": box.right - box.left,
                    "height": box.bottom - box.top,
                    "fill": "none",
                    "stroke": theme.dim if calm else theme.color(status),
                    "stroke-width": theme.symbol_stroke_width * theme.weight(status),
                    **(dotted(theme) if status is Status.UNAVAILABLE else {}),
                },
            )
        )
    parts.extend(_render_layers(item, c)[1] for item in element.items)
    labels = _collect_labels(
        element.name,
        element.readouts,
        resolved.values,
        status,
        theme,
        default_name=lambda _: Anchor.TOP_CENTER,
        default_readout=lambda _: Anchor.BOTTOM_CENTER,
    )
    parts.extend(_draw_labels(labels, lambda _: box, SYMBOL_GAP, theme))
    return "".join(parts)


def render_element(
    element: Element, state: StateSnapshot, theme: Theme, alerts: AlertView = NO_ALERTS
) -> str:
    """Render one element on its own: any underlay (line casing), then its group."""
    underlay, group = _render_layers(element, _Ctx(state, theme, alerts, Resolver(state, alerts)))
    return underlay + group


def _render_layers(element: Element, c: _Ctx) -> tuple[str, str]:
    """An element's underlay (tagged with ``data-for``) and its group (tagged with its id)."""
    theme = c.theme
    underlay = ""
    match element:
        case SymbolElement():
            body = _render_symbol(element, c)
        case LineElement():
            casing, body = _render_line(element, c)
            if casing:
                underlay = svg.element("g", {"data-for": element.id}, [casing])
        case GroupElement():
            body = _render_group(element, c)
        case TextElement():
            body = _text(
                Placement(element.at[0], element.at[1], element.align, None),
                element.text,
                theme.label_font_size,
                theme.text_color,
                theme,
            )
        case TileElement():
            body = _render_tile(element, c)
        case NodeElement():
            body = _render_node(element, theme)
        case LogElement():
            body = alert_log(element, c.alerts, theme)
        case RoomElement():
            resolved = c.resolver.element(element)
            status = Status.NORMAL if resolved is None else resolved.status
            body = room(element.points, element.name, element.label_at, status, theme)
        case WallElement():
            body = wall(element.points, element.exterior, theme)
    return underlay, svg.element("g", {"id": element.id}, [body])


#: Junction dot radius as a multiple of the theme's line width.
JUNCTION_RADIUS = 1.5


def _render_node(element: NodeElement, theme: Theme) -> str:
    if not element.junction:
        return ""
    return svg.element(
        "circle",
        {
            "cx": element.at[0],
            "cy": element.at[1],
            "r": theme.line_width * JUNCTION_RADIUS,
            "fill": theme.color(Status.NORMAL),
        },
    )


def _resolver(page: Page, state: StateSnapshot, alerts: AlertView) -> Resolver:
    """A resolver that knows top-level elements' channel values.

    Bindings to another element's channel never chain (the loader forbids
    binding to a channel that is itself such a binding), so one pre-pass over
    top-level elements is enough.
    """
    first = Resolver(state, alerts)
    values = {}
    for element in page.elements:
        resolved = first.element(element)
        if resolved is not None:
            values[element.id] = resolved.values
    return Resolver(state, alerts, values)


def attention_css(theme: Theme) -> str:
    """CSS for the theme's animated attention cue (flash or pulse); empty otherwise.

    The browser keeps time, so render stays pure. Every attention element shares
    one animation, so they stay in phase.
    """
    attention = theme.attention
    if not attention.animated:
        return ""
    timing = "step-end" if attention.kind is AttentionKind.FLASH else "ease-in-out"
    return (
        f".{ATTENTION_CLASS}{{animation:mfd-attn {svg.fmt(attention.period)}s {timing} infinite}}"
        f"@keyframes mfd-attn{{50%{{opacity:{svg.fmt(attention.low_opacity)}}}}}"
    )


def render_page(
    page: Page,
    state: StateSnapshot,
    theme: Theme,
    target: Target,
    alerts: AlertView = NO_ALERTS,
    controls: Controls | None = None,
    as_of: str | None = None,
) -> str:
    """Render ``page`` with ``state`` for ``target`` as a standalone SVG document.

    ``alerts`` supplies alert definitions, the shared board and its history for
    tiles, alert logs, alert-driven element status and the annunciator banner
    along the bottom of the canvas (while a caution or warning is
    unacknowledged). ``controls`` adds the soft keys to that strip, with the
    banner between them. ``as_of`` (a short text such as "AS OF 14:05",
    supplied by the caller) is drawn at the right end of the banner's space,
    which the banner then leaves free.

    Output is deterministic: no clock, randomness or I/O, and fixed element and
    attribute order.
    """
    logger.debug("rendering page %s for target %s", page.id, target.name)
    c = _Ctx(state, theme, alerts, _resolver(page, state, alerts))
    # Nodes last, so junction dots sit on top of the lines that meet there.
    ordered = sorted(page.elements, key=lambda e: isinstance(e, NodeElement))
    layers = [_render_layers(element, c) for element in ordered]
    underlays = [underlay for underlay, _ in layers if underlay]
    children = [
        svg.element(
            "rect",
            {"x": 0, "y": 0, "width": page.width, "height": page.height, "fill": theme.background},
        ),
        # Every line's casing beneath every line's body, so hollow pipes merge at joints.
        *([svg.element("g", {"id": "casings"}, underlays)] if underlays else []),
        *(group for _, group in layers),
    ]
    strip = banner_strip(page.width, page.height)
    box = strip if controls is None else banner_box(strip)
    if as_of is not None:
        note = Box(box.right - STAMP_WIDTH, box.top, box.right, box.bottom)
        box = Box(box.left, box.top, note.left, box.bottom)
        children.append(svg.element("g", {"id": "as-of"}, [stamp(note, as_of, theme)]))
    shown = alerts.banner()
    if shown is not None:
        status = SEVERITY_STATUS[shown.alert.severity]
        children.append(
            svg.element(
                "g",
                {"id": "banner"},
                [banner(box, shown.alert.message, shown.others, status, theme)],
            )
        )
    if controls is not None:
        children.append(svg.element("g", {"id": "controls"}, [soft_keys(strip, controls, theme)]))
    css = attention_css(theme)
    if css and f'class="{ATTENTION_CLASS}"' in "".join(children):
        children.insert(0, svg.element("style", {}, [css]))
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
