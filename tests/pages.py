"""Minimal Electrical page used by tests (generic entity ids, no house specifics)."""

from mfdhome.conditions import ChannelRef, Thresholds, state_map_rules
from mfdhome.model import (
    EntityRef,
    FlowSpec,
    LineElement,
    Page,
    Readout,
    Status,
    StatusSpec,
    SymbolElement,
    TextElement,
)

BUS = (500.0, 300.0)
POWER_READOUT = (Readout("power", format="power", absolute=True),)


def _line(id_: str, points: tuple[tuple[float, float], ...], entity: str) -> LineElement:
    return LineElement(
        id_,
        points,
        bind={"power": EntityRef(entity)},
        readouts=POWER_READOUT,
        flow=FlowSpec(),
    )


def electrical_page() -> Page:
    """Solar and battery feed a bus; the bus feeds loads and ties to grid via a breaker."""
    return Page(
        id="electrical",
        title="Electrical",
        width=1000,
        height=600,
        elements=(
            TextElement("title", (80, 40), "ELEC"),
            TextElement("solar_label", (500, 60), "SOLAR"),
            _line("solar", ((500, 80), BUS), "sensor.solar_power"),
            TextElement("battery_label", (200, 225), "BATT"),
            SymbolElement(
                "battery",
                "battery",
                (200, 300),
                bind={
                    "level": EntityRef("sensor.battery_soc"),
                    "power": EntityRef("sensor.battery_power"),
                },
                status=StatusSpec(
                    Thresholds(warning_low=10, caution_low=25).rules(ChannelRef("level"))
                ),
                readouts=(
                    Readout("level", format="percent"),
                    Readout("power", format="power"),
                ),
            ),
            # Positive battery power = discharging into the bus.
            _line("battery_feed", ((230, 300), BUS), "sensor.battery_power"),
            LineElement("bus_tie", (BUS, (630, 300))),
            SymbolElement(
                "main_breaker",
                "breaker",
                (650, 300),
                bind={"state": EntityRef("switch.main_breaker")},
                status=StatusSpec(
                    state_map_rules(
                        ChannelRef("state"),
                        {"on": Status.NORMAL, "closed": Status.NORMAL},
                        default=Status.CAUTION,
                    )
                ),
            ),
            # Positive grid power = import (grid -> house); negative = export.
            _line("grid", ((880, 300), (670, 300)), "sensor.grid_power"),
            TextElement("grid_label", (930, 307), "GRID"),
            _line("loads", (BUS, (500, 500)), "sensor.load_power"),
            TextElement("loads_label", (500, 530), "LOADS"),
        ),
    )
