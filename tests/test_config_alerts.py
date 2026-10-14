"""Tests for alerts.yaml loading."""

import textwrap
from pathlib import Path

import pytest

from mfdhome.conditions import EvalContext, holds
from mfdhome.config import ConfigError, load_alerts, load_config, load_defs
from mfdhome.model import Severity, System, snapshot_from_ha_states
from tests.support import ha_state

ALERTS = """\
systems:
  GRID: {label: GRID}
  BATT: {label: BATTERY}
alerts:
  - id: grid_lost
    severity: warning
    system: GRID
    page: electrical
    message: GRID POWER LOST
    when: [{use: grid_lost}]
  - id: battery_low
    severity: caution
    system: BATT
    page: electrical
    message: BATTERY LOW
    any:
      - {entity: sensor.battery_soc, le: 25}
      - {entity: sensor.battery, attribute: soc, le: 25}
  - id: exporting
    severity: advisory
    system: GRID
    message: EXPORTING
    when: [{entity: sensor.grid_power, lt: -1000}]
"""
DEFS = "conditions:\n  grid_lost: {when: [{entity: sensor.grid_power, unavailable: true}]}\n"


def write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body))
    return path


def errors(path: Path, **kwargs: object) -> list[str]:
    with pytest.raises(ConfigError) as info:
        load_alerts(path, **kwargs)  # type: ignore[arg-type]
    return [f"{i.line}: {i.loc}: {i.message}" for i in info.value.issues]


def test_load_alerts(tmp_path: Path) -> None:
    defs = load_defs(write(tmp_path / "defs.yaml", DEFS))
    alerts = load_alerts(write(tmp_path / "alerts.yaml", ALERTS), defs, page_ids={"electrical"})
    assert alerts.systems == {"GRID": System("GRID", "GRID"), "BATT": System("BATT", "BATTERY")}
    assert [(a.id, a.severity, a.system, a.page) for a in alerts.alerts] == [
        ("grid_lost", Severity.WARNING, "GRID", "electrical"),
        ("battery_low", Severity.CAUTION, "BATT", "electrical"),
        ("exporting", Severity.ADVISORY, "GRID", None),
    ]
    grid_lost = alerts.by_id()["grid_lost"]
    assert holds(grid_lost.condition, EvalContext(snapshot_from_ha_states([])))
    live = snapshot_from_ha_states([ha_state("sensor.grid_power", "100")])
    assert not holds(grid_lost.condition, EvalContext(live))


def test_severity_properties() -> None:
    assert [s.rank for s in Severity] == [0, 1, 2]
    assert not Severity.ADVISORY.preempts and not Severity.ADVISORY.latches
    assert Severity.CAUTION.preempts and Severity.WARNING.latches


def test_alert_errors(tmp_path: Path) -> None:
    path = write(
        tmp_path / "alerts.yaml",
        """\
        systems: {GRID: {label: GRID}}
        alerts:
          - {id: a, severity: warning, system: GRID, message: A, page: nowhere,
             when: [{channel: state, eq: off}]}
          - {id: a, severity: caution, system: HVAC, message: B, page: electrical,
             when: [{use: missing}]}
          - {id: c, severity: caution, system: GRID, message: C,
             when: [{entity: sensor.x, eq: 1}]}
          - {id: d, severity: severe, system: GRID, message: D, page: electrical, when: []}
        """,
    )
    msgs = errors(path, page_ids={"electrical"})
    assert "4: alerts[0].when[0].channel: alerts have no channels; use 'entity'" in msgs
    assert "5: alerts[1].id: duplicate alert id 'a'" in msgs
    assert "5: alerts[1].system: unknown system 'HVAC'; expected: GRID" in msgs
    assert "6: alerts[1].when[0].use: unknown condition 'missing'" in msgs
    assert "7: alerts[2]: a caution alert needs a 'page' to show when it preempts" in msgs
    assert any(m.startswith("9: alerts[3].severity: Input should be") for m in msgs)


def test_unknown_page_is_checked_after_pages_load(tmp_path: Path) -> None:
    write(tmp_path / "defs.yaml", DEFS)
    write(tmp_path / "alerts.yaml", ALERTS)
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path)  # no pages at all
    assert [i.loc for i in info.value.issues] == ["alerts[0].page", "alerts[1].page"]


def test_named_condition_with_channel_rejected_in_alerts(tmp_path: Path) -> None:
    defs = load_defs(
        write(tmp_path / "defs.yaml", "conditions:\n  off: {when: [{channel: state, eq: off}]}\n")
    )
    path = write(
        tmp_path / "alerts.yaml",
        """\
        systems: {GRID: {label: GRID}}
        alerts:
          - {id: a, severity: advisory, system: GRID, message: A, when: [{use: off}]}
        """,
    )
    [msg] = errors(path, defs=defs)
    assert msg == (
        "3: alerts[0].when[0].use: condition 'off' uses channel 'state'; "
        "alerts can only use 'entity'"
    )


def test_config_without_alerts_file(tmp_path: Path) -> None:
    write(tmp_path / "pages/p.yaml", "page: p\ntitle: P\ncanvas: {width: 1, height: 1}\n")
    assert load_config(tmp_path).alerts.alerts == ()
