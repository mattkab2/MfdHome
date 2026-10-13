"""Minimal Electrical page used by tests (generic entity ids, no house specifics)."""

from mfdhome.model import (
    BatteryElement,
    BreakerElement,
    EntityRef,
    LineElement,
    Page,
    TextElement,
)

BUS = (500.0, 300.0)


def electrical_page() -> Page:
    """Solar and battery feed a bus; the bus feeds loads and ties to grid via a breaker."""
    return Page(
        id="electrical",
        title="Electrical",
        width=1000,
        height=600,
        elements=(
            TextElement("title", 80, 40, "ELEC"),
            TextElement("solar_label", 500, 60, "SOLAR"),
            LineElement("solar", ((500, 80), BUS), power=EntityRef("sensor.solar_power")),
            TextElement("battery_label", 200, 225, "BATT"),
            BatteryElement(
                "battery",
                200,
                300,
                soc=EntityRef("sensor.battery_soc"),
                power=EntityRef("sensor.battery_power"),
            ),
            # Positive battery power = discharging into the bus.
            LineElement("battery_feed", ((230, 300), BUS), power=EntityRef("sensor.battery_power")),
            LineElement("bus_tie", (BUS, (630, 300))),
            BreakerElement("main_breaker", 650, 300, state=EntityRef("switch.main_breaker")),
            # Positive grid power = import (grid -> house); negative = export.
            LineElement("grid", ((880, 300), (670, 300)), power=EntityRef("sensor.grid_power")),
            TextElement("grid_label", 930, 307, "GRID"),
            LineElement("loads", (BUS, (500, 500)), power=EntityRef("sensor.load_power")),
            TextElement("loads_label", 500, 530, "LOADS"),
        ),
    )
