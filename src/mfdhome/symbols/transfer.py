"""Transfer switch and load panel symbols."""

from __future__ import annotations

from mfdhome.layout.anchors import Box
from mfdhome.layout.route import Port
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
        svg.rect(x - half_w, y - half_h, ATS_WIDTH, ATS_HEIGHT, {"fill": "none", **outline}),
        *(
            svg.circle(
                cx,
                y,
                CONTACT_RADIUS,
                {"fill": "none", "stroke": color, "stroke-width": theme.symbol_stroke_width},
            )
            for cx in (grid_x, load_x)
        ),
    ]
    if connected is not None:
        run = load_x - grid_x
        end = (grid_x, y) if connected else (grid_x + run * 0.15, y - run * OPEN_RISE)
        parts.append(
            svg.line(
                load_x,
                y,
                end[0],
                end[1],
                {**stroke(status, theme, theme.line_width), "stroke-linecap": "round"},
            )
        )
    transform = (
        f"rotate(90 {svg.fmt(x)} {svg.fmt(y)})" if orientation is Orientation.VERTICAL else None
    )
    return svg.element("g", {"transform": transform}, parts)


def panel_box(x: float, y: float) -> Box:
    """Bounding box of a load panel centered at (x, y)."""
    return Box(x - PANEL_WIDTH / 2, y - PANEL_HEIGHT / 2, x + PANEL_WIDTH / 2, y + PANEL_HEIGHT / 2)


def _breaker_rows(y: float) -> list[float]:
    """Heights of the panel's breaker ticks, top to bottom."""
    top, bottom = y - PANEL_HEIGHT / 2 + 12, y + PANEL_HEIGHT / 2 - 12
    step = (bottom - top) / (PANEL_BREAKERS - 1)
    return [top + i * step for i in range(PANEL_BREAKERS)]


def panel_breaker_ports(x: float, y: float) -> dict[str, Port]:
    """A port on the panel's edge level with each breaker tick: ``l1``-``l4`` down
    the left side and ``r1``-``r4`` down the right, so a circuit can leave from
    its own breaker."""
    ports = {}
    for i, yy in enumerate(_breaker_rows(y), start=1):
        ports[f"l{i}"] = Port((x - PANEL_WIDTH / 2, yy), (-1.0, 0.0))
        ports[f"r{i}"] = Port((x + PANEL_WIDTH / 2, yy), (1.0, 0.0))
    return ports


def load_panel(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a breaker panel: a box with a center bus and breaker ticks either side."""
    box = panel_box(x, y)
    outline = stroke(status, theme, theme.symbol_stroke_width)
    inner = stroke(status, theme, theme.symbol_stroke_width)
    rows = _breaker_rows(y)
    parts = [
        svg.rect(box.left, box.top, PANEL_WIDTH, PANEL_HEIGHT, {"fill": "none", **outline}),
        svg.line(x, rows[0], x, rows[-1], inner),
    ]
    for yy in rows:
        for x1, x2 in ((x - 14, x - 4), (x + 4, x + 14)):
            parts.append(svg.line(x1, yy, x2, yy, inner))
    return "".join(parts)
