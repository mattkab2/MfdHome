"""Displays taller than their pages (a 4:3 e-paper panel for 5:3 pages): the canvas
grows, the page keeps the top, an annunciator band fills the space below it and the
bottom strip moves to the display's bottom. Also the grayscale e-paper theme."""

import io
import re
from pathlib import Path

import pytest
from PIL import Image
from syrupy.assertion import SnapshotAssertion

from mfdhome.config import ConfigError
from mfdhome.config.load import load_displays
from mfdhome.model import Page, TileElement
from mfdhome.render import render_page
from mfdhome.render.controls import Controls
from mfdhome.render.page import band_tiles, canvas_height
from mfdhome.render.panels import GRAY16, PANELS
from mfdhome.render.raster import rasterize
from mfdhome.themes import EINK_GRAY, LCD, Target
from tests.support import board_from, config_page, fixture_state, image_colors, view

PAGE = Page("p", "P", 1000, 600)
E1003 = Target("e1003", 1872, 1404)  # 4:3
SYSTEMS = ["GRID", "BATT", "WATER", "LEAK", "HVAC", "NET", "SEC", "FIRE", "WX"]


class TestCanvas:
    def test_a_taller_display_grows_the_canvas(self) -> None:
        assert canvas_height(PAGE, E1003) == 750
        assert canvas_height(PAGE, Target("t", 1280, 800)) == 600  # 25 extra: letterboxed
        assert canvas_height(PAGE, Target("t", 1920, 1080)) == 600  # wider: pillarboxed
        assert canvas_height(PAGE, Target("t", 1000, 600)) == 600

    def test_band_rows_of_five_centered_between_page_and_strip(self) -> None:
        tiles = band_tiles(PAGE, 750, SYSTEMS)
        assert [t.system for t in tiles] == SYSTEMS  # two rows fit in the 150-unit band
        rows = sorted({t.at[1] for t in tiles})
        assert rows == [599.0, 671.0]  # centered on 635, rings clear of 560 and 710
        first_row = [t.at[0] for t in tiles if t.at[1] == 599.0]
        assert first_row == [132.0, 316.0, 500.0, 684.0, 868.0]  # 160 wide, 24 apart, centered
        assert len(band_tiles(PAGE, 750, [*SYSTEMS, "X", "Y"])) == 10  # the rest don't fit

    def test_no_band_on_a_page_with_tiles_or_without_room(self) -> None:
        status = Page("s", "S", 1000, 600, (TileElement("t", (500, 300), "GRID"),))
        assert band_tiles(status, 750, SYSTEMS) == []
        assert band_tiles(PAGE, 600, SYSTEMS) == []

    def test_rendered_band_and_strip_at_the_bottom(self) -> None:
        board = board_from("electrical_islanded")
        controls = Controls()
        svg = render_page(
            config_page("electrical"),
            fixture_state("electrical_islanded"),
            LCD,
            E1003,
            view(board),
            controls,
            annunciator=SYSTEMS,
        )
        assert 'viewBox="0 0 1000 750"' in svg
        band = svg[svg.index('<g id="annunciator">') : svg.index('<g id="banner">')]
        assert band.count('width="160" height="64"') >= 9 and ">GRID<" in band
        assert re.search(r'<g id="banner"><g class="attn"><rect x="\d+" y="710"', svg)

    def test_displays_choose_their_systems(self, tmp_path: Path) -> None:
        path = tmp_path / "displays.yaml"
        path.write_text(
            "displays:\n"
            "  panel: {theme: eink_gray, size: [1872, 1404], home: s, panel: gray16,\n"
            "          annunciator: [NET, GRID]}\n"
            "  tablet: {theme: lcd, size: [1280, 800], home: s}\n"
        )
        displays = load_displays(path, {"s"}, ("GRID", "BATT", "NET"))
        assert displays["panel"].annunciator == ("NET", "GRID")
        assert displays["tablet"].annunciator == ("GRID", "BATT", "NET")  # default: every one
        path.write_text(
            "displays:\n  panel: {theme: lcd, size: [1872, 1404], home: s, annunciator: [FOO]}\n"
        )
        with pytest.raises(ConfigError, match="unknown system 'FOO'"):
            load_displays(path, {"s"}, ("GRID",))


class TestGrayTheme:
    def test_only_on_panels_with_grays(self, tmp_path: Path) -> None:
        assert not PANELS["gray4"].unsupported(EINK_GRAY)
        assert not PANELS["gray16"].unsupported(EINK_GRAY)
        path = tmp_path / "displays.yaml"
        path.write_text(
            "displays:\n  p: {theme: eink_gray, size: [800, 480], home: s, panel: mono}\n"
        )
        with pytest.raises(ConfigError, match="mono"):
            load_displays(path, {"s"})

    def test_structure_recedes_in_gray(self) -> None:
        svg = render_page(config_page("security"), {}, EINK_GRAY, E1003)
        assert 'stroke="#555555"' in svg  # walls and rooms
        assert set(re.findall(r"#[0-9a-fA-F]{6}", svg)) <= EINK_GRAY.palette()


def test_e1003_snapshot(svg_snapshot: SnapshotAssertion, png_snapshot: SnapshotAssertion) -> None:
    """The Electrical page on a 10.3-inch 16-gray panel, islanded, with the band."""
    board = board_from("electrical_islanded")
    svg = render_page(
        config_page("electrical"),
        fixture_state("electrical_islanded"),
        EINK_GRAY,
        E1003,
        view(board),
        Controls(),
        "AVG 5M\nAS OF 14:05",
        annunciator=SYSTEMS,
    )
    assert svg == svg_snapshot
    png = rasterize(svg, GRAY16, EINK_GRAY.background)
    image = Image.open(io.BytesIO(png))
    assert image.size == (1872, 1404)
    assert image_colors(image) <= set(GRAY16.colors)
    assert png == png_snapshot
