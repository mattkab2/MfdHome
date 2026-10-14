"""Readout value formatting."""

from __future__ import annotations

from mfdhome.conditions.values import Value

NO_DATA = "---"

#: Named formatters accepted in readouts.
FORMATS = frozenset({"power", "percent", "number", "raw"})


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


def _trim(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def format_power(value: float, unit: str | None) -> str:
    """Format power; W and kW inputs are shown as W below 1000 and kW above."""
    unit = unit or "W"
    if unit.lower() == "kw":
        value, unit = value * 1000, "W"
    if unit == "W" and abs(value) >= 1000:
        return f"{value / 1000:.1f} kW"
    return f"{value:.0f} {unit}"


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
        case "percent":
            return f"{number:.0f}%"
        case "number":
            return _trim(number) + (f" {unit}" if unit else "")
        case _:
            return fmt.format(number)
