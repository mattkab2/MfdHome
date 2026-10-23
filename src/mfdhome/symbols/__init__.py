"""I&C symbol primitives. Each returns an SVG fragment string."""

from mfdhome.symbols.battery import battery
from mfdhome.symbols.breaker import breaker
from mfdhome.symbols.line import Flow, line
from mfdhome.symbols.registry import (
    LINE_CHANNELS,
    LINE_NUMERIC,
    REGISTRY,
    SymbolInput,
    SymbolSpec,
    get_symbol,
    line_primary,
)

__all__ = [
    "LINE_CHANNELS",
    "LINE_NUMERIC",
    "REGISTRY",
    "Flow",
    "SymbolInput",
    "SymbolSpec",
    "battery",
    "breaker",
    "get_symbol",
    "line",
    "line_primary",
]
