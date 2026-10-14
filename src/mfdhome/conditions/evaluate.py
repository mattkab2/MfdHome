"""Pure evaluation of conditions and rules against a state snapshot."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from mfdhome.conditions.model import AnyOf, ChannelRef, Condition, Op, Operand, Rule, ValueRef
from mfdhome.conditions.values import MISSING, Value, as_number, read
from mfdhome.model.binding import Binding, ElementRef, Status
from mfdhome.model.state import StateSnapshot

#: Rule levels in increasing precedence.
SEVERITY_ORDER = (Status.NORMAL, Status.CAUTION, Status.WARNING)


@dataclass(frozen=True)
class EvalContext:
    """What a condition can see.

    ``channels`` are the evaluating element's bindings; ``derived`` are its
    computed channels (a group's sums and counts); ``elements`` holds other
    elements' channel values, for bindings that refer to another element.
    """

    state: StateSnapshot
    channels: Mapping[str, Binding] = field(default_factory=dict)
    derived: Mapping[str, Value] = field(default_factory=dict)
    elements: Mapping[str, Mapping[str, Value]] = field(default_factory=dict)

    def value(self, ref: ValueRef) -> Value:
        """Resolve ``ref``; an unbound channel is unavailable."""
        if isinstance(ref, ChannelRef):
            if ref.channel in self.derived:
                return self.derived[ref.channel]
            bound = self.channels.get(ref.channel)
            if bound is None:
                return MISSING
            if isinstance(bound, ElementRef):
                return self.elements.get(bound.element_id, {}).get(bound.channel, MISSING)
            return read(bound, self.state)
        return read(ref, self.state)

    def has(self, channel: str) -> bool:
        """Whether ``channel`` is bound or derived on the evaluating element."""
        return channel in self.channels or channel in self.derived


def _same(value: object, operand: object) -> bool:
    left, right = as_number(value), as_number(operand)
    if left is not None and right is not None:
        return left == right
    return str(value).strip().lower() == str(operand).strip().lower()


def _compare(op: Op, value: float, operand: Operand) -> bool:
    if op is Op.BETWEEN:
        assert isinstance(operand, tuple)
        low, high = (as_number(bound) for bound in operand)
        return low is not None and high is not None and low <= value <= high
    limit = as_number(operand)
    if limit is None:
        return False
    match op:
        case Op.LT:
            return value < limit
        case Op.LE:
            return value <= limit
        case Op.GT:
            return value > limit
        case _:
            return value >= limit


def check(condition: Condition, ctx: EvalContext) -> bool:
    """Evaluate one condition.

    Every predicate except ``unavailable`` is false on missing data, so rules
    never fire on stale or absent sensors unless they ask about availability.
    """
    value = ctx.value(condition.ref)
    op, operand = condition.op, condition.operand
    if op is Op.UNAVAILABLE:
        return (not value.available) is bool(operand)
    if value.raw is None:
        return False
    match op:
        case Op.EQ:
            return _same(value.raw, operand)
        case Op.NE:
            return not _same(value.raw, operand)
        case Op.IN | Op.NOT_IN:
            options = operand if isinstance(operand, tuple) else (operand,)
            found = any(_same(value.raw, option) for option in options)
            return found if op is Op.IN else not found
        case _:
            number = value.number
            return number is not None and _compare(op, number, operand)


def holds(expr: AnyOf, ctx: EvalContext) -> bool:
    """Evaluate a DNF expression."""
    return any(all(check(c, ctx) for c in term.conditions) for term in expr.terms)


def highest_match(rules: Iterable[Rule], ctx: EvalContext) -> Status | None:
    """The highest-severity level among matching rules, or ``None`` if none match."""
    matched = [rule.level for rule in rules if holds(rule.when, ctx)]
    return max(matched, key=SEVERITY_ORDER.index) if matched else None
