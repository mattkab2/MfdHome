"""Line casing: hollow pipes by default, plain lines with ``casing: false``."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, Defs, load_page
from mfdhome.model import LineElement
from mfdhome.render import render_element
from mfdhome.themes import LCD, MIRROR


def test_cased_by_default_with_the_casing_underneath() -> None:
    svg = render_element(LineElement("l", ((0, 0), (100, 0))), {}, LCD)
    assert svg.startswith('<g data-for="l"><polyline')
    assert f'stroke-width="{LCD.casing_width:g}"' in svg and '<g id="l">' in svg


def test_plain_line_is_one_stroke_at_the_theme_width() -> None:
    for theme in (LCD, MIRROR):
        svg = render_element(LineElement("l", ((0, 0), (100, 0)), casing=False), {}, theme)
        assert "data-for" not in svg and svg.count("<polyline") == 1
        assert f'stroke-width="{theme.line_width:g}"' in svg


def test_config(tmp_path: Path) -> None:
    page = tmp_path / "p.yaml"
    page.write_text(
        textwrap.dedent(
            """\
            page: p
            title: P
            canvas: {width: 10, height: 10}
            elements:
              - {id: a, type: line, from: [0, 0], to: [1, 0]}
              - {id: b, type: line, from: [0, 0], to: [1, 0], casing: false}
            """
        )
    )
    a, b = load_page(page, Defs()).elements
    assert isinstance(a, LineElement) and a.casing
    assert isinstance(b, LineElement) and not b.casing
    page.write_text(
        page.read_text()
        + "  - {id: c, type: line, from: [0, 0], to: [1, 0], style: bus}\n"
        + "  - {id: d, type: line, from: [0, 0], to: [1, 0], weight: 2}\n"
        + "  - {id: e, type: line, from: [0, 0], to: [1, 0], color: red}\n"
    )
    with pytest.raises(ConfigError) as info:
        load_page(page, Defs())
    msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
    for i, key in ((2, "style"), (3, "weight"), (4, "color")):
        assert f"elements[{i}].{key}: Extra inputs are not permitted" in msgs
