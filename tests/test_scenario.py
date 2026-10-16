"""Scenarios and static sources: developing without Home Assistant."""

import asyncio
import textwrap
from datetime import timedelta
from pathlib import Path

import pytest

from mfdhome.config import ConfigError
from mfdhome.config.load import load_scenario
from mfdhome.model import EntityState
from mfdhome.sources.scenario import Scenario, ScenarioSource, StaticSource, Step, state_at
from tests.support import FIXTURES

S = timedelta(seconds=1)
SCENARIO = Scenario(
    base={"sensor.a": EntityState("1")},
    steps=(
        Step(10 * S, {"sensor.a": EntityState("2"), "sensor.b": EntityState("x")}),
        Step(20 * S, remove=frozenset({"sensor.b"}), connected=False),
        Step(30 * S, connected=True),
    ),
    loop=40 * S,
)


def values(seconds: float) -> tuple[dict[str, str], bool]:
    states, connected = state_at(SCENARIO, seconds * S)
    return {k: v.state for k, v in states.items()}, connected


def test_state_at_applies_steps_up_to_the_time() -> None:
    assert values(0) == ({"sensor.a": "1"}, True)
    assert values(10) == ({"sensor.a": "2", "sensor.b": "x"}, True)
    assert values(25) == ({"sensor.a": "2"}, False)
    assert values(35) == ({"sensor.a": "2"}, True)
    assert values(45) == values(5)  # looped


def test_load_scenario(tmp_path: Path) -> None:
    (tmp_path / "base.json").write_text((FIXTURES / "electrical_normal.json").read_text())
    path = tmp_path / "s.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            states: base.json
            loop: 2m
            steps:
              - at: 30s
                set:
                  binary_sensor.grid_connected: "off"
                  sensor.grid_power: {state: "0", attributes: {unit_of_measurement: W}}
              - {at: 10s, connected: false}
              - {at: 1m, remove: [sensor.grid_power]}
            """
        )
    )
    scenario = load_scenario(path)
    assert scenario.loop == 120 * S
    assert [s.at for s in scenario.steps] == [10 * S, 30 * S, 60 * S]  # sorted
    assert scenario.base["binary_sensor.grid_connected"].state == "on"
    grid = scenario.steps[1].set["sensor.grid_power"]
    assert (grid.state, grid.attributes) == ("0", {"unit_of_measurement": "W"})


def test_scenario_errors(tmp_path: Path) -> None:
    path = tmp_path / "s.yaml"
    path.write_text("states: missing.json\n")
    with pytest.raises(ConfigError, match="cannot read"):
        load_scenario(path)
    path.write_text("steps:\n  - {at: soon, set: {sensor.x: 1}}\n")
    with pytest.raises(ConfigError, match=r"steps\[0\]\.at"):
        load_scenario(path)


async def test_scenario_source_replays_in_real_time() -> None:
    quick = Scenario(
        base={"sensor.a": EntityState("1")},
        steps=(
            Step(timedelta(milliseconds=20), {"sensor.a": EntityState("2")}),
            Step(timedelta(milliseconds=40), connected=False),
        ),
    )
    source = ScenarioSource(quick)
    seen: list[tuple[str | None, bool]] = []

    async def on_change(_ids: frozenset[str] | None) -> None:
        state = source.snapshot.get("sensor.a")
        seen.append((state.state if state else None, source.connected))

    task = asyncio.create_task(source.run(on_change))
    await asyncio.sleep(0.15)
    task.cancel()
    assert seen == [("1", True), ("2", True), (None, False)]  # empty while disconnected


async def test_static_source_announces_once() -> None:
    source = StaticSource({"sensor.a": EntityState("1")})
    calls: list[frozenset[str] | None] = []

    async def on_change(ids: frozenset[str] | None) -> None:
        calls.append(ids)

    task = asyncio.create_task(source.run(on_change))
    await asyncio.sleep(0.02)
    task.cancel()
    assert calls == [None] and source.connected and source.snapshot["sensor.a"].state == "1"
