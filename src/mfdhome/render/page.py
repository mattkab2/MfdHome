"""Pure page rendering: (page, state, theme, target) -> SVG string."""

from __future__ import annotations

import logging

from mfdhome.model.page import (
    BatteryElement,
    BreakerElement,
    Element,
    LineElement,
    Page,
    TextElement,
)
from mfdhome.model.state import StateSnapshot
from mfdhome.render.resolve import resolve_battery, resolve_breaker, resolve_line
from mfdhome.symbols import battery, breaker, line, svg
from mfdhome.symbols.style import font
from mfdhome.themes.target import Target
from mfdhome.themes.theme import Theme

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"


def render_element(element: Element, state: StateSnapshot, theme: Theme) -> str:
    """Render one element to an SVG group tagged with its id."""
    match element:
        case LineElement():
            resolved_line = resolve_line(element, state)
            body = line(
                element.points, resolved_line.status, resolved_line.flow, resolved_line.label, theme
            )
        case BatteryElement():
            resolved_battery = resolve_battery(element, state)
            body = battery(
                element.x,
                element.y,
                resolved_battery.fill_fraction,
                resolved_battery.status,
                resolved_battery.labels,
                theme,
            )
        case BreakerElement():
            resolved_breaker = resolve_breaker(element, state)
            body = breaker(
                element.x,
                element.y,
                resolved_breaker.closed,
                resolved_breaker.status,
                element.orientation,
                theme,
            )
        case TextElement():
            body = svg.element(
                "text",
                {
                    "x": element.x,
                    "y": element.y,
                    "text-anchor": "middle",
                    **font(theme, theme.label_font_size, theme.text_color),
                },
                [svg.text(element.text)],
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
