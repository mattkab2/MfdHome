"""Transfer switch and load panel symbols."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.model.binding import Status
from mfdhome.model.page import Orientation
from mfdhome.symbols import svg
from mfdhome.symbols.style import stroke
from mfdhome.themes.theme import Theme

ATS_WIDTH = 56.0
ATS_HEIGHT = 40.0
CONTACT_RADIUS = 3.0
CONTACT_INSET = 12.0
OPEN_RISE = 0.45  # open blade rises 0.45 * width over its run

PANEL_WIDTH = 60.0
PANEL_HEIGHT = 80.0
PANEL_BREAKERS = 4


def ats_box(x: float, y: float, orientation: Orientation) -> Box:
    """Bounding box of a transfer switch centered at (x, y)."""
    w, h = (
        (ATS_HEIGHT, ATS_WIDTH) if orientation is Orientation.VERTICAL else (ATS_WIDTH, ATS_HEIGHT)
    )
    return Box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def transfer_switch(
    x: float,
    y: float,
    connected: bool | None,
    status: Status,
    orientation: Orientation,
    theme: Theme,
) -> str:
    """Render a grid-isolating transfer switch centered at (x, y).

    The grid side is left (top when vertical), the load side right (bottom).
    The blade pivots at the load contact: across to the grid contact when
    ``connected``, swung open when islanded, absent when unknown.
    """
    half_w, half_h = ATS_WIDTH / 2, ATS_HEIGHT / 2
    outline = stroke(status, theme, theme.symbol_stroke_width)
    color = theme.color(status)
    grid_x, load_x = x - half_w + CONTACT_INSET, x + half_w - CONTACT_INSET
    parts = [
        svg.element(
            "rect",
            {
                "x": x - half_w,
                "y": y - half_h,
                "width": ATS_WIDTH,
                "height": ATS_HEIGHT,
                "fill": "none",
                **outline,
            },
        ),
        *(
            svg.element(
                "circle",
                {
                    "cx": cx,
                    "cy": y,
                    "r": CONTACT_RADIUS,
                    "fill": "none",
                    "stroke": color,
                    "stroke-width": theme.symbol_stroke_width,
                },
            )
            for cx in (grid_x, load_x)
        ),
    ]
    if connected is not None:
        run = load_x - grid_x
        end = (grid_x, y) if connected else (grid_x + run * 0.15, y - run * OPEN_RISE)
        parts.append(
            svg.element(
                "line",
                {
                    "x1": load_x,
                    "y1": y,
                    "x2": end[0],
                    "y2": end[1],
                    **stroke(status, theme, theme.line_width),
                    "stroke-linecap": "round",
                },
            )
        )
    transform = (
        f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if orientation is Orientation.VERTICAL else None
    )
    return svg.element("g", {"transform": transform}, parts)


def panel_box(x: float, y: float) -> Box:
    """Bounding box of a load panel centered at (x, y)."""
    return Box(x - PANEL_WIDTH / 2, y - PANEL_HEIGHT / 2, x + PANEL_WIDTH / 2, y + PANEL_HEIGHT / 2)


def load_panel(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a breaker panel: a box with a center bus and breaker ticks either side."""
    box = panel_box(x, y)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    inner = stroke(status, theme, theme.symbol_stroke_width)
    top, bottom = box.top + 12, box.bottom - 12
    parts = [
        svg.element(
            "rect",
            {
                "x": box.left,
                "y": box.top,
                "width": PANEL_WIDTH,
                "height": PANEL_HEIGHT,
                "fill": "none",
                **outline,
            },
        ),
        svg.element("line", {"x1": x, "y1": top, "x2": x, "y2": bottom, **inner}),
    ]
    step = (bottom - top) / (PANEL_BREAKERS - 1)
    for i in range(PANEL_BREAKERS):
        yy = top + i * step
        for x1, x2 in ((x - 14, x - 4), (x + 4, x + 14)):
            parts.append(svg.element("line", {"x1": x1, "y1": yy, "x2": x2, "y2": yy, **inner}))
    return "".join(parts)
