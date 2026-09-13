"""
Auto-scaling thresholds -- the one mechanism Section 3.4 actually specifies.

    "We set thresholds for auto-scaling based on the performance-throughput characteristic in
    executor profiles."

That sentence points at something real and already built: `ModelProfile.curve`, the sequence of
`LoadPoint`s digitized from Figure 3, each carrying a throughput and the TPOT/TTFT observed at
that throughput. The "performance-throughput characteristic" IS that curve.

What the sentence does NOT give is a number. No ratio, no window, no hysteresis. So the mechanism
is paper-sourced and the constants are `[INVENTED]` (Q35), defaulted, swept, and never quoted
without the ratio beside them.

WHAT THE THRESHOLD SHOULD BE. Section 3.3.1's capacity constraint says load must stay "within the
throughput envelope at which the profile satisfies the latency SLO". So the meaningful ceiling is
not `theta_m` flat -- it is the largest throughput whose TPOT still lets eq. (5) come in under
`tau`:

    theta^slo(m, tau, t_c)  =  max { L.throughput : L.ttft + t_c * L.tpot <= tau }

Scale out at 80% of that, scale in below 40%, both with hysteresis. Note this makes the threshold
depend on `tau` and on `t_c` -- i.e. on the SLO tier and the workflow configuration -- which is
exactly the SLO-dependence the prose implies and A.5's constant `theta_m` cannot express (A37b).

A86 -- THE RULE IS UNEVALUABLE FOR SECTION 3.4'S OWN EXAMPLE. The formula needs `ttft` at each
load point. Llava-OneVision-7B has no TTFT anywhere in either version (A35/A36) -- and it is the
model Section 3.4 uses to motivate the auto-scaler in the first place ("600 and 1200 tokens in
the 50th and 99th percentile"). For those 7 profiles we fall back to the KNEE policy already in
M3 and MARK the value, never imputing a TTFT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from optimization.profiles.provenance import Measured, Unavailable
from optimization.profiles.schema import LoadPoint, ModelProfile, OperatingPointPolicy

SCALE_OUT_RATIO: float = 0.80
SCALE_IN_RATIO: float = 0.40
HYSTERESIS_WINDOWS: int = 3
"""All three are [INVENTED] -- Section 3.4 gives no numbers (Q35). Swept, never quoted bare.

`SCALE_IN_RATIO` is deliberately far below `SCALE_OUT_RATIO`: with a 20-minute provisioning
delay (A87), releasing an instance you will need again in ten minutes is far more expensive than
holding it, so the band is wide on purpose.
"""


@dataclass(frozen=True)
class ScaleThresholds:
    """The throughput band for one `(model, tau, t_c)`, and where it came from."""

    model_id: str
    theta_slo_tokens_s: float
    scale_out_at: float
    scale_in_at: float
    derived_from: str
    is_fallback: bool = False
    """True when the SLO-aware rule could not be evaluated and KNEE was used instead (A86)."""

    def decide(self, observed_tokens_s: float) -> str:
        if self.theta_slo_tokens_s <= 0:
            return "hold"
        if observed_tokens_s >= self.scale_out_at:
            return "out"
        if observed_tokens_s <= self.scale_in_at:
            return "in"
        return "hold"


def _usable(curve: Sequence[LoadPoint]) -> list[LoadPoint]:
    return [p for p in curve if isinstance(p.throughput, Measured)]


def theta_under_slo(
    profile: ModelProfile,
    tau_s: float | None,
    tokens_per_request: float,
) -> tuple[float, str, bool]:
    """The largest profiled throughput at which eq. (5) still meets `tau`.

    Returns `(throughput, provenance_note, is_fallback)`.

    This is Section 3.3.1's "throughput envelope at which the profile satisfies the latency SLO",
    computed against the curve rather than assumed constant. When `tau` is None -- an accuracy
    tier, where A68 makes the latency filter inactive -- there is no latency ceiling at all, so
    the envelope is the curve maximum and we say so.
    """
    points = _usable(profile.curve)
    if not points:
        return 0.0, "no usable load point", True

    if tau_s is None:
        best = max(points, key=lambda p: float(p.throughput.value))
        return (
            float(best.throughput.value),
            "accuracy tier: A68 leaves the latency filter inactive, so no latency ceiling "
            "exists and the envelope is the curve maximum",
            False,
        )

    feasible = []
    for p in points:
        if not isinstance(p.tpot_p90, Measured) or not isinstance(p.ttft_p90, Measured):
            continue
        if float(p.ttft_p90.value) + tokens_per_request * float(p.tpot_p90.value) <= tau_s:
            feasible.append(p)

    if feasible:
        best = max(feasible, key=lambda p: float(p.throughput.value))
        return (
            float(best.throughput.value),
            f"largest curve point meeting eq.(5) <= tau={tau_s:g}s at t_c={tokens_per_request:g}",
            False,
        )

    # A86: either no TTFT exists (7 profiles, incl. Llava-OneVision-7B) or no point meets tau.
    knee = profile.theta(OperatingPointPolicy.KNEE)
    if isinstance(knee, Unavailable):
        return 0.0, "no point meets tau and KNEE is unavailable", True
    return (
        float(knee.value),
        "A86 FALLBACK: the SLO-aware envelope is unevaluable (no TTFT reported, or no curve "
        "point meets tau); using M3's KNEE policy. NOT a profiled SLO envelope",
        True,
    )


def thresholds_for(
    profile: ModelProfile,
    tau_s: float | None,
    tokens_per_request: float,
    scale_out_ratio: float = SCALE_OUT_RATIO,
    scale_in_ratio: float = SCALE_IN_RATIO,
) -> ScaleThresholds:
    theta, note, fallback = theta_under_slo(profile, tau_s, tokens_per_request)
    return ScaleThresholds(
        model_id=str(profile.key),
        theta_slo_tokens_s=theta,
        scale_out_at=theta * scale_out_ratio,
        scale_in_at=theta * scale_in_ratio,
        derived_from=note,
        is_fallback=fallback,
    )


__all__ = [
    "HYSTERESIS_WINDOWS",
    "SCALE_IN_RATIO",
    "SCALE_OUT_RATIO",
    "ScaleThresholds",
    "theta_under_slo",
    "thresholds_for",
]
