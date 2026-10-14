"""Line style resolution and loading."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.config import ConfigError, load_defs, load_page
from mfdhome.model import LineElement, LineLook, LineStyle
from mfdhome.render import render_element
from mfdhome.render.lines import ResolvedLook, resolve_look
from mfdhome.themes import EINK_MONO, LCD, MIRROR, Theme

BUS = LineStyle("bus", LineLook(2.0, None), {"mirror": LineLook(1.25, None)})
SIGNAL = LineStyle("signal", LineLook(0.5, False))


DEFAULT_STYLE = LineStyle()
NO_LOOK = LineLook()


def line(style: LineStyle = DEFAULT_STYLE, look: LineLook = NO_LOOK) -> LineElement:
    return LineElement("l", ((0, 0), (100, 0)), style=style, look=look)


@pytest.mark.parametrize(
    ("element", "theme", "expected"),
    [
        (line(), LCD, ResolvedLook(1.0, True)),  # casing is the default
        (line(BUS), LCD, ResolvedLook(2.0, True)),
        (line(BUS), MIRROR, ResolvedLook(1.25, True)),  # per-theme variant
        (line(BUS, LineLook(1.5, None)), LCD, ResolvedLook(3.0, True)),  # element multiplies
        (line(BUS, LineLook(2.0, None)), LCD, ResolvedLook(3.0, True)),  # LCD caps at 3
        (line(BUS, LineLook(2.0, None)), MIRROR, ResolvedLook(2.0, True)),  # mirror caps at 2
        (line(SIGNAL), LCD, ResolvedLook(0.5, False)),
        (line(SIGNAL, LineLook(None, True)), LCD, ResolvedLook(0.5, True)),  # element casing wins
    ],
)
def test_resolve_look(element: LineElement, theme: Theme, expected: ResolvedLook) -> None:
    assert resolve_look(element, theme) == expected


def test_theme_policy_can_forbid_casing() -> None:
    from dataclasses import replace

    no_casing = replace(EINK_MONO, casing_allowed=False)
    assert resolve_look(line(BUS), no_casing) == ResolvedLook(2.0, False)


def test_rendered_line_puts_casing_in_underlay() -> None:
    svg = render_element(line(), {}, LCD)
    assert svg.startswith('<g data-for="l"><polyline')
    assert '<g id="l">' in svg


def write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body))
    return path


def test_load_styles_and_errors(tmp_path: Path) -> None:
    defs = load_defs(
        write(
            tmp_path / "defs.yaml",
            "line_styles:\n  bus: {weight: 2, themes: {mirror: {weight: 1.25}}}\n",
        )
    )
    assert defs.line_styles["bus"] == BUS
    page = write(
        tmp_path / "p.yaml",
        """\
        page: p
        title: P
        canvas: {width: 10, height: 10}
        elements:
          - {id: a, type: line, points: [[0, 0], [1, 0]], style: bus, weight: 1.5, casing: false}
          - {id: b, type: line, points: [[0, 0], [1, 0]], style: nope}
          - {id: c, type: line, points: [[0, 0], [1, 0]], weight: 0}
          - {id: d, type: line, points: [[0, 0], [1, 0]], color: red}
        """,
    )
    with pytest.raises(ConfigError) as info:
        load_page(page, defs)
    msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
    assert "elements[1].style: unknown line style 'nope'; expected: bus" in msgs
    assert any(m.startswith("elements[2].weight: Input should be greater than 0") for m in msgs)
    assert "elements[3].color: Extra inputs are not permitted" in msgs


def test_style_patterns_and_unknown_themes_rejected(tmp_path: Path) -> None:
    path = write(
        tmp_path / "defs.yaml",
        "line_styles:\n  x: {pattern: dashed, themes: {plasma: {weight: 2}}}\n",
    )
    with pytest.raises(ConfigError) as info:
        load_defs(path)
    msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
    assert "line_styles.x.pattern: Extra inputs are not permitted" in msgs


def test_unknown_theme_in_variant(tmp_path: Path) -> None:
    path = write(tmp_path / "defs.yaml", "line_styles:\n  x: {themes: {plasma: {weight: 2}}}\n")
    with pytest.raises(
        ConfigError, match="unknown theme 'plasma'; expected: lcd, mirror, eink_mono"
    ):
        load_defs(path)
