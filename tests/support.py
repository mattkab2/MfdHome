"""Test helpers: fixture loading, inline HA state builders and alert boards."""

from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from PIL import Image

from mfdhome.config import Config, load_config
from mfdhome.mfd import (
    EMPTY_BOARD,
    Board,
    Pending,
    acknowledge,
    apply_holds,
    evaluate_alerts,
    step,
)
from mfdhome.model import Page, StateSnapshot
from mfdhome.render.alerts import AlertView
from mfdhome.sources import load_fixture

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = FIXTURES / "config"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def fixture_state(name: str) -> StateSnapshot:
    """Load ``tests/fixtures/<name>.json``."""
    return load_fixture(FIXTURES / f"{name}.json")


def ha_state(entity_id: str, state: str, **attributes: Any) -> dict[str, Any]:
    """Build one HA state object for inline test snapshots."""
    return {"entity_id": entity_id, "state": state, "attributes": attributes}


@cache
def load_test_config() -> Config:
    """Load ``tests/fixtures/config`` (once: configs are never modified)."""
    return load_config(CONFIG)


def config_page(page_id: str) -> Page:
    """One page from the test config."""
    return load_test_config().pages[page_id]


def board_from(*fixtures: str, acks: tuple[str, ...] = ()) -> Board:
    """Step the test config's alerts through ``fixtures`` in order, a minute apart.

    ``acks`` are acknowledged after the first fixture.
    """
    alerts = load_test_config().alerts.alerts
    board = EMPTY_BOARD
    pending: Pending = {}
    for i, name in enumerate(fixtures):
        now = T0 + timedelta(minutes=i)
        raised = evaluate_alerts(alerts, fixture_state(name))
        raised, pending = apply_holds(alerts, raised, board, pending, now)  # as the runtime does
        board = step(board, alerts, raised, now)
        if i == 0 and acks:
            board = acknowledge(board, "workshop", T0 + timedelta(seconds=30), ids=acks)
    return board


def view(board: Board) -> AlertView:
    """The test config's alerts over ``board``."""
    config = load_test_config()
    return AlertView(config.alerts.alerts, config.alerts.systems, board)


def image_colors(image: Image.Image) -> frozenset[str]:
    """Every distinct color in ``image``, as ``#rrggbb``."""
    data = image.convert("RGB").tobytes()
    return frozenset(f"#{data[i : i + 3].hex()}" for i in range(0, len(data), 3))
