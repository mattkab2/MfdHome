"""Test helpers: fixture loading and inline HA state builders."""

from pathlib import Path
from typing import Any

from mfdhome.model import StateSnapshot
from mfdhome.sources import load_fixture

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_state(name: str) -> StateSnapshot:
    """Load ``tests/fixtures/<name>.json``."""
    return load_fixture(FIXTURES / f"{name}.json")


def ha_state(entity_id: str, state: str, **attributes: Any) -> dict[str, Any]:
    """Build one HA state object for inline test snapshots."""
    return {"entity_id": entity_id, "state": state, "attributes": attributes}
