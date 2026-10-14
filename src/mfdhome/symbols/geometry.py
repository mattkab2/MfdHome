"""Element geometry: bounding boxes and connection ports."""

from __future__ import annotations

from mfdhome.layout.anchors import Anchor, Box, box_point, parse_anchor
from mfdhome.layout.path import Point
from mfdhome.model.page import Element, NodeElement, SymbolElement, TileElement
from mfdhome.symbols.registry import get_symbol
from mfdhome.symbols.tile import tile_box


def element_box(element: Element) -> Box | None:
    """The element's bounding box, or ``None`` for elements without one (lines, text)."""
    match element:
        case SymbolElement():
            return get_symbol(element.type).box(element.at, element.orientation)
        case TileElement():
            return tile_box(*element.at)
        case NodeElement():
            return Box.point(*element.at)
        case _:
            return None


def port_names(element: Element) -> list[str]:
    """Port names valid on ``element`` (empty for nodes, which connect at their point)."""
    if isinstance(element, NodeElement) or element_box(element) is None:
        return []
    extra = list(get_symbol(element.type).ports) if isinstance(element, SymbolElement) else []
    edges = [a.value for a in Anchor if a is not Anchor.CENTER]
    return [*extra, *edges, "top", "bottom", "left", "right"]


def port_point(element: Element, port: str | None) -> Point:
    """Where a line attaches to ``element`` at ``port``.

    Nodes take no port. Other boxed elements accept their type's named ports
    and the box's edge midpoints and corners (anchor names, minus ``center``).
    Raises ``ValueError`` with a message listing valid ports.
    """
    if isinstance(element, NodeElement):
        if port is not None:
            raise ValueError(f"node {element.id!r} has no ports; connect to {element.id!r}")
        return element.at
    box = element_box(element)
    if box is None:
        raise ValueError(f"{element.id!r} cannot be connected to")
    valid = ", ".join(port_names(element))
    if port is None:
        raise ValueError(f"connecting to {element.id!r} needs a port: {valid}")
    if isinstance(element, SymbolElement):
        named = get_symbol(element.type).ports.get(port)
        if named is not None:
            return named(element.at, element.orientation)
    try:
        anchor = parse_anchor(port)
    except ValueError:
        anchor = Anchor.CENTER
    if anchor is Anchor.CENTER:
        raise ValueError(f"unknown port {port!r} on {element.id!r}; expected: {valid}")
    x, y = box_point(box, anchor)
    # Edge midpoints sit on the element's own axis, not the box center: a box can
    # be asymmetric (the battery's terminal nub makes its box taller on top).
    cx, cy = element_center(element)
    return (cx if anchor.column == "center" else x, cy if anchor.row == "center" else y)


def element_center(element: Element) -> Point:
    """The element's own center point (its ``at`` for symbols, tiles and nodes)."""
    match element:
        case SymbolElement() | TileElement() | NodeElement():
            return element.at
        case _:
            raise ValueError(f"{element.id!r} has no center")
