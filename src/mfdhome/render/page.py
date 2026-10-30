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
    EnclosureElement,
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
from mfdhome.symbols.line import Flow, arrow_reach, line, tag_plate
from mfdhome.symbols.registry import LINE_BACK, SymbolInput, get_symbol
from mfdhome.symbols.style import dotted, font
from mfdhome.symbols.tile import (
    ATTENTION_CLASS,
    BANNER_HEIGHT,
    RING_OUTSET,
    STAMP_WIDTH,
    TILE_HEIGHT,
    TILE_WIDTH,
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
    default_readout: Callable[[Readout], Anchor],
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
        anchor = r.anchor or default_readout(r)
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


def _flow(
    element: LineElement, values: Mapping[str, Value], c: _Ctx
) -> tuple[Flow | None, Flow | None]:
    """Which way the line flows now, and a two-way line's flow the other way: from
    its condition, from its rate's sign, or from each direction's rate (none at
    all while its gate fails)."""
    spec = element.flow
    if spec is None:
        return None, None
    forward, backward = (
        (Flow.REVERSE, Flow.FORWARD) if spec.reverse else (Flow.FORWARD, Flow.REVERSE)
    )

    def flowing(channel: str) -> float | None:
        rate = values[channel].number
        return None if rate is None or abs(rate) <= spec.threshold else rate

    if spec.when is not None:
        return (forward if holds(spec.when, c.resolver.context(element.bind)) else None), None
    if spec.gate is not None and not holds(spec.gate, c.resolver.context(element.bind)):
        return None, None
    rate = flowing(spec.channel)
    if spec.back is not None:
        back = flowing(spec.back)
        return (None if rate is None else forward), (None if back is None else backward)
    if rate is None:
        return None, None
    return (forward if rate > 0 else backward), None


def _render_line(element: LineElement, c: _Ctx) -> tuple[str, str]:
    """The line's casing layer and its body (inner stroke, arrow, labels)."""
    theme = c.theme
    resolved = c.resolver.element(element)
    assert resolved is not None
    status, values = resolved.status, resolved.values
    flow, back = _flow(element, values, c)
    if (flow is not None or back is not None) and status is Status.NORMAL:
        status = Status.ACTIVE
    two_way = element.flow is not None and element.flow.back is not None

    def default_anchor(along: float, backward: bool = False) -> Anchor:
        return default_line_anchor(point_along(element.points, along)[1], backward)

    def readout_anchor(r: Readout) -> Anchor:
        return default_anchor(r.along, two_way and r.channel == LINE_BACK)

    # The flow arrow sits level with the first readout, on the other side of the
    # line; with no readout but a service tag, in the other half from the tag.
    # A two-way line's forward arrow sits on its first readout's side instead,
    # its backward arrow on the other side, each beneath its direction's readout.
    readout = element.readouts[0] if element.readouts else None
    arrow_at = readout.along if readout else None
    if readout is None and element.tag is not None:
        arrow_at = 0.75 if element.tag.along < 0.5 else 0.25
    avoid = None
    if two_way and readout is None:
        avoid = _toward(default_anchor(0.5, backward=True))
    elif two_way and readout is not None:
        toward = _toward(readout.anchor or readout_anchor(readout))
        avoid = toward if readout.channel == LINE_BACK else (-toward[0], -toward[1])
    elif readout is not None and readout.anchor:
        avoid = _toward(readout.anchor)
    parts = line(
        element.points,
        status,
        flow,
        theme,
        element.casing,
        element.id,
        arrow_at=arrow_at,
        arrow_avoid=avoid,
        back=back,
    )

    def box_at(along: float) -> Box:
        return Box.point(*point_along(element.points, along)[0])

    # Readouts that go with the arrows show only while their direction flows (the
    # arrow keeps its place by the first readout either way).
    shown = [
        r
        for r in element.readouts
        if not r.with_flow or (back if two_way and r.channel == LINE_BACK else flow) is not None
    ]
    labels = _collect_labels(
        element.name, shown, values, status, theme, default_anchor, readout_anchor
    )
    # A two-way line's labels clear the harpoons on both sides.
    edge = arrow_reach(parts.half_width) if two_way else parts.half_width
    gap = max(LINE_GAP, edge + LABEL_CLEARANCE)
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


def _frame(box: Box, status: Status, theme: Theme, quiet: str) -> str:
    """A container's frame: in ``quiet`` while normal, in the status color otherwise."""
    calm = status in (Status.NORMAL, Status.ACTIVE)
    return svg.rect(
        box.left,
        box.top,
        box.right - box.left,
        box.bottom - box.top,
        {
            "fill": "none",
            "stroke": quiet if calm else theme.color(status),
            "stroke-width": theme.symbol_stroke_width * theme.weight(status),
            **(dotted(theme) if status is Status.UNAVAILABLE else {}),
        },
    )


def _container_labels(
    element: GroupElement | EnclosureElement, status: Status, values: Mapping[str, Value], c: _Ctx
) -> list[str]:
    box = element_box(element)
    assert box is not None
    readouts = element.readouts if isinstance(element, GroupElement) else ()
    labels = _collect_labels(
        element.name,
        readouts,
        values,
        status,
        c.theme,
        default_name=lambda _: Anchor.TOP_CENTER,
        default_readout=lambda _: Anchor.BOTTOM_CENTER,
    )
    return _draw_labels(labels, lambda _: box, SYMBOL_GAP, c.theme)


def _render_group(element: GroupElement, c: _Ctx) -> str:
    """Frame (status-colored when not normal), items, then name and readouts."""
    resolved = c.resolver.element(element)
    assert resolved is not None
    box = element_box(element)
    assert box is not None
    parts = []
    if element.frame is Frame.OUTLINE:
        parts.append(_frame(box, resolved.status, c.theme, c.theme.dim))
    parts.extend(_render_layers(item, c)[1] for item in element.items)
    parts.extend(_container_labels(element, resolved.status, resolved.values, c))
    return "".join(parts)


def _render_enclosure(element: EnclosureElement, c: _Ctx) -> str:
    """Frame and name; the members draw themselves. A cabinet is structure, so while
    normal its frame takes the structure color (which shows on paper, unlike dim)."""
    resolved = c.resolver.element(element)
    assert resolved is not None
    box = element_box(element)
    assert box is not None
    return _frame(box, resolved.status, c.theme, c.theme.structure_color) + "".join(
        _container_labels(element, resolved.status, {}, c)
    )


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
        case EnclosureElement():
            body = _render_enclosure(element, c)
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
    return svg.circle(
        element.at[0],
        element.at[1],
        theme.line_width * JUNCTION_RADIUS,
        {"fill": theme.color(Status.NORMAL)},
    )


#: Extra height a display must have over its page before the annunciator band
#: appears; anything less is letterboxed as before.
BAND_MIN = TILE_HEIGHT + 16.0
#: The band's tiles: at most this many to a row, this far apart.
BAND_COLUMNS = 5
BAND_GAP = (24.0, 8.0)


def canvas_height(page: Page, target: Target) -> float:
    """The canvas height to draw ``page`` on for ``target``: the page's own, or, on a
    display proportionally taller (a 4:3 panel for a 5:3 page) by at least
    ``BAND_MIN``, the page's width at the display's proportions."""
    wanted = page.width * target.height_px / target.width_px
    return wanted if wanted - page.height >= BAND_MIN else page.height


def band_tiles(page: Page, height: float, systems: Sequence[str]) -> list[TileElement]:
    """The annunciator band's tiles below a page drawn on a taller canvas.

    The band runs from the page's own reserved strip to the canvas's bottom
    strip. Tiles go in rows of ``BAND_COLUMNS``, as many rows as fit, centered;
    systems that don't fit are left out. A page with tiles of its own (the
    status page) gets none, so they aren't shown twice.
    """
    if height <= page.height or any(isinstance(e, TileElement) for e in page.elements):
        return []
    # Keep an unacknowledged tile's ring clear of the page and the strip.
    top = page.height - BANNER_HEIGHT + RING_OUTSET
    bottom = height - BANNER_HEIGHT - RING_OUTSET
    gap_x, gap_y = BAND_GAP
    rows = max(0, int((bottom - top + gap_y) // (TILE_HEIGHT + gap_y)))
    shown = list(systems)[: rows * BAND_COLUMNS]
    if not shown:
        return []
    used_rows = -(-len(shown) // BAND_COLUMNS)
    first_y = (top + bottom) / 2 - (used_rows - 1) * (TILE_HEIGHT + gap_y) / 2
    tiles = []
    for row in range(used_rows):
        names = shown[row * BAND_COLUMNS : (row + 1) * BAND_COLUMNS]
        first_x = page.width / 2 - (len(names) - 1) * (TILE_WIDTH + gap_x) / 2
        for col, system in enumerate(names):
            at = (first_x + col * (TILE_WIDTH + gap_x), first_y + row * (TILE_HEIGHT + gap_y))
            tiles.append(TileElement(f"band-{system}", at, system))
    return tiles


def _resolver(page: Page, state: StateSnapshot, alerts: AlertView) -> Resolver:
    """A resolver that knows top-level elements' channel values.

    Bindings to another element's channel never chain (the loader forbids
    binding to a channel that is itself such a binding), so one pre-pass over
    top-level elements is enough.
    """
    by_id = {element.id: element for element in page.elements}
    first = Resolver(state, alerts, by_id=by_id)
    values = {}
    for element in page.elements:
        resolved = first.element(element)
        if resolved is not None:
            values[element.id] = resolved.values
    return Resolver(state, alerts, values, by_id)


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
    annunciator: Sequence[str] = (),
) -> str:
    """Render ``page`` with ``state`` for ``target`` as a standalone SVG document.

    ``alerts`` supplies alert definitions, the shared board and its history for
    tiles, alert logs, alert-driven element status and the annunciator banner
    along the bottom of the canvas (while a caution or warning is
    unacknowledged). ``controls`` adds the soft keys to that strip, with the
    banner between them. ``as_of`` (a short text such as "AS OF 14:05", or
    two lines split by a newline, supplied by the caller) is drawn at the
    right end of the banner's space, which the banner then leaves free.

    On a display proportionally taller than the page (see ``canvas_height``),
    the canvas grows to fill it: the page keeps the top, the bottom strip moves
    to the display's bottom, and the band between holds the ``annunciator``
    systems' tiles.

    Output is deterministic: no clock, randomness or I/O, and fixed element and
    attribute order.
    """
    logger.debug("rendering page %s for target %s", page.id, target.name)
    c = _Ctx(state, theme, alerts, _resolver(page, state, alerts))
    # Enclosure frames first, beneath the pipes that cross them; nodes last, so
    # junction dots sit on top of the lines that meet there.
    ordered = sorted(
        page.elements,
        key=lambda e: (
            0 if isinstance(e, EnclosureElement) else 2 if isinstance(e, NodeElement) else 1
        ),
    )
    layers = [_render_layers(element, c) for element in ordered]
    underlays = [underlay for underlay, _ in layers if underlay]
    frames = sum(isinstance(e, EnclosureElement) for e in page.elements)
    groups = [group for _, group in layers]
    children = [
        svg.rect(0, 0, page.width, canvas_height(page, target), {"fill": theme.background}),
        *groups[:frames],
        # Every line's casing beneath every line's body, so hollow pipes merge at joints.
        *([svg.element("g", {"id": "casings"}, underlays)] if underlays else []),
        *groups[frames:],
    ]
    height = canvas_height(page, target)
    tiles = band_tiles(page, height, annunciator)
    if tiles:
        children.append(
            svg.element("g", {"id": "annunciator"}, [_render_tile(t, c) for t in tiles])
        )
    strip = banner_strip(page.width, height)
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
                "viewBox": f"0 0 {svg.fmt(page.width)} {svg.fmt(canvas_height(page, target))}",
                "width": target.width_px,
                "height": target.height_px,
                "data-page": page.id,
                "data-theme": theme.name,
            },
            children,
        )
        + "\n"
    )
