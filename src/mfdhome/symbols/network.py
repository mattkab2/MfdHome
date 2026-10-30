"""Network symbols: router, switch, access point, host and radio.

Abstract boxes in the P&ID manner, told apart by a small mark: the router's
crossed routes, the switch's row of ports, the access point's Wi-Fi arcs, the
host's drive bays and the radio's antenna mast. Only the outlines take the
status weight; the fine marks inside keep theirs, so they stay legible.

Each is centered on its body; the access point's arcs and the radio's mast
reach above it, so lines attach level with the body and names clear the marks.
A router can break out its ports: a numbered socket for the WAN on its left
edge and one for each LAN port down its right edge, so every device on the
gateway gets its own line.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from mfdhome.layout.anchors import Box
from mfdhome.layout.route import Port
from mfdhome.model.binding import Status
from mfdhome.symbols import svg
from mfdhome.symbols.style import detail, stroke, text_at
from mfdhome.themes.theme import Theme

ROUTER_WIDTH, ROUTER_HEIGHT = 60.0, 40.0
ROUTE_RADIUS = 13.0  # the circle of crossed routes
CHEVRON = 4.0  # half-width of the arrowheads on the routes
LAN_PITCH = 20.0  # between broken-out LAN ports: room for a pipe each
LAN_MARGIN = 8.0  # from the box's top and bottom to the first and last port
SOCKET_COLUMN = 16.0  # added width for a column of numbered sockets
SOCKET = 6.0  # a socket's square, on the edge
SOCKET_NUMBER_SCALE = 0.6  # socket numbers relative to the theme's font size

SWITCH_WIDTH, SWITCH_HEIGHT = 84.0, 28.0
SWITCH_PORTS = 8
PORT_SIZE, PORT_GAP = 6.0, 3.0

AP_WIDTH, AP_HEIGHT = 44.0, 16.0
ARC_RADII = (7.0, 13.0)  # Wi-Fi arcs above the body, from its top center
ARC_SPAN = 50.0  # degrees either side of straight up
ARC_GAP = 3.0  # between the body and the arcs' center

HOST_WIDTH, HOST_HEIGHT = 48.0, 44.0
HOST_BAYS = 3
LED_RADIUS = 2.0

RADIO_WIDTH, RADIO_HEIGHT = 32.0, 20.0
MAST_HEIGHT = 16.0
ANTENNA_WIDTH, ANTENNA_HEIGHT = 18.0, 10.0  # the inverted triangle atop the mast


def _body(x: float, y: float, width: float, height: float, status: Status, theme: Theme) -> str:
    return svg.rect(
        x - width / 2,
        y - height / 2,
        width,
        height,
        {"rx": 3, "fill": "none", **stroke(status, theme, theme.symbol_stroke_width)},
    )


def _centered(x: float, y: float, width: float, height: float, above: float = 0.0) -> Box:
    return Box(x - width / 2, y - height / 2 - above, x + width / 2, y + height / 2)


def _router_size(lan: int, wan: bool) -> tuple[float, float]:
    """Width and height: wider by a column for the LAN ports (right) and the WAN
    socket (left), taller to fit the LAN ports."""
    width = ROUTER_WIDTH + (SOCKET_COLUMN if lan else 0.0) + (SOCKET_COLUMN if wan else 0.0)
    height = max(ROUTER_HEIGHT, (lan - 1) * LAN_PITCH + 2 * LAN_MARGIN) if lan else ROUTER_HEIGHT
    return width, height


def router_box(x: float, y: float, lan: int = 0, wan: bool = False) -> Box:
    """Bounding box of a router centered at (x, y), with ``lan`` ports broken out and
    a numbered ``wan`` socket."""
    return _centered(x, y, *_router_size(lan, wan))


def router_ports(x: float, y: float, lan: Sequence[int], wan: int | None) -> dict[str, Port]:
    """The numbered sockets' ports: ``wan`` in the middle of the left edge pointing
    left, and the LAN ports (``lan1``, ``lan7``, ...) down the right edge in the
    order given, pointing right."""
    width, _ = _router_size(len(lan), wan is not None)
    top = y - (len(lan) - 1) * LAN_PITCH / 2
    ports = {} if wan is None else {"wan": Port((x - width / 2, y), (-1.0, 0.0))}
    for i, n in enumerate(lan):
        ports[f"lan{n}"] = Port((x + width / 2, top + i * LAN_PITCH), (1.0, 0.0))
    return ports


def router(
    x: float,
    y: float,
    status: Status,
    theme: Theme,
    lan: Sequence[int] = (),
    wan: int | None = None,
) -> str:
    """Render a router (a gateway): a box holding a circle crossed by four routes,
    each ending in an outward chevron, with any numbered sockets on its edges
    (the WAN on the left, LAN ports down the right), each a square with its
    number beside it."""
    marks = detail(status, theme, theme.symbol_stroke_width)
    r, c = ROUTE_RADIUS, CHEVRON
    width, height = _router_size(len(lan), wan is not None)
    parts = [_body(x, y, width, height, status, theme)]
    sockets = detail(status, theme, theme.symbol_stroke_width * 0.75)
    for name, port in router_ports(x, y, lan, wan).items():
        px, py = port.point
        inward = 1.0 if name == "wan" else -1.0  # the WAN is on the left edge
        square = px if inward > 0 else px - SOCKET
        parts.append(svg.rect(square, py - SOCKET / 2, SOCKET, SOCKET, {"fill": "none", **sockets}))
        number = str(wan) if name == "wan" else name.removeprefix("lan")
        parts.append(
            text_at(
                px + inward * (SOCKET + 6),
                py,
                number,
                theme,
                theme.font_size * SOCKET_NUMBER_SCALE,
                theme.text_in(status),
            )
        )
    # The routes keep to the middle, clear of the socket columns.
    cx = x + ((SOCKET_COLUMN if wan is not None else 0.0) - (SOCKET_COLUMN if lan else 0.0)) / 2
    parts.append(svg.circle(cx, y, r, {"fill": "none", **marks}))
    inner = r - 3.0  # the routes stop short of the circle, chevrons inside it
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip = (cx + dx * inner, y + dy * inner)
        back = (tip[0] - dx * c, tip[1] - dy * c)
        wings = [(back[0] + dy * c, back[1] + dx * c), tip, (back[0] - dy * c, back[1] - dx * c)]
        parts.append(svg.line(cx, y, tip[0], tip[1], marks))
        parts.append(svg.polyline(wings, {"fill": "none", "stroke-linejoin": "round", **marks}))
    return "".join(parts)


def switch_box(x: float, y: float) -> Box:
    """Bounding box of a network switch centered at (x, y)."""
    return _centered(x, y, SWITCH_WIDTH, SWITCH_HEIGHT)


def network_switch(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a network switch: a long box with a row of ports along its middle."""
    row = SWITCH_PORTS * PORT_SIZE + (SWITCH_PORTS - 1) * PORT_GAP
    left = x - row / 2
    ports = detail(status, theme, theme.symbol_stroke_width * 0.75)
    parts = [_body(x, y, SWITCH_WIDTH, SWITCH_HEIGHT, status, theme)]
    for i in range(SWITCH_PORTS):
        parts.append(
            svg.rect(
                left + i * (PORT_SIZE + PORT_GAP),
                y - PORT_SIZE / 2,
                PORT_SIZE,
                PORT_SIZE,
                {"fill": "none", **ports},
            )
        )
    return "".join(parts)


def ap_box(x: float, y: float) -> Box:
    """Bounding box of an access point whose body is centered at (x, y), arcs included."""
    return _centered(x, y, AP_WIDTH, AP_HEIGHT, above=ARC_GAP + ARC_RADII[-1])


def access_point(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a Wi-Fi access point: a flat body with radio arcs rising from it."""
    arcs = detail(status, theme, theme.symbol_stroke_width)
    cx, cy = x, y - AP_HEIGHT / 2 - ARC_GAP
    span = math.radians(ARC_SPAN)
    parts = [
        _body(x, y, AP_WIDTH, AP_HEIGHT, status, theme),
        svg.circle(cx, cy, 1.5, {"fill": theme.color(status), "stroke": "none"}),
    ]
    for r in ARC_RADII:
        dx, dy = r * math.sin(span), r * math.cos(span)
        d = (
            f"M {svg.fmt(cx - dx)} {svg.fmt(cy - dy)} "
            f"A {svg.fmt(r)} {svg.fmt(r)} 0 0 1 {svg.fmt(cx + dx)} {svg.fmt(cy - dy)}"
        )
        parts.append(
            svg.element("path", {"d": d, "fill": "none", "stroke-linecap": "round", **arcs})
        )
    return "".join(parts)


def host_box(x: float, y: float) -> Box:
    """Bounding box of a host (a server) centered at (x, y)."""
    return _centered(x, y, HOST_WIDTH, HOST_HEIGHT)


def host(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a host, such as the Home Assistant server: a box of stacked drive bays,
    each with an indicator dot."""
    marks = detail(status, theme, theme.symbol_stroke_width)
    top = y - HOST_HEIGHT / 2
    bay = HOST_HEIGHT / HOST_BAYS
    left, right = x - HOST_WIDTH / 2, x + HOST_WIDTH / 2
    parts = [_body(x, y, HOST_WIDTH, HOST_HEIGHT, status, theme)]
    for i in range(HOST_BAYS):
        if i:
            yy = top + i * bay
            parts.append(svg.line(left, yy, right, yy, marks))
        mid = top + (i + 0.5) * bay
        parts.append(svg.line(left + 6, mid, right - 14, mid, marks))
        parts.append(
            svg.circle(right - 7, mid, LED_RADIUS, {"fill": theme.color(status), "stroke": "none"})
        )
    return "".join(parts)


def radio_box(x: float, y: float) -> Box:
    """Bounding box of a radio whose body is centered at (x, y), antenna included."""
    return _centered(x, y, RADIO_WIDTH, RADIO_HEIGHT, above=MAST_HEIGHT + ANTENNA_HEIGHT)


def radio(x: float, y: float, status: Status, theme: Theme) -> str:
    """Render a radio node (a LoRa companion or repeater): a box with an antenna mast
    topped by the schematic antenna, an inverted triangle."""
    outline = stroke(status, theme, theme.symbol_stroke_width)
    body_top = y - RADIO_HEIGHT / 2
    mast_top = body_top - MAST_HEIGHT
    top = mast_top - ANTENNA_HEIGHT
    half = ANTENNA_WIDTH / 2
    antenna = [(x - half, top), (x + half, top), (x, mast_top)]
    return "".join(
        [
            _body(x, y, RADIO_WIDTH, RADIO_HEIGHT, status, theme),
            svg.line(x, body_top, x, mast_top, outline),
            svg.polygon(antenna, {"fill": "none", "stroke-linejoin": "round", **outline}),
        ]
    )
