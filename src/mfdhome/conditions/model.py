"""Condition data model: rules in disjunctive normal form (OR of ANDs)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mfdhome.model.binding import EntityRef, Status


class Op(StrEnum):
    """Condition predicates."""

    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    BETWEEN = "between"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ChannelRef:
    """A reference to one of the evaluating element's bound channels."""

    channel: str


type ValueRef = ChannelRef | EntityRef


@dataclass(frozen=True)
class RefOperand:
    """Another value to compare against, plus ``offset`` (e.g. a setpoint minus 3)."""

    ref: ValueRef
    offset: float = 0.0


type Scalar = str | float
type Operand = Scalar | bool | tuple[Scalar, ...] | RefOperand


@dataclass(frozen=True)
class Condition:
    """One predicate on one value, e.g. ``sensor.grid_power lt 0``.

    The ordering predicates (``lt``, ``le``, ``gt``, ``ge``) may compare
    against another value (a ``RefOperand``) instead of a constant.
    """

    ref: ValueRef
    op: Op
    operand: Operand

    def refs(self) -> tuple[ValueRef, ...]:
        """Every value this condition reads: its own, and a compared one."""
        if isinstance(self.operand, RefOperand):
            return (self.ref, self.operand.ref)
        return (self.ref,)


@dataclass(frozen=True)
class AllOf:
    """A conjunction: true when every condition is true (an empty one is true)."""

    conditions: tuple[Condition, ...] = ()


@dataclass(frozen=True)
class AnyOf:
    """A disjunction of conjunctions: true when any term is true (an empty one is false)."""

    terms: tuple[AllOf, ...] = ()

    @classmethod
    def single(cls, condition: Condition) -> AnyOf:
        """An expression of one condition."""
        return cls((AllOf((condition,)),))

    def and_(self, other: AnyOf) -> AnyOf:
        """Conjunction of two DNF expressions, distributed back into DNF."""
        return AnyOf(
            tuple(AllOf(a.conditions + b.conditions) for a in self.terms for b in other.terms)
        )

    def or_(self, other: AnyOf) -> AnyOf:
        """Disjunction of two DNF expressions."""
        return AnyOf(self.terms + other.terms)


TRUE = AnyOf((AllOf(),))


@dataclass(frozen=True)
class Rule:
    """When ``when`` holds, the subject takes status ``level``."""

    level: Status
    when: AnyOf
