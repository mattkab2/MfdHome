"""The flow arrow: a harpoon beside the line, level with its readout, clear of core and labels."""

import re
import textwrap
from pathlib import Path

import pytest

from mfdhome.conditions import AnyOf, Condition, Op
from mfdhome.config import ConfigError, Defs, load_page
from mfdhome.layout import Anchor
from mfdhome.model import (
    EntityRef,
    FlowSpec,
    LineElement,
    LineTag,
    Readout,
    Status,
    snapshot_from_ha_states,
)
from mfdhome.render import render_element
from mfdhome.symbols.line import Flow, line
from mfdhome.themes import LCD
from tests.support import ha_state

ACTIVE = Status.ACTIVE
FLAT = ((0.0, 0.0), (100.0, 0.0))


def head(body: str) -> str:
    """The arrowhead's points attribute."""
    match = re.search(r'<polygon points="([^"]+)"', body)
    assert match is not None
    return match.group(1)


def points(body: str) -> list[tuple[float, float]]:
    pairs = (p.split(",") for p in head(body).split())
    return [(float(x), float(y)) for x, y in pairs]


def test_harpoon_beside_a_cased_line() -> None:
    # Pipe 10 wide: a 2 wide shaft and a head set 4 off the wall, below the line.
    body = line(FLAT, ACTIVE, Flow.FORWARD, LCD, casing=True).body
    assert head(body) == "65,9 51,9 51,17"  # tip downstream, barb flaring outward
    assert '<line x1="35" y1="10" x2="51" y2="10"' in body and 'stroke-width="2"' in body
    reverse = line(FLAT, ACTIVE, Flow.REVERSE, LCD, casing=True).body
    assert head(reverse) == "35,9 49,9 49,17"  # same side, pointing back


def test_never_touches_the_pipe() -> None:
    for casing in (True, False):
        parts = line(FLAT, ACTIVE, Flow.FORWARD, LCD, casing=casing)
        assert min(y for _, y in points(parts.body)) > parts.half_width


def test_sides_by_default_and_away_from_labels() -> None:
    vertical = line(((0.0, 0.0), (0.0, 100.0)), ACTIVE, Flow.FORWARD, LCD, casing=True).body
    assert all(x < 0 for x, _ in points(vertical))  # left of vertical lines
    above = line(FLAT, ACTIVE, Flow.FORWARD, LCD, casing=True, arrow_avoid=(0.0, 1.0)).body
    assert all(y < 0 for _, y in points(above))  # labels below: arrow above


def test_level_with_the_readout_but_never_round_a_bend() -> None:
    bent = ((0.0, 0.0), (200.0, 0.0), (200.0, 100.0))

    def tip(at: float) -> tuple[float, float]:
        return points(line(bent, ACTIVE, Flow.FORWARD, LCD, casing=True, arrow_at=at).body)[0]

    assert tip(0.1) == (45, 9)  # centered at 30, a tenth of the way
    assert tip(0.0) == (39, 9)  # slid in from the start (half the arrow plus clearance)
    assert tip(0.66) == (191, 9)  # slid back from the bend at 200
    # Too close to the end of a short leg: the middle of the longest leg instead.
    short = ((0.0, 0.0), (200.0, 0.0), (200.0, 20.0))
    assert points(line(short, ACTIVE, Flow.FORWARD, LCD, casing=True, arrow_at=0.99).body)[0] == (
        115,
        9,
    )


def test_no_arrow_without_flow() -> None:
    assert "<polygon" not in line(FLAT, ACTIVE, None, LCD, casing=True).body


def test_rendered_line_follows_its_first_readout() -> None:
    state = snapshot_from_ha_states([ha_state("sensor.p", "500")])

    def rendered(readout: Readout) -> list[tuple[float, float]]:
        element = LineElement(
            "l",
            ((0.0, 0.0), (200.0, 0.0)),
            bind={"rate": EntityRef("sensor.p")},
            flow=FlowSpec("rate", 10),
            readouts=(readout,),
        )
        return points(render_element(element, state, LCD))

    assert rendered(Readout("rate", along=0.2))[0] == (55, 9)  # below, under the readout
    assert rendered(Readout("rate", along=0.2, anchor=Anchor.BOTTOM_CENTER))[0] == (55, -9)


def test_default_threshold_shows_any_nonzero_rate() -> None:
    def svg(rate: str) -> str:
        element = LineElement(
            "water",
            ((0.0, 0.0), (200.0, 0.0)),
            bind={"rate": EntityRef("sensor.water_flow")},
            flow=FlowSpec(),  # what 'flow: true' gives
        )
        return render_element(
            element, snapshot_from_ha_states([ha_state("sensor.water_flow", rate)]), LCD
        )

    assert "<polygon" in svg("2.5")  # 2.5 gal/min flows
    assert "<polygon" in svg("-0.5")  # so does a small reverse flow
    assert "<polygon" not in svg("0")


class TestConditionFlow:
    """Flow from a condition, for lines with nothing to measure (ducts, gas, irrigation)."""

    def duct(self, action: str, reverse: bool = False) -> str:
        running = AnyOf.single(
            Condition(EntityRef("climate.main", "hvac_action"), Op.IN, ("heating", "cooling"))
        )
        element = LineElement(
            "duct", ((0.0, 0.0), (200.0, 0.0)), flow=FlowSpec(when=running, reverse=reverse)
        )
        state = snapshot_from_ha_states([ha_state("climate.main", "heat", hvac_action=action)])
        return render_element(element, state, LCD)

    def test_flows_while_the_condition_holds(self) -> None:
        assert "<polygon" in self.duct("heating")
        assert "<polygon" not in self.duct("idle")
        assert f'stroke="{LCD.color(Status.ACTIVE)}"' in self.duct("cooling")  # solid core

    def test_reverse(self) -> None:
        forward, backward = points(self.duct("heating")), points(self.duct("heating", True))
        assert forward[0][0] > forward[1][0] and backward[0][0] < backward[1][0]

    def test_arrow_avoids_a_service_tag(self) -> None:
        state = snapshot_from_ha_states([ha_state("sensor.p", "5")])
        element = LineElement(
            "gas",
            ((0.0, 0.0), (200.0, 0.0)),
            bind={"rate": EntityRef("sensor.p")},
            flow=FlowSpec(),
            tag=LineTag("GAS", 0.25),
        )
        tip_x = points(render_element(element, state, LCD))[0][0]
        assert tip_x > 150  # in the other half from the tag at a quarter


def test_condition_flow_config(tmp_path: Path) -> None:
    page = tmp_path / "p.yaml"
    body = textwrap.dedent(
        """\
        page: p
        title: P
        canvas: {width: 100, height: 100}
        elements:
          - id: duct
            type: line
            from: [0, 0]
            to: [10, 0]
            flow:
              when: [{entity: climate.main, attribute: hvac_action, eq: heating}]
              reverse: true
        """
    )
    page.write_text(body)
    [duct] = load_page(page, Defs()).elements
    assert isinstance(duct, LineElement) and duct.flow is not None
    assert duct.flow.when is not None and duct.flow.reverse
    page.write_text(body.replace("reverse: true", "threshold: 5"))
    with pytest.raises(ConfigError, match="flow from a condition has no 'from' or 'threshold'"):
        load_page(page, Defs())


class TestTwoWay:
    """A two-way line (download and upload): one harpoon per direction, one per side."""

    def link(
        self, rx: str, tx: str, reverse: bool = False, readouts: tuple[Readout, ...] = ()
    ) -> str:
        element = LineElement(
            "uplink",
            ((0.0, 0.0), (200.0, 0.0)),
            bind={"rate": EntityRef("sensor.rx"), "rate_back": EntityRef("sensor.tx")},
            flow=FlowSpec(threshold=1, reverse=reverse, back="rate_back"),
            readouts=readouts
            or (Readout("rate", format="data_rate"), Readout("rate_back", format="data_rate")),
        )
        state = snapshot_from_ha_states([ha_state("sensor.rx", rx), ha_state("sensor.tx", tx)])
        return render_element(element, state, LCD)

    def harpoons(self, svg: str) -> list[tuple[str, str]]:
        """(side, direction) of each harpoon: above/below, and which way its tip points."""
        out = []
        for match in re.finditer(r'<polygon points="([^"]+)"', svg):
            (tx, ty), (bx, _), _ = (tuple(map(float, p.split(","))) for p in match[1].split())
            out.append(("above" if ty < 0 else "below", "forward" if tx > bx else "back"))
        return out

    def test_download_above_upload_below(self) -> None:
        assert self.harpoons(self.link("412", "38")) == [("above", "forward"), ("below", "back")]

    def test_each_direction_on_its_own(self) -> None:
        assert self.harpoons(self.link("412", "0.5")) == [("above", "forward")]  # under threshold
        upload = self.link("0", "38")
        assert self.harpoons(upload) == [("below", "back")]
        assert f'stroke="{LCD.color(Status.ACTIVE)}"' in upload  # solid core: something flows
        assert self.harpoons(self.link("0", "0")) == []
        assert self.harpoons(self.link("-412", "0")) == [("above", "forward")]  # a magnitude

    def test_reverse_swaps_the_directions(self) -> None:
        assert self.harpoons(self.link("412", "38", reverse=True)) == [
            ("above", "back"),
            ("below", "forward"),
        ]

    def test_readouts_sit_outside_their_harpoons(self) -> None:
        svg = self.link("412", "38")
        texts = dict(
            (text, float(y))
            for y, text in re.findall(r'<text x="[^"]+" y="([^"]+)"[^>]*>([^<]+)<', svg)
        )
        reach = 5 + 10 * (0.4 + 0.8)  # half the pipe, plus the harpoon's gap and barb
        assert texts["412 Mb/s"] < -reach and texts["38 Mb/s"] > reach

    def test_an_upload_readout_first_still_puts_download_above(self) -> None:
        readouts = (Readout("rate_back", format="data_rate"), Readout("rate", format="data_rate"))
        svg = self.link("412", "38", readouts=readouts)
        assert self.harpoons(svg) == [("above", "forward"), ("below", "back")]

    def test_config(self, tmp_path: Path) -> None:
        page = tmp_path / "p.yaml"
        body = textwrap.dedent(
            """\
            page: p
            title: P
            canvas: {width: 100, height: 100}
            elements:
              - id: uplink
                type: line
                from: [0, 0]
                to: [10, 0]
                bind: {rate: sensor.rx, rate_back: sensor.tx}
                flow: {threshold: 1}
            """
        )
        page.write_text(body)
        [uplink] = load_page(page, Defs()).elements
        assert isinstance(uplink, LineElement) and uplink.flow is not None
        assert uplink.flow.back == "rate_back"
        page.write_text(body.replace("{threshold: 1}", "{when: [{entity: sensor.x, eq: on}]}"))
        with pytest.raises(ConfigError, match=r"a condition can't drive a two-way line"):
            load_page(page, Defs())
