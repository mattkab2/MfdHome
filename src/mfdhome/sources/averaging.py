"""Time-averaging numeric states for displays that refresh slowly (e-paper).

An e-paper display shows one image for minutes. Rendering it from the latest
reading would hold a passing spike or lull for that whole time, so such a
display renders from an averaged snapshot instead: each averaged entity shows
its time-weighted mean over the display's window, ending now. ``Samples``
keeps the recent values that needs. Like staleness marking, this happens
before render (render itself reads no clock), and the caller supplies the
time.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta

from mfdhome.conditions.values import as_number
from mfdhome.model.state import AveragingPolicy, EntityState, StateSnapshot

#: A value from a time until the next sample; ``None``: no number (unavailable).
type Sample = tuple[datetime, float | None]


def _number(entity: EntityState | None) -> float | None:
    if entity is None or not entity.available:
        return None
    return as_number(entity.state)


class Samples:
    """Recent numeric values per entity, as a step function: each holds from its
    time until the next. Only changes are kept, for the last ``keep``, plus the
    value in effect at its start. ``entities`` limits which are recorded (those
    a config uses); ``None`` records every entity seen.
    """

    def __init__(self, keep: timedelta, entities: Collection[str] | None = None) -> None:
        self.keep = keep
        self.entities = None if entities is None else frozenset(entities)
        self._series: dict[str, deque[Sample]] = {}

    def record(self, state: StateSnapshot, now: datetime) -> None:
        """Note each entity's value at ``now`` (a missing entity has none), and drop
        samples no window can reach any more."""
        ids = self.entities if self.entities is not None else state.keys() | self._series.keys()
        cutoff = now - self.keep
        for entity_id in ids:
            series = self._series.setdefault(entity_id, deque())
            value = _number(state.get(entity_id))
            if not series or series[-1][1] != value:
                series.append((now, value))
            while len(series) > 1 and series[1][0] <= cutoff:
                series.popleft()

    def mean(self, entity_id: str, start: datetime, end: datetime) -> float | None:
        """The time-weighted mean from ``start`` to ``end``, over the stretches that had
        a number; ``None`` if none did (or nothing was recorded)."""
        series = self._series.get(entity_id)
        if not series:
            return None
        total = weight = 0.0
        ends = [t for t, _ in series][1:]
        for (at, value), until in zip(series, [*ends, end], strict=True):
            lo, hi = max(at, start), min(until, end)
            if value is None or hi <= lo:
                continue
            seconds = (hi - lo).total_seconds()
            total += value * seconds
            weight += seconds
        return total / weight if weight else None


def averaged(
    state: StateSnapshot,
    samples: Samples,
    window: timedelta,
    now: datetime,
    policy: AveragingPolicy,
) -> StateSnapshot:
    """A copy of ``state`` with each averaged entity's state replaced by its mean over
    the ``window`` ending ``now``.

    An entity without a number now keeps its state, so an average never hides a
    sensor that has gone unavailable. Attributes are never averaged.
    """
    out = dict(state)
    start = now - window
    for entity_id, entity in state.items():
        if _number(entity) is None or not policy.averages(entity_id, entity):
            continue
        mean = samples.mean(entity_id, start, now)
        if mean is not None:
            out[entity_id] = replace(entity, state=str(round(mean, 6)))
    return out
