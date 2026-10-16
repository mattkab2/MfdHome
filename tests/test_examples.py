"""Keep the example config loadable and renderable."""

from datetime import timedelta
from pathlib import Path

import pytest

from mfdhome.config import load_config
from mfdhome.config.inventory import entity_uses
from mfdhome.config.load import load_scenario
from mfdhome.mfd import evaluate_alerts
from mfdhome.render import render_page
from mfdhome.sources.scenario import state_at
from mfdhome.themes import LCD, Target
from tests.support import fixture_state

EXAMPLES = Path(__file__).parent.parent / "examples" / "config"


@pytest.mark.parametrize(
    "fixture",
    ["electrical_normal", "electrical_export", "electrical_unavailable", "electrical_islanded"],
)
def test_example_config_renders(fixture: str) -> None:
    config = load_config(EXAMPLES)
    assert "electrical" in config.pages
    for page in config.pages.values():
        svg = render_page(page, fixture_state(fixture), LCD, Target("tablet", 1280, 768))
        assert svg.startswith("<svg ")


SCENARIOS = EXAMPLES.parent / "scenarios"


@pytest.mark.parametrize("path", sorted(SCENARIOS.glob("*.yaml")), ids=lambda p: p.stem)
def test_example_scenarios_cover_the_example_config(path: Path) -> None:
    """Every entity the example config uses is in the scenario's starting states,
    and the house starts quiet (no alert raised before the first step)."""
    config = load_config(EXAMPLES)
    scenario = load_scenario(path)
    assert set(entity_uses(config)) <= set(scenario.base)
    quiet, _ = state_at(scenario, timedelta(0))
    assert evaluate_alerts(config.alerts.alerts, quiet) == frozenset()
