"""Shorthands (thresholds, state maps) that compile to plain rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mfdhome.conditions.model import AllOf, AnyOf, Condition, Op, Rule, ValueRef
from mfdhome.model.binding import Status


@dataclass(frozen=True)
class Thresholds:
    """Numeric limits; a value at or beyond a limit takes that level. All optional."""

    warning_low: float | None = None
    caution_low: float | None = None
    caution_high: float | None = None
    warning_high: float | None = None

    def rules(self, ref: ValueRef) -> tuple[Rule, ...]:
        """Compile to rules on ``ref``."""
        out = []
        for level, low, high in (
            (Status.WARNING, self.warning_low, self.warning_high),
            (Status.CAUTION, self.caution_low, self.caution_high),
        ):
            terms = []
            if low is not None:
                terms.append(AllOf((Condition(ref, Op.LE, low),)))
            if high is not None:
                terms.append(AllOf((Condition(ref, Op.GE, high),)))
            if terms:
                out.append(Rule(level, AnyOf(tuple(terms))))
        return tuple(out)


def state_map_rules(
    ref: ValueRef, mapping: Mapping[str, Status], default: Status = Status.NORMAL
) -> tuple[Rule, ...]:
    """Compile ``{state: level}`` plus a level for unlisted (but available) states."""
    rules = [
        Rule(level, AnyOf((AllOf((Condition(ref, Op.EQ, state),)),)))
        for state, level in mapping.items()
    ]
    if default is not Status.NORMAL:
        unlisted = Condition(ref, Op.NOT_IN, tuple(mapping))
        rules.append(Rule(default, AnyOf((AllOf((unlisted,)),))))
    return tuple(rules)
