"""Element status resolution."""

from __future__ import annotations

from mfdhome.conditions.evaluate import SEVERITY_ORDER, EvalContext, highest_match
from mfdhome.conditions.model import ChannelRef
from mfdhome.model.binding import Status
from mfdhome.model.page import StatusSpec


def element_status(
    spec: StatusSpec,
    ctx: EvalContext,
    primary: str,
    numeric: bool = False,
    alert_status: Status | None = None,
) -> Status:
    """Resolve an element's status.

    1. The most severe of the matching rules and ``alert_status`` (from the
       element's referenced alerts) wins, so an explicit rule (even one about
       missing data) beats the no-data display.
    2. Otherwise, a bound primary channel with no data gives ``UNAVAILABLE``.
       For a ``numeric`` primary, a non-numeric value also counts as no data.
    3. Otherwise ``NORMAL``.
    """
    candidates = [s for s in (highest_match(spec.rules, ctx), alert_status) if s is not None]
    if candidates:
        return max(candidates, key=SEVERITY_ORDER.index)
    if primary in ctx.channels:
        value = ctx.value(ChannelRef(primary))
        if (value.number if numeric else value.raw) is None:
            return Status.UNAVAILABLE
    return Status.NORMAL
