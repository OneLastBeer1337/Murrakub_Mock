"""
Load projection between epochs -- and the one runtime mechanism the paper actually numbers.

Section 3.4: "The state of the previous epochs is used to project the load for each workflow in
the next epoch." That says *what* but not *how*.

Section 4.7 supplies the how, verbatim: "We use an exponentially weighted moving average (EWMA)
[18], with **alpha = 0.5**, to predict workload demand at every epoch."

So unlike `mu_m` (A42), `tau_{w,cost}` (A67) and the auto-scaling ratios (Q35), the projector is
**paper-sourced and not invented**. It lives in the evaluation section rather than the design,
which is worth noting, but the number is the paper's.

A90 -- TWO ALPHAS, AND THEY ARE NOT THE SAME ALPHA. A.5 p.586: "alpha: Unified buffer factor
(default 1.15)". Section 4.7: EWMA "alpha = 0.5". The auto-scaler needs both at once. Nothing in
`/execution/` may be called a bare `alpha`; this module uses `ewma_alpha` and the buffer keeps
its A.5 name. A test asserts no bare `alpha` identifier exists in the package, because a single
shadowed name would silently corrupt either the demand buffer or the forecast.

REPLAY IS NOT PREDICTION. M3's arrivals come from Figure 19's 24-hour Azure traces. Feeding the
true next-epoch value into the optimizer would reproduce the paper's SETUP while inventing a
perfect oracle it never claims. `project()` takes only epochs strictly before the one being
predicted, and its signature enforces it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

EWMA_ALPHA: float = 0.5
"""Section 4.7, verbatim. Paper-sourced, not invented."""


class LookaheadError(ValueError):
    """The projector was offered data from the epoch it is supposed to predict, or later."""


@dataclass
class EwmaProjector:
    """`s_t = a * x_t + (1 - a) * s_{t-1}`, seeded on the first observation.

    Past-only by construction: `project(history, target_epoch)` raises if `history` contains any
    epoch index >= `target_epoch`.
    """

    ewma_alpha: float = EWMA_ALPHA
    state: dict[str, float] = field(default_factory=dict)

    def observe(self, series: str, value: float) -> float:
        prev = self.state.get(series)
        self.state[series] = value if prev is None else (
            self.ewma_alpha * value + (1.0 - self.ewma_alpha) * prev
        )
        return self.state[series]

    def project(
        self,
        series: str,
        history: Sequence[tuple[int, float]],
        target_epoch: int,
    ) -> float:
        """Forecast `series` for `target_epoch` from strictly-earlier observations."""
        future = [e for e, _v in history if e >= target_epoch]
        if future:
            raise LookaheadError(
                f"projection for epoch {target_epoch} was given epochs {sorted(future)}; "
                "a projector that can see the epoch it predicts is an oracle, and Section 4.7 "
                "describes an EWMA over PAST state"
            )
        if not history:
            return 0.0
        self.state.pop(series, None)
        value = 0.0
        for _epoch, observation in sorted(history):
            value = self.observe(series, observation)
        return value


def under_prediction(projected: float, actual: float) -> float:
    """Figure 13b's quantity: how much the forecast missed the real load by, as a fraction.

    Positive means the projector UNDER-predicted, which is the direction that causes dropped
    requests. Computed from the true trace for REPORTING only -- feeding it back would make the
    projector an oracle, and a test asserts it never reaches `project()`.
    """
    if actual <= 0:
        return 0.0
    return (actual - projected) / actual


__all__ = ["EWMA_ALPHA", "EwmaProjector", "LookaheadError", "under_prediction"]
