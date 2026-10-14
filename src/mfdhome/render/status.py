"""Element status resolution."""

from __future__ import annotations

from mfdhome.conditions.evaluate import EvalContext, highest_match
from mfdhome.conditions.model import ChannelRef
from mfdhome.model.binding import Status
from mfdhome.model.page import StatusSpec


def element_status(
    spec: StatusSpec, ctx: EvalContext, primary: str, numeric: bool = False
) -> Status:
    """Resolve an element's status.

    1. The most severe matching rule wins, so an explicit rule (even one about
       missing data) beats the no-data display.
    2. Otherwise, a bound primary channel with no data gives ``UNAVAILABLE``.
       For a ``numeric`` primary, a non-numeric value also counts as no data.
    3. Otherwise ``NORMAL``.
    """
    matched = highest_match(spec.rules, ctx)
    if matched is not None:
        return matched
    if primary in ctx.channels:
        value = ctx.value(ChannelRef(primary))
        if (value.number if numeric else value.raw) is None:
            return Status.UNAVAILABLE
    return Status.NORMAL
