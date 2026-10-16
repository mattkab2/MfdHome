"""The flow arrow: a harpoon beside the line, level with its readout, clear of core and labels."""

import re

from mfdhome.layout import Anchor
from mfdhome.model import EntityRef, FlowSpec, LineElement, Readout, Status, snapshot_from_ha_states
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
