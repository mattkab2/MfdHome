"""Scripted state sources for developing without Home Assistant.

A scenario is a starting snapshot plus timed steps that set or remove
entities and can drop and restore the "Home Assistant" connection; with a
``loop`` period it starts over. ``serve --scenario`` replays one in real time,
exercising alerts, hold times, the banner and the log end to end.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

from mfdhome.model.state import EntityState, StateSnapshot

logger = logging.getLogger(__name__)

#: Called with the entity ids that changed (``None``: the whole snapshot was replaced).
type OnChange = Callable[[frozenset[str] | None], Awaitable[None]]


class StateSource(Protocol):
    """Anything the server can take states from: Home Assistant, a file, a scenario."""

    @property
    def snapshot(self) -> StateSnapshot:
        """The current entity states."""
        ...

    @property
    def connected(self) -> bool:
        """Whether the source is reachable (alerts are frozen while it isn't)."""
        ...

    async def run(self, on_change: OnChange) -> None:
        """Keep the snapshot current, calling ``on_change`` after changes; runs until cancelled."""
        ...


@dataclass(frozen=True)
class Step:
    """At ``at`` into the scenario: set and remove entities, and maybe (dis)connect.

    Entities in ``keep`` keep the attributes they had (the step gave only a
    state, as most Home Assistant changes do); the others take the step's.
    """

    at: timedelta
    set: Mapping[str, EntityState] = field(default_factory=dict)
    remove: frozenset[str] = frozenset()
    connected: bool | None = None
    keep: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Scenario:
    """A starting snapshot and timed steps (sorted by time); ``loop`` restarts it."""

    base: StateSnapshot = field(default_factory=dict)
    steps: tuple[Step, ...] = ()
    loop: timedelta | None = None


def state_at(scenario: Scenario, elapsed: timedelta) -> tuple[StateSnapshot, bool]:
    """The snapshot and connection state ``elapsed`` into the scenario."""
    if scenario.loop is not None and scenario.loop > timedelta(0):
        elapsed = elapsed % scenario.loop
    states = dict(scenario.base)
    connected = True
    for step in scenario.steps:
        if step.at > elapsed:
            break
        for entity_id, new in step.set.items():
            old = states.get(entity_id)
            if entity_id in step.keep and old is not None:
                new = EntityState(new.state, old.attributes)
            states[entity_id] = new
        for entity_id in step.remove:
            states.pop(entity_id, None)
        if step.connected is not None:
            connected = step.connected
    return states, connected


class StaticSource:
    """A fixed snapshot (``serve --states``): always connected, never changes."""

    def __init__(self, snapshot: StateSnapshot) -> None:
        self._snapshot = snapshot

    @property
    def snapshot(self) -> StateSnapshot:
        """The fixed states."""
        return self._snapshot

    @property
    def connected(self) -> bool:
        """Always connected."""
        return True

    async def run(self, on_change: OnChange) -> None:
        """Announce the snapshot once, then wait to be cancelled."""
        await on_change(None)
        await asyncio.Event().wait()


class ScenarioSource:
    """Replays a scenario in real time (``serve --scenario``).

    While "disconnected" the snapshot is empty, as with the real Home
    Assistant client.
    """

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self._states, self._connected = state_at(scenario, timedelta(0))

    @property
    def snapshot(self) -> StateSnapshot:
        """The states at the current point in the scenario (empty while disconnected)."""
        return self._states if self._connected else {}

    @property
    def connected(self) -> bool:
        """Whether the scenario currently has Home Assistant connected."""
        return self._connected

    def times(self) -> list[timedelta]:
        """When the snapshot can change within one pass (plus the loop point)."""
        times = sorted({s.at for s in self.scenario.steps if s.at > timedelta(0)})
        if self.scenario.loop is not None:
            times.append(self.scenario.loop)
        return times

    async def run(self, on_change: OnChange) -> None:
        """Step through the scenario in real time, looping if it loops."""
        await on_change(None)
        while True:
            previous = timedelta(0)
            for at in self.times():
                await asyncio.sleep((at - previous).total_seconds())
                previous = at
                self._states, self._connected = state_at(self.scenario, at)
                logger.info("scenario at %s", at)
                await on_change(None)
            if self.scenario.loop is None:
                await asyncio.Event().wait()
