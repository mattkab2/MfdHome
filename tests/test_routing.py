"""Auto-routing with at most one elbow, port directions and arrow placement."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, load_page
from mfdhome.layout import Elbow, Port, route
from mfdhome.model import LineElement, Orientation, Status, SymbolElement
from mfdhome.symbols import Flow, line
from mfdhome.symbols.geometry import find_port
from mfdhome.themes import LCD

RIGHT, DOWN = (1.0, 0.0), (0.0, 1.0)


@pytest.mark.parametrize(
    ("start", "end", "elbow", "expected"),
    [
        (Port((0, 0), RIGHT), Port((100, 0)), None, ((0, 0), (100, 0))),  # aligned: straight
        (Port((0, 0), RIGHT), Port((100, 50)), None, ((0, 0), (100, 0), (100, 50))),
        (Port((0, 0), DOWN), Port((100, 50)), None, ((0, 0), (0, 50), (100, 50))),
        # no start direction: last leg enters the end port head-on
        (Port((0, 0)), Port((100, 50), RIGHT), None, ((0, 0), (0, 50), (100, 50))),
        (Port((0, 0)), Port((100, 50), DOWN), None, ((0, 0), (100, 0), (100, 50))),
        (Port((0, 0)), Port((100, 50)), None, ((0, 0), (100, 0), (100, 50))),  # default
        (Port((0, 0), RIGHT), Port((100, 50)), Elbow.VERTICAL_FIRST, ((0, 0), (0, 50), (100, 50))),
    ],
)
def test_route(
    start: Port, end: Port, elbow: Elbow | None, expected: tuple[tuple[float, float], ...]
) -> None:
    assert route(start, end, elbow) == expected


def test_port_directions() -> None:
    battery = SymbolElement("b", "battery", (200, 300))
    assert find_port(battery, "right") == Port((230, 300), RIGHT)
    assert find_port(battery, "bottom") == Port((200, 350), DOWN)
    assert find_port(battery, "top-left").direction is None  # corners have no direction
    vertical = SymbolElement("br", "breaker", (0, 0), orientation=Orientation.VERTICAL)
    assert find_port(vertical, "out") == Port((0, 20), DOWN)


def page(tmp_path: Path, elements: str) -> Path:
    path = tmp_path / "p.yaml"
    body = "page: p\ntitle: P\ncanvas: {width: 1000, height: 600}\nelements:\n"
    path.write_text(body + textwrap.indent(textwrap.dedent(elements), "  "))
    return path


def test_lines_route_from_ports(tmp_path: Path) -> None:
    path = page(
        tmp_path,
        """\
        - {id: bus, type: node, at: [500, 300]}
        - {id: bat, type: battery, at: [300, 450], bind: {level: sensor.soc}}
        - {id: up, type: line, from: bat.top, to: bus}
        - {id: across, type: line, from: bat.right, to: bus}
        - {id: forced, type: line, from: bat.right, to: bus, elbow: vertical-first}
        - {id: diag, type: line, from: bat.right, to: bus, route: straight}
        - {id: bent, type: line, from: bat.right, to: bus, via: [[400, 400]]}
        """,
    )
    lines = {e.id: e.points for e in load_page(path).elements if isinstance(e, LineElement)}
    assert lines["up"] == ((300, 392), (300, 300), (500, 300))  # leaves the top going up
    assert lines["across"] == ((330, 450), (500, 450), (500, 300))
    assert lines["forced"] == ((330, 450), (330, 300), (500, 300))
    assert lines["diag"] == ((330, 450), (500, 300))
    assert lines["bent"] == ((330, 450), (400, 400), (500, 300))


def test_elbow_needs_auto_routing(tmp_path: Path) -> None:
    path = page(
        tmp_path,
        "- {id: l, type: line, from: [0, 0], to: [5, 5], via: [[1, 1]], elbow: vertical-first}\n",
    )
    with pytest.raises(ConfigError, match="'elbow' only applies to auto-routed"):
        load_page(path)


def test_arrow_sits_on_longest_leg() -> None:
    pts = ((0.0, 0.0), (200.0, 0.0), (200.0, 40.0))
    body = line(pts, Status.ACTIVE, Flow.FORWARD, LCD).body
    assert 'points="110,0 90,10 90,-10"' in body  # middle of the 200-long leg, not the bend
