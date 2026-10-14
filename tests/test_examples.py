"""Keep the example config loadable and renderable."""

from pathlib import Path

import pytest

from mfdhome.config import load_config
from mfdhome.render import render_page
from mfdhome.themes import DARK, Target
from tests.support import fixture_state

EXAMPLES = Path(__file__).parent.parent / "examples" / "config"


@pytest.mark.parametrize(
    "fixture", ["electrical_normal", "electrical_export", "electrical_unavailable"]
)
def test_example_config_renders(fixture: str) -> None:
    config = load_config(EXAMPLES)
    assert "electrical" in config.pages
    for page in config.pages.values():
        svg = render_page(page, fixture_state(fixture), DARK, Target("tablet", 1280, 768))
        assert svg.startswith("<svg ")
