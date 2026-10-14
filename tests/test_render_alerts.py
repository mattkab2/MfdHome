"""Rendering alerts: system aggregation, tiles, banner and attention cues."""

import re
from datetime import UTC, datetime

import pytest

from mfdhome.conditions import AnyOf, Condition, Op
from mfdhome.mfd import AlertState, Phase
from mfdhome.model import (
    AlertDef,
    EntityRef,
    LineElement,
    Page,
    Severity,
    Status,
    StatusSpec,
    System,
    TileElement,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element, render_page
from mfdhome.render.alerts import AlertView, SystemView
from mfdhome.render.page import attention_css
from mfdhome.themes import EINK_MONO, LCD, MIRROR, Target, Theme
from tests.support import ha_state

T0 = datetime(2026, 1, 1, tzinfo=UTC)
TARGET = Target("t", 100, 100)


def cond(entity: str) -> AnyOf:
    return AnyOf.single(Condition(EntityRef(entity), Op.EQ, "on"))


def alert(id_: str, severity: Severity, system: str = "GRID") -> AlertDef:
    return AlertDef(id_, severity, system, id_.upper(), cond(f"binary_sensor.{id_}"), "p")


WARN = alert("warn", Severity.WARNING)
CAUT = alert("caut", Severity.CAUTION)
ADV = alert("adv", Severity.ADVISORY)
OTHER = alert("other", Severity.WARNING, "BATT")
ALERTS = (WARN, CAUT, ADV, OTHER)
SYSTEMS = {"GRID": System("GRID", "GRID"), "BATT": System("BATT", "BATTERY")}
LIVE = snapshot_from_ha_states([ha_state(f"binary_sensor.{a.id}", "off") for a in ALERTS])


def view(**phases: Phase) -> AlertView:
    board = {k: AlertState(p, T0) for k, p in phases.items()}
    return AlertView(ALERTS, SYSTEMS, board)


class TestSystemView:
    @pytest.mark.parametrize(
        ("phases", "expected"),
        [
            ({}, SystemView(None)),
            ({"caut": Phase.ACTIVE_ACKED}, SystemView(Severity.CAUTION)),
            (
                {"caut": Phase.ACTIVE_ACKED, "warn": Phase.ACTIVE_UNACKED},
                SystemView(Severity.WARNING, unacknowledged=True),
            ),
            (
                {"warn": Phase.CLEARED_UNACKED},
                SystemView(Severity.WARNING, cleared=True, unacknowledged=True),
            ),
            # an active warning outranks the latch: not "cleared"
            (
                {"warn": Phase.ACTIVE_ACKED, "caut": Phase.CLEARED_UNACKED},
                SystemView(Severity.WARNING, unacknowledged=True),
            ),
            # advisories light the tile but never ask for attention
            ({"adv": Phase.ACTIVE_UNACKED}, SystemView(Severity.ADVISORY)),
            # another system's alert doesn't leak in
            ({"other": Phase.ACTIVE_UNACKED}, SystemView(None)),
        ],
    )
    def test_aggregation(self, phases: dict[str, Phase], expected: SystemView) -> None:
        assert view(**phases).system("GRID", LIVE) == expected

    def test_unavailable_when_every_entity_is_missing(self) -> None:
        assert view().system("GRID", {}) == SystemView(None, unavailable=True)
        partly = snapshot_from_ha_states([ha_state("binary_sensor.warn", "off")])
        assert not view().system("GRID", partly).unavailable
        # a lit tile still shows its latch
        lit = view(warn=Phase.CLEARED_UNACKED).system("GRID", {})
        assert lit.severity is Severity.WARNING and lit.unavailable

    def test_active_status_for_elements(self) -> None:
        assert view(warn=Phase.ACTIVE_ACKED).active_status(("GRID",), ()) is Status.WARNING
        assert view(caut=Phase.ACTIVE_UNACKED).active_status((), ("caut",)) is Status.CAUTION
        assert view(warn=Phase.CLEARED_UNACKED).active_status(("GRID",), ()) is None
        assert view(adv=Phase.ACTIVE_UNACKED).active_status(("GRID",), ()) is None
        assert view(other=Phase.ACTIVE_ACKED).active_status(("GRID",), ()) is None


class TestBanner:
    def test_off_unless_requested(self) -> None:
        assert view(warn=Phase.ACTIVE_UNACKED).banner() is None

    def test_picks_most_urgent_and_counts_others(self) -> None:
        v = AlertView(
            ALERTS,
            SYSTEMS,
            {
                "caut": AlertState(Phase.ACTIVE_UNACKED, T0),
                "other": AlertState(Phase.ACTIVE_UNACKED, T0),
                "adv": AlertState(Phase.ACTIVE_UNACKED, T0),
            },
            show_banner=True,
        )
        banner = v.banner()
        assert banner is not None
        assert (banner.alert.id, banner.others) == ("other", 1)

    def test_rendered_at_bottom_with_attention(self) -> None:
        v = AlertView(ALERTS, SYSTEMS, {"warn": AlertState(Phase.ACTIVE_UNACKED, T0)}, True)
        svg = render_page(Page("p", "P", 400, 300), LIVE, LCD, TARGET, v)
        assert '<g id="banner"><g class="attn"><rect x="0" y="260" width="400" height="40"' in svg
        assert ">WARN<" in svg and "+" not in svg.split('id="banner"')[1]


def tile_svg(theme: Theme, **phases: Phase) -> str:
    return render_element(TileElement("t", (100, 100), "GRID"), LIVE, theme, view(**phases))


class TestTiles:
    def test_dark_tile(self) -> None:
        svg = tile_svg(LCD)
        assert f'stroke="{LCD.dim}"' in svg and "attn" not in svg

    def test_unavailable_tile_is_dotted(self) -> None:
        svg = render_element(TileElement("t", (0, 0), "GRID"), {}, LCD, view())
        assert f'stroke-dasharray="{LCD.unavailable_dots}" stroke-linecap="round"' in svg

    def test_lcd_unacked_warning_is_filled_and_flashes(self) -> None:
        svg = tile_svg(LCD, warn=Phase.ACTIVE_UNACKED)
        red = LCD.color(Status.WARNING)
        assert f'fill="{red}"' in svg and 'class="attn"' in svg
        assert f'fill="{LCD.background}"' in svg  # label drawn in the background color

    def test_acknowledged_is_steady(self) -> None:
        assert "attn" not in tile_svg(LCD, warn=Phase.ACTIVE_ACKED)
        assert "attn" not in tile_svg(MIRROR, warn=Phase.ACTIVE_ACKED)

    def test_mirror_outlines_and_pulses(self) -> None:
        svg = tile_svg(MIRROR, caut=Phase.ACTIVE_UNACKED)
        yellow = MIRROR.color(Status.CAUTION)
        assert f'fill="none" stroke="{yellow}"' in svg and 'class="attn"' in svg
        assert f'fill="{yellow}"' in svg  # label in the caution color

    def test_eink_ring_instead_of_animation(self) -> None:
        unacked = tile_svg(EINK_MONO, warn=Phase.ACTIVE_UNACKED)
        acked = tile_svg(EINK_MONO, warn=Phase.ACTIVE_ACKED)
        assert "attn" not in unacked
        assert unacked.count("<rect") == acked.count("<rect") + 1

    def test_cleared_is_outlined_with_mark(self) -> None:
        svg = tile_svg(LCD, warn=Phase.CLEARED_UNACKED)
        assert ">CLR<" in svg and 'fill="none"' in svg and 'class="attn"' in svg

    def test_advisory_is_cyan_outline_without_attention(self) -> None:
        svg = tile_svg(LCD, adv=Phase.ACTIVE_UNACKED)
        assert LCD.color(Status.ACTIVE) in svg and "attn" not in svg

    def test_label_override(self) -> None:
        tile = TileElement("t", (0, 0), "BATT", label="BATTERY SYS")
        assert ">BATTERY SYS<" in render_element(tile, LIVE, LCD, view())
        assert ">BATTERY<" in render_element(TileElement("t", (0, 0), "BATT"), LIVE, LCD, view())

    @pytest.mark.parametrize("theme", [LCD, MIRROR, EINK_MONO], ids=lambda t: t.name)
    def test_every_state_renders_distinctly(self, theme: Theme) -> None:
        states = [
            tile_svg(theme),
            render_element(TileElement("t", (100, 100), "GRID"), {}, theme, view()),
            tile_svg(theme, adv=Phase.ACTIVE_UNACKED),
            tile_svg(theme, caut=Phase.ACTIVE_UNACKED),
            tile_svg(theme, caut=Phase.ACTIVE_ACKED),
            tile_svg(theme, caut=Phase.CLEARED_UNACKED),
            tile_svg(theme, warn=Phase.ACTIVE_UNACKED),
            tile_svg(theme, warn=Phase.ACTIVE_ACKED),
            tile_svg(theme, warn=Phase.CLEARED_UNACKED),
        ]
        assert len(set(states)) == len(states)


class TestAttentionCss:
    def test_per_theme(self) -> None:
        assert attention_css(LCD) == (
            ".attn{animation:mfd-attn 1s step-end infinite}@keyframes mfd-attn{50%{opacity:0.25}}"
        )
        assert "2.5s ease-in-out" in attention_css(MIRROR)
        assert attention_css(EINK_MONO) == ""

    @pytest.mark.parametrize("theme", [LCD, MIRROR], ids=lambda t: t.name)
    def test_style_only_when_something_needs_attention(self, theme: Theme) -> None:
        page = Page("p", "P", 400, 300, (TileElement("t", (100, 100), "GRID"),))
        quiet = render_page(page, LIVE, theme, TARGET, view(warn=Phase.ACTIVE_ACKED))
        loud = render_page(page, LIVE, theme, TARGET, view(warn=Phase.ACTIVE_UNACKED))
        assert "<style>" not in quiet
        assert loud.count("<style>") == 1

    def test_eink_output_never_animates(self) -> None:
        page = Page("p", "P", 400, 300, (TileElement("t", (100, 100), "GRID"),))
        v = AlertView(ALERTS, SYSTEMS, {"warn": AlertState(Phase.ACTIVE_UNACKED, T0)}, True)
        svg = render_page(page, LIVE, EINK_MONO, TARGET, v)
        assert not re.search(r"animation|@keyframes|<animate|<style", svg)


def test_element_status_from_system() -> None:
    line = LineElement("l", ((0, 0), (10, 0)), status=StatusSpec(systems=("GRID",)))
    assert LCD.color(Status.WARNING) in render_element(
        line, LIVE, LCD, view(warn=Phase.ACTIVE_ACKED)
    )
    assert LCD.color(Status.NORMAL) in render_element(line, LIVE, LCD, view())
