"""
`lambda^peak_{w,s}` and `lambda^avg_{w,s}` -- arrival rates, per optimization epoch.

Section 4.1 (p.576), verbatim: "Since no publicly available traces exist for production agentic
workflow serving, we approximate workload arrivals using LLM serving traces collected over a
24-hour period in May 2024 from Azure's LLM inference service for chat and coding applications
[78] (Section A.4)... We map the chat requests from the trace to the video Q/A workflow and
coding requests to the code generation workflow."

A.4 (p.587): "We use a subset of LLM serving traces released by Azure [78] from 08:00 05/15/2024
to 08:00 05/16/2024 shown in Figure 19."

Section 3.4 (p.575) fixes the epoch: "The optimizer runs in the background after every
optimization epoch, in our case every 60 minutes." So there are 24 epochs, each yielding one
`lambda^peak` and one `lambda^avg` per (workflow, SLO).

UNITS. Figure 19's y-axis is req/min. A.5's capacity constraint eq. (3) is
`mu_m * SUM x^peak * t_c <= n_m * theta_m` with `t_c` in tokens/request and `theta_m` in
tokens/second, so `x` -- and therefore `lambda` -- must be REQUESTS PER SECOND. We divide by 60
once, here, and record the unit on every value so the conversion cannot happen twice.

WHAT PEAK MEANS HERE, AND WHY IT IS NOT THE TRACE MAXIMUM. Within one 60-minute epoch the trace
has roughly 55 samples. `lambda^peak` is the maximum over that epoch and `lambda^avg` the mean
over it -- both are properties OF THE EPOCH, not of the day. Taking the day's maximum would make
eq. (1) provision the whole 24 h for the busiest hour, which is exactly the static over-provision
Murakkab argues against (Table 2's LangGraph row).

THE SLO SPLIT IS THE PAPER'S, NOT OURS. The trace says nothing about SLOs; Section 4.2 (p.576)
runs "all requests have the same SLO for each experiment" and Section 4.3 (p.576) splits "70%
requests to be high-accuracy and 30% requests to low-latency, both with *good* tier". A `SloMix`
supplies the split and the arrival builder applies it, so the trace and the SLO assumption never
get conflated.
"""

from __future__ import annotations

import math
from typing import Final, Mapping, Sequence

from optimization.profiles.provenance import Citation, Measured, Provenance
from optimization.profiles.schema import ArrivalPattern, SloMix
from optimization.profiles.sources.figures_digitized import (
    FIG_19_CHAT,
    FIG_19_CODING,
    FIG_19_SERIES_TO_WORKFLOW,
)

FIG19 = Citation(version="BOTH", figure="19", page=587)
SEC_3_4 = Citation(
    version="BOTH",
    section="3.4",
    page=575,
    quote=(
        "The optimizer runs in the background after every optimization epoch, in our case every "
        "60 minutes."
    ),
)

EPOCH_MINUTES: Final[int] = 60
EPOCHS: Final[int] = 24
SECONDS_PER_MINUTE: Final[float] = 60.0

TRACE_START_LOCAL: Final[str] = "2024-05-15T08:00"
"""A.4 (p.587). t=0 is 08:00, NOT midnight -- every epoch index here is trace-relative, so a
diurnal reading of epoch 0 is wrong by 8 hours unless shifted deliberately."""

TRACES: Final[Mapping[str, tuple[tuple[float, float], ...]]] = {
    "chat": FIG_19_CHAT,
    "coding": FIG_19_CODING,
}


def _epoch_samples(trace: Sequence[tuple[float, float]], epoch: int) -> list[float]:
    lo, hi = epoch, epoch + 1
    return [v for t, v in trace if lo <= t < hi]


def epoch_statistics(series: str, epoch: int) -> tuple[float, float, int]:
    """`(peak, avg, n_samples)` in requests per MINUTE for one series and epoch."""
    samples = _epoch_samples(TRACES[series], epoch)
    if not samples:
        raise ValueError(f"{series}: epoch {epoch} has no samples")
    return max(samples), sum(samples) / len(samples), len(samples)


def build_arrivals(
    mix: SloMix | None = None,
    epochs: Sequence[int] | None = None,
) -> tuple[ArrivalPattern, ...]:
    """One `ArrivalPattern` per (workflow, SLO type, tier, epoch).

    `mix` defaults to Section 4.3's 70/30 split, the only multi-SLO mix the paper states.
    """
    mix = mix or SloMix.section_4_3()
    wanted = list(epochs) if epochs is not None else list(range(EPOCHS))
    out: list[ArrivalPattern] = []

    for series, workflow in FIG_19_SERIES_TO_WORKFLOW.items():
        for epoch in wanted:
            peak_rpm, avg_rpm, n = epoch_statistics(series, epoch)
            for (slo_type, tier), share in mix.shares.items():
                peak = peak_rpm * share / SECONDS_PER_MINUTE
                avg = avg_rpm * share / SECONDS_PER_MINUTE
                note = (
                    f"Figure 19 '{series}' -> {workflow} (Section 4.1 p.576); epoch {epoch} "
                    f"({n} samples) of 24; share {share:g} from mix '{mix.name}'; "
                    f"req/min -> req/s"
                )
                out.append(
                    ArrivalPattern(
                        workflow_id=workflow,
                        slo=(slo_type, tier),
                        epoch=epoch,
                        lam_peak=Measured(
                            value=peak,
                            unit="req/s",
                            provenance=Provenance.PAPER_FIGURE_READ,
                            cite=FIG19,
                            lo=peak * 0.97,
                            hi=peak * 1.03,
                            note=f"epoch MAXIMUM. {note}",
                        ),
                        lam_avg=Measured(
                            value=avg,
                            unit="req/s",
                            provenance=Provenance.PAPER_FIGURE_READ,
                            cite=FIG19,
                            lo=avg * 0.97,
                            hi=avg * 1.03,
                            note=f"epoch MEAN. {note}",
                        ),
                    )
                )
    return tuple(out)


def trace_summary() -> dict[str, dict[str, float]]:
    """Day-level summary, for `PROFILES.md` and for sanity-checking against Figure 19 by eye."""
    out: dict[str, dict[str, float]] = {}
    for series, trace in TRACES.items():
        values = [v for _t, v in trace]
        peaks = [epoch_statistics(series, e)[0] for e in range(EPOCHS)]
        avgs = [epoch_statistics(series, e)[1] for e in range(EPOCHS)]
        out[series] = {
            "samples": float(len(values)),
            "min_rpm": min(values),
            "max_rpm": max(values),
            "mean_rpm": sum(values) / len(values),
            "peak_to_mean_ratio": max(values) / (sum(values) / len(values)),
            "busiest_epoch": float(max(range(EPOCHS), key=lambda e: peaks[e])),
            "quietest_epoch": float(min(range(EPOCHS), key=lambda e: avgs[e])),
            "epoch_peak_spread": max(peaks) / max(min(peaks), 1e-9),
        }
    return out


__all__ = [
    "EPOCHS",
    "EPOCH_MINUTES",
    "TRACES",
    "TRACE_START_LOCAL",
    "build_arrivals",
    "epoch_statistics",
    "trace_summary",
]
