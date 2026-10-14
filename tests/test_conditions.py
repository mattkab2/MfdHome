"""Tests for DNF condition evaluation."""

import pytest

from mfdhome.conditions import (
    TRUE,
    AllOf,
    AnyOf,
    ChannelRef,
    Condition,
    EvalContext,
    Op,
    Rule,
    Thresholds,
    check,
    highest_match,
    holds,
    state_map_rules,
)
from mfdhome.model import EntityRef, Status, snapshot_from_ha_states
from tests.support import ha_state

GRID = EntityRef("sensor.grid_power")
BREAKER = ChannelRef("state")


def ctx(*items: dict[str, object], **channels: str) -> EvalContext:
    return EvalContext(
        snapshot_from_ha_states(items),
        {name: EntityRef(entity) for name, entity in channels.items()},
    )


def when(*groups: tuple[Condition, ...]) -> AnyOf:
    return AnyOf(tuple(AllOf(group) for group in groups))


@pytest.mark.parametrize(
    ("op", "operand", "state", "expected"),
    [
        (Op.EQ, "on", "ON", True),
        (Op.EQ, 5, "5.0", True),
        (Op.NE, "on", "off", True),
        (Op.IN, ("off", "tripped"), "tripped", True),
        (Op.NOT_IN, ("on", "closed"), "tripped", True),
        (Op.NOT_IN, ("on", "closed"), "on", False),
        (Op.LT, 0, "-2800", True),
        (Op.LE, 10, "10", True),
        (Op.GT, 0, "-1", False),
        (Op.GE, 90, "95", True),
        (Op.BETWEEN, (10, 20), "15", True),
        (Op.BETWEEN, (10, 20), "25", False),
        (Op.LT, 0, "abc", False),
    ],
)
def test_predicates(op: Op, operand: object, state: str, expected: bool) -> None:
    condition = Condition(GRID, op, operand)  # type: ignore[arg-type]
    assert check(condition, ctx(ha_state("sensor.grid_power", state))) is expected


@pytest.mark.parametrize("op", [Op.EQ, Op.NE, Op.NOT_IN, Op.LT, Op.GE])
def test_predicates_are_false_on_missing_data(op: Op) -> None:
    operand = ("on",) if op is Op.NOT_IN else 0
    assert check(Condition(GRID, op, operand), ctx()) is False
    unavailable = ctx(ha_state("sensor.grid_power", "unavailable"))
    assert check(Condition(GRID, op, operand), unavailable) is False


def test_unavailable_predicate() -> None:
    assert check(Condition(GRID, Op.UNAVAILABLE, True), ctx())
    assert not check(Condition(GRID, Op.UNAVAILABLE, False), ctx())
    present = ctx(ha_state("sensor.grid_power", "12"))
    assert check(Condition(GRID, Op.UNAVAILABLE, False), present)


def test_channel_refs_resolve_through_bindings() -> None:
    context = ctx(ha_state("switch.main", "off"), state="switch.main")
    assert check(Condition(BREAKER, Op.EQ, "off"), context)
    assert check(Condition(ChannelRef("unbound"), Op.UNAVAILABLE, True), context)


def test_attribute_refs() -> None:
    context = ctx(ha_state("sensor.bat", "ok", temp=41))
    assert check(Condition(EntityRef("sensor.bat", "temp"), Op.GT, 40), context)
    assert check(Condition(EntityRef("sensor.bat", "missing"), Op.UNAVAILABLE, True), context)


def test_cross_entity_dnf() -> None:
    # warning if (breaker off AND grid unavailable) OR breaker tripped
    expr = when(
        (Condition(BREAKER, Op.EQ, "off"), Condition(GRID, Op.UNAVAILABLE, True)),
        (Condition(BREAKER, Op.EQ, "tripped"),),
    )
    cases = [
        (("off", "unavailable"), True),
        (("off", "300"), False),
        (("on", "unavailable"), False),
        (("tripped", "300"), True),
    ]
    for (breaker, grid), expected in cases:
        context = ctx(
            ha_state("switch.main", breaker),
            ha_state("sensor.grid_power", grid),
            state="switch.main",
        )
        assert holds(expr, context) is expected, (breaker, grid)


def test_empty_expressions() -> None:
    assert holds(TRUE, ctx())
    assert not holds(AnyOf(), ctx())


def test_and_distributes_into_dnf() -> None:
    a, b, c, d = (Condition(GRID, Op.EQ, n) for n in range(4))
    product = when((a,), (b,)).and_(when((c,), (d,)))
    assert [term.conditions for term in product.terms] == [(a, c), (a, d), (b, c), (b, d)]
    assert when((a,)).or_(when((b,))).terms == (AllOf((a,)), AllOf((b,)))


def test_highest_match_takes_most_severe() -> None:
    rules = [
        Rule(Status.CAUTION, TRUE),
        Rule(Status.WARNING, TRUE),
        Rule(Status.NORMAL, TRUE),
    ]
    assert highest_match(rules, ctx()) is Status.WARNING
    assert highest_match([Rule(Status.WARNING, AnyOf())], ctx()) is None


def test_thresholds_compile() -> None:
    rules = Thresholds(warning_low=10, caution_low=25, warning_high=100).rules(GRID)
    for raw, expected in [("80", None), ("25", Status.CAUTION), ("8", Status.WARNING)]:
        context = ctx(ha_state("sensor.grid_power", raw))
        assert highest_match(rules, context) is expected, raw
    assert highest_match(rules, ctx(ha_state("sensor.grid_power", "100"))) is Status.WARNING


def test_state_map_compiles_with_default() -> None:
    rules = state_map_rules(
        BREAKER, {"on": Status.NORMAL, "off": Status.CAUTION}, default=Status.WARNING
    )
    for raw, expected in [("on", Status.NORMAL), ("off", Status.CAUTION), ("x", Status.WARNING)]:
        context = ctx(ha_state("switch.main", raw), state="switch.main")
        assert highest_match(rules, context) is expected, raw
    assert highest_match(rules, ctx(state="switch.main")) is None
