"""Time-averaging numeric states for slow-refreshing displays."""

from datetime import timedelta

from mfdhome.model import snapshot_from_ha_states
from mfdhome.model.state import AveragingPolicy, StateSnapshot
from mfdhome.sources.averaging import Samples, averaged
from tests.support import T0, ha_state

MEASURED = {"state_class": "measurement", "unit_of_measurement": "W"}
FIVE_MIN = timedelta(minutes=5)


def snap(power: str, **attributes: object) -> StateSnapshot:
    return snapshot_from_ha_states(
        [ha_state("sensor.load_power", power, **(attributes or MEASURED))]
    )


def feed(samples: Samples, *steps: tuple[float, str]) -> None:
    for seconds, power in steps:
        samples.record(snap(power), T0 + timedelta(seconds=seconds))


def load(state: StateSnapshot) -> str:
    return state["sensor.load_power"].state


def test_a_short_spike_is_averaged_away() -> None:
    samples = Samples(FIVE_MIN)
    # 500 W, a 3 kW kettle for 30 s, then 500 W again; rendered 5 minutes in.
    feed(samples, (0, "500"), (120, "3000"), (150, "500"))
    now = T0 + FIVE_MIN
    shown = averaged(snap("500"), samples, FIVE_MIN, now, AveragingPolicy())
    assert float(load(shown)) == 750.0  # (270 s x 500 + 30 s x 3000) / 300 s


def test_the_value_before_the_window_counts_from_its_start() -> None:
    samples = Samples(FIVE_MIN)
    feed(samples, (0, "1000"), (540, "2000"))  # 1000 W for 9 minutes, then 2000 W
    now = T0 + timedelta(minutes=10)
    shown = averaged(snap("2000"), samples, FIVE_MIN, now, AveragingPolicy())
    assert float(load(shown)) == 1200.0  # 4 min at 1000, 1 min at 2000


def test_gaps_are_left_out_but_no_data_now_stays_no_data() -> None:
    samples = Samples(FIVE_MIN)
    feed(samples, (0, "400"), (60, "unavailable"), (240, "600"))
    now = T0 + FIVE_MIN
    shown = averaged(snap("600"), samples, FIVE_MIN, now, AveragingPolicy())
    assert float(load(shown)) == 500.0  # 60 s at 400 and 60 s at 600; the gap is skipped
    feed(samples, (300, "unavailable"))
    dead = averaged(snap("unavailable"), samples, FIVE_MIN, now, AveragingPolicy())
    assert load(dead) == "unavailable"  # never hidden behind an old average


def test_only_measurements_unless_overridden() -> None:
    samples = Samples(FIVE_MIN)
    total = {"state_class": "total_increasing", "unit_of_measurement": "kWh"}
    for seconds, value in ((0, "10"), (150, "20")):
        samples.record(snap(value, **total), T0 + timedelta(seconds=seconds))
    now = T0 + FIVE_MIN
    assert load(averaged(snap("20", **total), samples, FIVE_MIN, now, AveragingPolicy())) == "20"
    forced = AveragingPolicy({"sensor.load_power": True})
    assert float(load(averaged(snap("20", **total), samples, FIVE_MIN, now, forced))) == 15.0
    off = AveragingPolicy({"sensor.load_power": False})
    feed(samples, (200, "900"))
    assert load(averaged(snap("900"), samples, FIVE_MIN, now, off)) == "900"


def test_text_states_and_attributes_pass_through() -> None:
    samples = Samples(FIVE_MIN)
    climate = ha_state("climate.main", "heat", state_class="measurement", temperature=70)
    samples.record(snapshot_from_ha_states([climate]), T0)
    state = snapshot_from_ha_states([{**climate, "attributes": {"temperature": 72}}])
    shown = averaged(state, samples, FIVE_MIN, T0 + FIVE_MIN, AveragingPolicy())
    assert shown["climate.main"] == state["climate.main"]


def test_nothing_recorded_yet_shows_the_reading() -> None:
    shown = averaged(snap("640"), Samples(FIVE_MIN), FIVE_MIN, T0, AveragingPolicy())
    assert load(shown) == "640"


def test_samples_keep_only_changes_within_reach() -> None:
    samples = Samples(FIVE_MIN, entities={"sensor.load_power"})
    for minute in range(20):
        feed(samples, (minute * 60, "500"))  # unchanged: one sample
    assert len(samples._series["sensor.load_power"]) == 1
    for second in range(0, 1200, 10):
        feed(samples, (1200 + second, str(second)))
    series = samples._series["sensor.load_power"]
    assert series[0][0] <= T0 + timedelta(seconds=2390) - FIVE_MIN < series[1][0]
    other = snapshot_from_ha_states([ha_state("sensor.other", "1", **MEASURED)])
    samples.record(other, T0)
    assert "sensor.other" not in samples._series  # not one the config uses
