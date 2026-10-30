"""Enclosures: a frame sized to its members, which keep their own places and lines."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, load_page
from mfdhome.model import EnclosureElement, Page, Status, snapshot_from_ha_states
from mfdhome.render import render_page
from mfdhome.symbols.geometry import element_box
from mfdhome.themes import LCD, Target
from tests.support import ha_state

HEADER = "page: p\ntitle: P\ncanvas: {width: 1000, height: 600}\nelements:\n"

CABINET = """\
- {id: relay, type: breaker, at: [100, 100], bind: {state: switch.a},
   status: {map: {"on": normal}, default: caution}}
- {id: other, type: breaker, at: [100, 160], bind: {state: switch.b},
   status: {map: {"on": normal}, default: caution}}
- {id: feed, type: line, from: [0, 100], to: relay.in, bind: {state: switch.a}}
- {id: gateway, type: enclosure, contains: [relay, other], padding: 10, name: GATEWAY}
"""


def page(tmp_path: Path, elements: str) -> Path:
    path = tmp_path / "p.yaml"
    path.write_text(HEADER + textwrap.indent(textwrap.dedent(elements), "  "))
    return path


def errors(path: Path) -> list[str]:
    with pytest.raises(ConfigError) as info:
        load_page(path)
    return [f"{i.loc}: {i.message}" for i in info.value.issues]


def enclosure(loaded: Page) -> EnclosureElement:
    [found] = [e for e in loaded.elements if isinstance(e, EnclosureElement)]
    return found


def render(loaded: Page, a: str | None, b: str | None) -> str:
    states = [ha_state(e, s) for e, s in (("switch.a", a), ("switch.b", b)) if s is not None]
    return render_page(loaded, snapshot_from_ha_states(states), LCD, Target("t", 1000, 600))


def frame(svg: str) -> str:
    start = svg.index('<g id="gateway">')
    return svg[start : svg.index("</g>", start)]


def test_frame_wraps_the_members_plus_padding(tmp_path: Path) -> None:
    loaded = load_page(page(tmp_path, CABINET))
    boxes = [element_box(e) for e in loaded.elements if e.id in ("relay", "other")]
    left = min(b.left for b in boxes if b) - 10
    top = min(b.top for b in boxes if b) - 10
    found = enclosure(loaded)
    assert found.members == ("relay", "other")
    assert found.at == (left, top)
    assert found.size == (
        max(b.right for b in boxes if b) + 10 - left,
        max(b.bottom for b in boxes if b) + 10 - top,
    )


def test_status_is_the_members_worst(tmp_path: Path) -> None:
    loaded = load_page(page(tmp_path, CABINET))
    calm = frame(render(loaded, "on", "on"))
    assert f'stroke="{LCD.structure_color}"' in calm and ">GATEWAY<" in calm
    assert f'stroke="{LCD.color(Status.CAUTION)}"' in frame(render(loaded, "on", "off"))
    # unavailable only when every member is
    assert "stroke-dasharray" not in frame(render(loaded, None, "on"))
    gone = frame(render(loaded, None, None))
    assert f'stroke="{LCD.color(Status.UNAVAILABLE)}"' in gone and "stroke-dasharray" in gone


def test_frame_is_drawn_beneath_the_pipes(tmp_path: Path) -> None:
    svg = render(load_page(page(tmp_path, CABINET)), "on", "on")
    assert svg.index('<g id="gateway">') < svg.index('<g id="casings">')


def test_members_must_be_boxed_top_level_elements(tmp_path: Path) -> None:
    outer = "- {id: outer, type: enclosure, contains: [gateway, feed, nowhere]}\n"
    assert errors(page(tmp_path, CABINET + outer)) == [
        "elements[4].contains[0]: 'gateway' can't be enclosed: enclose symbols, groups, tiles "
        "or nodes",
        "elements[4].contains[1]: 'feed' can't be enclosed: enclose symbols, groups, tiles "
        "or nodes",
        "elements[4].contains[2]: unknown element 'nowhere'",
    ]


def test_lines_attach_to_members_not_the_enclosure(tmp_path: Path) -> None:
    path = page(tmp_path, CABINET + "- {id: stray, type: line, from: [0, 300], to: gateway.left}\n")
    assert errors(path) == [
        "elements[4].to: enclosure 'gateway' has no ports; connect to the elements inside it"
    ]
