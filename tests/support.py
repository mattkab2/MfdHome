"""Test helpers: fixture loading and inline HA state builders."""

from pathlib import Path
from typing import Any

from mfdhome.config import Config, load_config
from mfdhome.model import Page, StateSnapshot
from mfdhome.sources import load_fixture

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = FIXTURES / "config"


def fixture_state(name: str) -> StateSnapshot:
    """Load ``tests/fixtures/<name>.json``."""
    return load_fixture(FIXTURES / f"{name}.json")


def ha_state(entity_id: str, state: str, **attributes: Any) -> dict[str, Any]:
    """Build one HA state object for inline test snapshots."""
    return {"entity_id": entity_id, "state": state, "attributes": attributes}


def load_test_config() -> Config:
    """Load ``tests/fixtures/config``."""
    return load_config(CONFIG)


def config_page(page_id: str) -> Page:
    """One page from the test config."""
    return load_test_config().pages[page_id]
