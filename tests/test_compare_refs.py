"""Comparing one value against another (plus an offset), e.g. a room against its setpoint."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.conditions import ChannelRef, Condition, EvalContext, Op, RefOperand, check
from mfdhome.config import ConfigError, Defs, load_alerts, load_config
from mfdhome.config.inventory import entity_uses
from mfdhome.model import EntityRef, snapshot_from_ha_states
from tests.support import ha_state

SETPOINT = EntityRef("climate.upstairs", "temperature")
ROOM = EntityRef("sensor.bedroom_temperature")
TOO_COLD = Condition(ROOM, Op.LT, RefOperand(SETPOINT, -3.0))


def ctx(room: str | None, setpoint: float | None) -> EvalContext:
    items = []
    if room is not None:
        items.append(ha_state("sensor.bedroom_temperature", room))
    if setpoint is not None:
        items.append(ha_state("climate.upstairs", "heat", temperature=setpoint))
    return EvalContext(snapshot_from_ha_states(items))


@pytest.mark.parametrize(
    ("room", "setpoint", "expected"),
    [
        ("64", 68, True),
        ("65", 68, False),
        ("66", 68, False),
        (None, 68, False),
        ("60", None, False),
    ],
)
def test_compares_against_another_value_plus_offset(
    room: str | None, setpoint: float | None, expected: bool
) -> None:
    assert check(TOO_COLD, ctx(room, setpoint)) is expected  # missing either side: false


def test_channel_operands() -> None:
    cond = Condition(ChannelRef("supply"), Op.GE, RefOperand(ChannelRef("limit")))
    state = snapshot_from_ha_states([ha_state("sensor.s", "60"), ha_state("sensor.l", "55")])
    channels = {"supply": EntityRef("sensor.s"), "limit": EntityRef("sensor.l")}
    assert check(cond, EvalContext(state, channels))
    assert cond.refs() == (ChannelRef("supply"), ChannelRef("limit"))


def write(path: Path, body: str) -> Path:
    path.write_text(textwrap.dedent(body))
    return path


def test_alert_config(tmp_path: Path) -> None:
    alerts = load_alerts(
        write(
            tmp_path / "alerts.yaml",
            """\
            systems: {HVAC: {label: HVAC}}
            alerts:
              - id: upstairs_cold
                severity: caution
                system: HVAC
                message: UPSTAIRS BELOW SETPOINT
                for: 30m
                when:
                  - entity: sensor.bedroom_temperature
                    lt: {entity: climate.upstairs, attribute: temperature, offset: -3}
            """,
        ),
        Defs(),
    )
    assert alerts.alerts[0].condition.terms[0].conditions == (TOO_COLD,)
    assert set(entity_uses(load_config(tmp_path))) == {
        "sensor.bedroom_temperature",
        "climate.upstairs",  # the compared entity counts as used too
    }


@pytest.mark.parametrize(
    ("operand", "message"),
    [
        ("{channel: x}", "alerts have no channels"),
        ("{entity: sensor.a, channel: b}", "exactly one of 'channel' or 'entity'"),
        ("{offset: 2}", "exactly one of 'channel' or 'entity'"),
        ("{channel: x, attribute: y}", "'attribute' is only allowed with 'entity'"),
    ],
)
def test_operand_errors(tmp_path: Path, operand: str, message: str) -> None:
    path = write(
        tmp_path / "alerts.yaml",
        f"""\
        systems: {{S: {{label: S}}}}
        alerts:
          - {{id: a, severity: caution, system: S, message: A,
             when: [{{entity: sensor.t, gt: {operand}}}]}}
        """,
    )
    with pytest.raises(ConfigError, match=message):
        load_alerts(path, Defs())
