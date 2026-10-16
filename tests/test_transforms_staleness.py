"""Binding transforms (scale/unit) and stale-data handling."""

import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mfdhome.conditions import read
from mfdhome.config import ConfigError, load_defs, load_page
from mfdhome.model import EntityRef, LineElement, snapshot_from_ha_states
from mfdhome.model.state import StalePolicy
from mfdhome.sources.staleness import mark_stale
from mfdhome.symbols.format import format_value

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def item(
    entity_id: str, state: str, minutes_ago: float | None = None, **attrs: object
) -> dict[str, object]:
    out: dict[str, object] = {"entity_id": entity_id, "state": state, "attributes": attrs}
    if minutes_ago is not None:
        out["last_reported"] = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return out


class TestTransforms:
    SNAP = snapshot_from_ha_states(
        [
            item("sensor.grid", "-1200", unit_of_measurement="W"),
            item("sensor.batt_kw", "1.5", unit_of_measurement="kW"),
            item("sensor.mode", "charging"),
            item("sensor.inv", "ok", power=2.5),
        ]
    )

    def test_scale_flips_sign(self) -> None:
        value = read(EntityRef("sensor.grid", scale=-1), self.SNAP)
        assert value.number == 1200 and value.unit == "W"

    def test_scale_with_unit_converts(self) -> None:
        value = read(EntityRef("sensor.batt_kw", scale=1000, unit="W"), self.SNAP)
        assert value.number == 1500
        assert format_value(value, "power") == "1.5 kW"

    def test_scale_ignores_non_numeric_and_scales_attributes(self) -> None:
        assert read(EntityRef("sensor.mode", scale=-1), self.SNAP).raw == "charging"
        assert (
            read(EntityRef("sensor.inv", "power", scale=1000, unit="W"), self.SNAP).number == 2500
        )

    def test_load_transforms(self, tmp_path: Path) -> None:
        path = tmp_path / "p.yaml"
        path.write_text(
            textwrap.dedent(
                """\
                page: p
                title: P
                canvas: {width: 10, height: 10}
                elements:
                  - id: g
                    type: line
                    from: [0, 0]
                    to: [1, 0]
                    bind: {rate: {entity: sensor.grid, scale: -1, unit: W}}
                """
            )
        )
        [line] = load_page(path).elements
        assert isinstance(line, LineElement)
        assert line.bind["rate"] == EntityRef("sensor.grid", scale=-1, unit="W")

    def test_transform_errors(self, tmp_path: Path) -> None:
        path = tmp_path / "p.yaml"
        path.write_text(
            textwrap.dedent(
                """\
                page: p
                title: P
                canvas: {width: 10, height: 10}
                defs:
                  stale_after: {default: 5m}
                elements:
                  - {id: b, type: battery, at: [0, 0], bind: {level: sensor.soc}}
                  - id: a
                    type: line
                    from: [0, 0]
                    to: [1, 0]
                    bind: {rate: {entity: sensor.x, scale: 0}}
                  - id: c
                    type: line
                    from: [0, 0]
                    to: [1, 0]
                    bind: {rate: {entity: b.level, scale: 2}}
                """
            )
        )
        with pytest.raises(ConfigError) as info:
            load_page(path)
        msgs = [f"{i.loc}: {i.message}" for i in info.value.issues]
        assert "defs.stale_after: stale_after is house-wide: set it in defs.yaml" in msgs
        assert "elements[1].bind.rate: 'scale' must not be 0" in msgs
        assert (
            "elements[2].bind.rate: "
            "'scale' and 'unit' apply to entity bindings, not element channels"
        ) in msgs


class TestStaleness:
    def test_report_time_prefers_last_reported(self) -> None:
        [entity] = snapshot_from_ha_states(
            [
                {
                    "entity_id": "sensor.a",
                    "state": "1",
                    "last_updated": "2026-01-01T10:00:00+00:00",
                    "last_reported": "2026-01-01T11:59:00+00:00",
                }
            ]
        ).values()
        assert entity.reported == datetime(2026, 1, 1, 11, 59, tzinfo=UTC)
        [old] = snapshot_from_ha_states(
            [{"entity_id": "a.b", "state": "1", "last_updated": "2026-01-01T10:00:00+00:00"}]
        ).values()
        assert old.reported == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    def test_mark_stale(self) -> None:
        snap = snapshot_from_ha_states(
            [
                item("sensor.fresh", "1", minutes_ago=2),
                item("sensor.old", "1", minutes_ago=20, unit_of_measurement="W"),
                item("sensor.slow", "1", minutes_ago=50),
                item("sensor.undated", "1"),
            ]
        )
        policy = StalePolicy(timedelta(minutes=15), {"sensor.slow": timedelta(hours=1)})
        marked = mark_stale(snap, policy, NOW)
        assert marked["sensor.fresh"].available
        assert not marked["sensor.old"].available
        assert marked["sensor.old"].attributes == {"unit_of_measurement": "W", "mfd_stale": True}
        assert marked["sensor.slow"].available  # per-entity override
        assert marked["sensor.undated"].available  # no report time: never stale
        assert snap["sensor.old"].available  # input untouched
        assert mark_stale(snap, StalePolicy(), NOW) == snap  # no policy: nothing stale

    def test_load_stale_policy(self, tmp_path: Path) -> None:
        path = tmp_path / "defs.yaml"
        path.write_text(
            "stale_after:\n  default: 15m\n  entities: {sensor.wind: 1h, sensor.x: 90}\n"
        )
        policy = load_defs(path).stale_after
        assert policy == StalePolicy(
            timedelta(minutes=15),
            {"sensor.wind": timedelta(hours=1), "sensor.x": timedelta(seconds=90)},
        )
        path.write_text("stale_after: {default: soon}\n")
        with pytest.raises(ConfigError, match=r"stale_after\.default"):
            load_defs(path)
