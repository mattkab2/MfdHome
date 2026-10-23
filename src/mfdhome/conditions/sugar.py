"""Shorthands (thresholds, state maps) that compile to plain rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mfdhome.conditions.model import AnyOf, Condition, Op, Rule, ValueRef
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
            limits = [(Op.LE, low), (Op.GE, high)]
            when = AnyOf()
            for op, limit in limits:
                if limit is not None:
                    when = when.or_(AnyOf.single(Condition(ref, op, limit)))
            if when.terms:
                out.append(Rule(level, when))
        return tuple(out)


@dataclass(frozen=True)
class StateMap:
    """Levels for listed states (lowercase) and a level for any other available state."""

    states: Mapping[str, Status]
    default: Status = Status.NORMAL

    def rules(self, ref: ValueRef) -> tuple[Rule, ...]:
        """Compile to rules on ``ref``: one per listed state, and one for the others
        unless their level is normal."""
        rules = [
            Rule(level, AnyOf.single(Condition(ref, Op.EQ, state)))
            for state, level in self.states.items()
        ]
        if self.default is not Status.NORMAL:
            others = Condition(ref, Op.NOT_IN, tuple(self.states))
            rules.append(Rule(self.default, AnyOf.single(others)))
        return tuple(rules)
