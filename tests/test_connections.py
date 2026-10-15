"""Attaching lines to symbols: ports, nodes, junctions and endpoint errors."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, load_page
from mfdhome.model import EntityRef, LineElement, NodeElement, Orientation, SymbolElement
from mfdhome.symbols.geometry import find_port, port_names

BATTERY = SymbolElement("bat", "battery", (200, 300), bind={"level": EntityRef("sensor.soc")})
BREAKER = SymbolElement("br", "breaker", (650, 300))
VBREAKER = SymbolElement("vb", "breaker", (100, 100), orientation=Orientation.VERTICAL)


@pytest.mark.parametrize(
    ("element", "port", "expected"),
    [
        (BATTERY, "right", (230, 300)),  # on the symbol's axis, not the nub-skewed box center
        (BATTERY, "left", (170, 300)),
        (BATTERY, "top", (200, 242)),  # top of the terminal nub
        (BATTERY, "bottom", (200, 350)),
        (BATTERY, "top-left", (170, 242)),
        (BATTERY, "center-right", (230, 300)),
        (BREAKER, "in", (630, 300)),
        (BREAKER, "out", (670, 300)),
        (VBREAKER, "in", (100, 80)),
        (VBREAKER, "out", (100, 120)),
        (NodeElement("n", (5, 6)), None, (5, 6)),
    ],
)
def test_port_points(
    element: SymbolElement, port: str | None, expected: tuple[float, float]
) -> None:
    assert find_port(element, port).point == expected


def test_port_errors() -> None:
    with pytest.raises(ValueError, match="needs a port: in, out, top-left"):
        find_port(BREAKER, None)
    with pytest.raises(ValueError, match="unknown port 'center'"):
        find_port(BATTERY, "center")
    with pytest.raises(ValueError, match="unknown port 'side'"):
        find_port(BATTERY, "side")
    with pytest.raises(ValueError, match="has no ports"):
        find_port(NodeElement("n", (0, 0)), "left")
    assert "center" not in port_names(BATTERY)


def page(tmp_path: Path, elements: str) -> Path:
    path = tmp_path / "p.yaml"
    body = "page: p\ntitle: P\ncanvas: {width: 1000, height: 600}\nelements:\n"
    path.write_text(body + textwrap.indent(textwrap.dedent(elements), "  "))
    return path


def test_endpoints_resolve_including_forward_references(tmp_path: Path) -> None:
    path = page(
        tmp_path,
        """\
        - {id: feed, type: line, from: bus, via: [[400, 200]], to: bat.right}
        - {id: a, type: line, from: bus, to: [500, 500]}
        - {id: b, type: line, from: [500, 80], to: bus}
        - {id: bus, type: node, at: [500, 300]}
        - {id: bat, type: battery, at: [200, 300], bind: {level: sensor.soc}}
        - {id: lone, type: node, at: [10, 10]}
        - {id: two, type: line, from: lone, to: [20, 20]}
        """,
    )
    elements = {e.id: e for e in load_page(path).elements}
    feed = elements["feed"]
    assert isinstance(feed, LineElement)
    assert feed.points == ((500, 300), (400, 200), (230, 300))
    assert elements["bus"] == NodeElement("bus", (500, 300), junction=True)  # 3 lines
    assert elements["lone"] == NodeElement("lone", (10, 10), junction=False)  # 1 line


def test_endpoint_errors(tmp_path: Path) -> None:
    path = page(
        tmp_path,
        """\
        - {id: bus, type: node, at: [0, 0]}
        - {id: bat, type: battery, at: [200, 300], bind: {level: sensor.soc}}
        - {id: t, type: text, at: [0, 0], text: X}
        - {id: l1, type: line, from: nowhere, to: bus}
        - {id: l2, type: line, from: bat, to: bat.side}
        - {id: l3, type: line, from: bus.left, to: t.right}
        - {id: l4, type: line, points: [[0, 0], [1, 1]]}
        - {id: l5, type: line, from: bus}
        """,
    )
    with pytest.raises(ConfigError) as info:
        load_page(path)
    msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
    assert "elements[3].from: unknown element 'nowhere'; use a node id or 'element.port'" in msgs
    assert any(m.startswith("elements[4].from: connecting to 'bat' needs a port:") for m in msgs)
    assert any(m.startswith("elements[4].to: unknown port 'side' on 'bat'") for m in msgs)
    assert "elements[5].from: node 'bus' has no ports; connect to 'bus'" in msgs
    assert "elements[5].to: 't' cannot be connected to" in msgs
    assert "elements[6].points: Extra inputs are not permitted" in msgs  # use from/via/to
    assert any("a line needs both 'from' and 'to'" in m for m in msgs)
