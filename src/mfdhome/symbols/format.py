"""Readout value formatting."""

from __future__ import annotations

from mfdhome.conditions.values import Value
from mfdhome.symbols import svg

NO_DATA = "---"

#: Named formatters accepted in readouts.
FORMATS = frozenset({"power", "data_rate", "percent", "number", "raw"})


def is_valid_format(fmt: str) -> bool:
    """Whether ``fmt`` is a named formatter or a format string that accepts one number."""
    if fmt in FORMATS:
        return True
    if "{" not in fmt:
        return False
    try:
        fmt.format(1.0)
    except ValueError, TypeError, IndexError, KeyError, AttributeError:
        return False
    return True


def format_power(value: float, unit: str | None) -> str:
    """Format power; W and kW inputs are shown as W below 1000 and kW above."""
    unit = unit or "W"
    if unit.lower() == "kw":
        value, unit = value * 1000, "W"
    if unit == "W" and abs(value) >= 1000:
        return f"{value / 1000:.1f} kW"
    return f"{value:.0f} {unit}"


#: Home Assistant's data rate units, in bits per second. Case matters: B is bytes.
DATA_RATE_UNITS = {
    "bit/s": 1.0,
    "kbit/s": 1e3,
    "Mbit/s": 1e6,
    "Gbit/s": 1e9,
    "B/s": 8.0,
    "kB/s": 8e3,
    "MB/s": 8e6,
    "GB/s": 8e9,
    "KiB/s": 8 * 2.0**10,
    "MiB/s": 8 * 2.0**20,
    "GiB/s": 8 * 2.0**30,
}
_BIT_RATE_SCALES = ((1e9, "Gb/s"), (1e6, "Mb/s"), (1e3, "kb/s"))


def format_data_rate(value: float, unit: str | None) -> str:
    """Format a data rate in bits per second, scaled to b/s, kb/s, Mb/s or Gb/s.

    Any of Home Assistant's data rate units is converted (no unit: Mbit/s);
    one decimal below 10 (dropped when zero), whole numbers above.
    """
    factor = DATA_RATE_UNITS.get(unit or "Mbit/s")
    if factor is None:
        return f"{svg.fmt(value)} {unit}"
    bits = value * factor
    scale, label = next(((f, u) for f, u in _BIT_RATE_SCALES if abs(bits) >= f), (1.0, "b/s"))
    scaled = bits / scale
    text = f"{scaled:.1f}".removesuffix(".0") if abs(scaled) < 10 else f"{scaled:.0f}"
    return f"{text} {label}"


def format_value(value: Value, fmt: str, unit: str | None = None, absolute: bool = False) -> str:
    """Format a bound value for display; missing or non-numeric data shows ``---``.

    ``unit`` overrides the entity's own unit of measurement.
    """
    if value.raw is None:
        return NO_DATA
    if fmt == "raw":
        return str(value.raw)
    number = value.number
    if number is None:
        return NO_DATA
    if absolute:
        number = abs(number)
    unit = unit if unit is not None else value.unit
    match fmt:
        case "power":
            return format_power(number, unit)
        case "data_rate":
            return format_data_rate(number, unit)
        case "percent":
            return f"{number:.0f}%"
        case "number":
            return svg.fmt(number) + (f" {unit}" if unit else "")
        case _:
            return fmt.format(number)
