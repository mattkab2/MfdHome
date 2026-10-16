"""Line service tags: what a line carries, the P&ID way (color is reserved for status)."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, Defs, load_page
from mfdhome.model import LineElement, LineTag, Status
from mfdhome.render import render_element
from mfdhome.themes import EINK_COLOR, LCD


def test_plate_sits_on_the_line_at_its_fraction() -> None:
    line = LineElement("hot", ((0.0, 0.0), (200.0, 0.0)), casing=True, tag=LineTag("HW"))
    svg = render_element(line, {}, LCD)
    assert '<rect x="38.8" y="-8" width="22.4" height="16"' in svg  # centered a quarter along
    assert ">HW<" in svg and f'fill="{LCD.background}"' in svg
    moved = render_element(
        LineElement("hot", ((0.0, 0.0), (200.0, 0.0)), tag=LineTag("HW", 0.9)), {}, LCD
    )
    assert '<rect x="168.8"' in moved


def test_untagged_lines_have_no_plate() -> None:
    assert "<rect" not in render_element(LineElement("l", ((0.0, 0.0), (100.0, 0.0))), {}, LCD)


def test_tag_text_is_never_pale_yellow_on_paper() -> None:
    from mfdhome.symbols.line import tag_plate

    assert 'fill="#ffff00">' not in tag_plate((0, 0), "GAS", Status.CAUTION, EINK_COLOR)


def test_config(tmp_path: Path) -> None:
    page = tmp_path / "p.yaml"
    page.write_text(
        textwrap.dedent(
            """\
            page: p
            title: P
            canvas: {width: 100, height: 100}
            elements:
              - {id: a, type: line, from: [0, 0], to: [10, 0], tag: CW}
              - {id: b, type: line, from: [0, 0], to: [10, 0], tag: {text: GAS, along: 0.8}}
            """
        )
    )
    a, b = load_page(page, Defs()).elements
    assert isinstance(a, LineElement) and a.tag == LineTag("CW")
    assert isinstance(b, LineElement) and b.tag == LineTag("GAS", 0.8)
    page.write_text(page.read_text().replace("tag: CW", "tag: STEAM"))
    with pytest.raises(ConfigError, match=r"tag\.text: String should have at most 4"):
        load_page(page, Defs())
