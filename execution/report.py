"""
Execution reporting -- and the caveat gate, carried forward from M4.

M4 established the rule: no code path prints an objective value without the profile set name,
the operating-point policy and the excluded-for-lack-of-data count. M6 inherits it and adds two
more gates, because a runtime report invites a specific kind of over-reading:

  * **Every number here is SIMULATED.** No GPU, no serving engine, no batching, no KV cache, no
    network. `fidelity_notes` is mandatory and non-empty, and a report without it raises.
  * **A "0% violation" result proves nothing on its own.** It has to be read against the
    provisioning delay, the spare fraction and the dispatch policy that produced it -- three
    knobs the paper leaves undefined (A87, A88, A83). So those three travel in the header, not a
    footnote.

The quantity worth reading is not the violation rate but the RELATION between the planner's
latency model and the runtime's: eq. (5) admits a configuration on `l^TTFT + t_c * l^TPOT <= tau`
with no queueing term at all, so any wait a request experiences is latency the optimizer cannot
see. `planner_blind_latency_s` is that gap, measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from execution.requests import Outcome, RequestOutcome
from execution.runner import EpochOutcome

GPU_QUALIFIER = (
    "for LLM executors only (11 of 26 executors are tools with no profile; M3 Section 12.3)"
)
SIMULATION_BANNER = (
    "SIMULATED RUN -- no GPU, no serving engine, no batching, no KV cache, no network"
)


@dataclass(frozen=True)
class ExecutionReport:
    """One execution run, with everything needed to read its numbers correctly."""

    profile_set_name: str
    workflow: str
    slo: str
    dispatch_policy: str
    provisioning_delay_s: float
    spare_fraction: float
    tau_s: float | None
    epochs: Sequence[EpochOutcome]
    outcomes: Sequence[RequestOutcome]
    fidelity_notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.fidelity_notes:
            raise ValueError(
                "an ExecutionReport without fidelity notes cannot be constructed -- a simulated "
                "latency reported without its limits is worse than no number"
            )

    # -- aggregates ---------------------------------------------------------------------

    @property
    def served(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome.served)

    @property
    def violated(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome.served and not o.met_slo)

    @property
    def dropped(self) -> int:
        return sum(1 for o in self.outcomes if o.outcome is Outcome.DROPPED)

    @property
    def violation_rate(self) -> float:
        return 0.0 if self.served == 0 else self.violated / self.served

    @property
    def planner_blind_latency_s(self) -> float:
        """Mean queueing delay -- latency eq. (5) has no term for.

        The optimizer admits a `(c, m)` pair if `l^TTFT_m + t_c * l^TPOT_m <= tau`. That
        expression contains no queue, no contention and no waiting. Every second measured here is
        end-to-end latency the planner structurally cannot account for, which is why a plan can
        be feasible on paper and violate its SLO in the run.
        """
        served = [o for o in self.outcomes if o.outcome.served]
        return 0.0 if not served else sum(o.queued_s for o in served) / len(served)

    @property
    def violations_from_queueing(self) -> int:
        """Violations where eq. (5) alone would have PASSED -- attributable to the blind spot."""
        if self.tau_s is None:
            return 0
        return sum(
            1
            for o in self.outcomes
            if o.outcome.served
            and not o.met_slo
            and o.service_s <= self.tau_s
        )

    @property
    def violations_from_token_variance(self) -> int:
        """Violations where the service time ALONE exceeded tau.

        These are not a runtime failure -- they are the p90 collapse showing up. The optimizer
        admitted the pair on `t_c` at the 90th percentile (A46); a request in the upper decile
        exceeds tau on service time before it waits for anything.
        """
        if self.tau_s is None:
            return 0
        return sum(
            1
            for o in self.outcomes
            if o.outcome.served and not o.met_slo and o.service_s > self.tau_s
        )

    def total_wasted_gpu_seconds(self) -> float:
        return sum(e.wasted_gpu_seconds for e in self.epochs)

    def scale_totals(self) -> Mapping[str, float]:
        out: dict[str, float] = {}
        for e in self.epochs:
            for k, v in e.scale_events.items():
                out[k] = out.get(k, 0.0) + v
        return out

    # -- rendering ----------------------------------------------------------------------

    def header(self) -> str:
        """The caveat gate: no result without the three undefined knobs that shaped it."""
        return "\n".join(
            [
                SIMULATION_BANNER,
                f"[{self.workflow} / {self.slo}] profile set: {self.profile_set_name}",
                f"  dispatch policy: {self.dispatch_policy} (A83: the paper says dispatch is "
                "'deterministic' but x is continuous)",
                f"  provisioning delay: {self.provisioning_delay_s:.0f}s "
                "(A87: Section 4.7's 20 min against Section 3.4's 60 s window)",
                f"  spare capacity: {self.spare_fraction:.2f} "
                "(A88: Section 3.4 names it, never sizes it)",
            ]
        )

    def render(self) -> str:
        lines = [self.header(), ""]
        if self.served == 0:
            lines.append("no requests served")
        else:
            lines += [
                f"served {self.served}   violated {self.violated} "
                f"({self.violation_rate * 100:.1f}%)   dropped {self.dropped}",
                f"  of violations: {self.violations_from_token_variance} from token variance "
                f"(service time alone > tau), {self.violations_from_queueing} from queueing",
                f"  mean queueing delay: {self.planner_blind_latency_s:.3f}s "
                "<-- eq. (5) has NO term for this",
                f"  GPUs at epoch end: {self.epochs[-1].gpus_end if self.epochs else 0} "
                f"{GPU_QUALIFIER}",
                f"  wasted GPU-seconds (provisioning): {self.total_wasted_gpu_seconds():.0f}",
                f"  scaling: {dict(self.scale_totals())}",
            ]
        lines += ["", "fidelity:"] + [f"  - {n}" for n in self.fidelity_notes]
        return "\n".join(lines)


__all__ = ["ExecutionReport", "GPU_QUALIFIER", "SIMULATION_BANNER"]
