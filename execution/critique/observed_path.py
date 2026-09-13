"""
The measured critical path against eq. (5) -- the HEFT/precedence gap, finally as a number.

**QUARANTINED.** Nothing in `/execution/` outside `critique/` may import this, by test. It exists
to compare, not to schedule, and it may consume the INVENTED tool overlay (Q16).

WHAT CHANGED AT M7. M3 built `profiles/critique/critical_path.py`, which stated the gap
STRUCTURALLY: eq. (5) has two terms, a critical path has more, and three of the DAG's stages have
no counterpart in eq. (5) at all. What it could not do was observe an actual execution. M7's
`RequestTrace` supplies that, so the comparison stops being an argument about which symbols exist
and becomes a measurement of how much they are worth.

A94 -- AND THE ANSWER DEPENDS ENTIRELY ON THE WORKFLOW, WHICH IS ITSELF THE FINDING:

    Code Generation   t_c ~ 40,000 tokens   eq. (5) ~ 1547 s   blind spot ~ 0.3 %
    Video Q/A         t_c ~     194 tokens  eq. (5) ~ 2.74 s   blind spot ~ 69 %

The same formulation defect is negligible on one workflow and dominant on the other, and the
discriminator is `t_c`. When a configuration generates tens of thousands of tokens, the `t_c *
l^TPOT_m` term swamps everything eq. (5) omits -- tool stages, extra prefills, the lot. When it
generates a couple of hundred, the omissions are most of the latency.

That is why "Murakkab's latency model is wrong" is too coarse a claim to be useful, and why this
module reports the ratio per workflow rather than a single headline number. The Video Q/A figure
survives the full +/-3x band on the invented tool times (42%-87%), so the conclusion rests on the
STRUCTURE -- small `t_c`, three tool stages -- not on the magnitudes we made up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from execution.workflow_run import NodeTrace, RequestTrace
from shared.executor import ExecutorKind


@dataclass(frozen=True)
class PathComparison:
    """One request's observed walk set beside what the optimizer charged for it."""

    trace: RequestTrace

    @property
    def eq5_s(self) -> float | None:
        return self.trace.eq5_s

    @property
    def observed_s(self) -> float:
        return self.trace.observed_span_s

    @property
    def unmodelled_s(self) -> float | None:
        """Latency the formulation has no term for.

        Tool wall-clock plus the prefills eq. (5) does not charge. Negative values are possible
        and meaningful -- they mean the apportioned per-node walk came in UNDER eq. (5), which
        happens when the whole token cost lands on one node.
        """
        if self.eq5_s is None:
            return None
        return self.observed_s - self.eq5_s

    @property
    def blind_spot_fraction(self) -> float | None:
        """Share of observed latency eq. (5) cannot see. The number A94 is about."""
        if self.eq5_s is None or self.observed_s <= 0:
            return None
        return max(0.0, self.observed_s - self.eq5_s) / self.observed_s

    @property
    def tool_seconds(self) -> float:
        return sum(n.duration_s for n in self.trace.tool_nodes)

    @property
    def free_stage_count(self) -> int:
        """Stages A.5 charges exactly nothing for."""
        return len(self.trace.tool_nodes)

    # NOTE: the TTFT undercount is NOT a property here. It needs `l^TTFT_m`, which the trace
    # does not carry (node durations already have it folded in), and reconstructing it by
    # division would be arithmetic on a derived number. Use the `ttft_undercount()` free
    # function with the profiled value instead -- two exact inputs, no inference.

    def describe(self) -> str:
        if self.eq5_s is None:
            return (
                f"{self.trace.workflow_id}: eq. (5) is unevaluable for {self.trace.model} "
                "(A35/A36 -- no TTFT reported anywhere), so there is nothing to compare against"
            )
        fraction = self.blind_spot_fraction or 0.0
        return (
            f"{self.trace.workflow_id} on {self.trace.model}: "
            f"eq. (5) = {self.eq5_s:.2f}s, observed walk = {self.observed_s:.2f}s, "
            f"unmodelled = {self.unmodelled_s:.2f}s ({fraction * 100:.0f}% of observed). "
            f"{self.free_stage_count} stage(s) cost the formulation nothing; "
            f"{self.trace.llm_invocations} LLM invocation(s) were charged one prefill."
        )


def compare(trace: RequestTrace) -> PathComparison:
    return PathComparison(trace=trace)


def ttft_undercount(invocations: int, ttft_s: float) -> float:
    """A96, computed directly. `(invocations - 1) * l^TTFT_m`.

    Kept as a free function because it needs only two numbers and both are exact: an integer
    count from the configuration's knobs, and a profiled TTFT. No apportionment, no invention.
    """
    return max(0, invocations - 1) * ttft_s


def workflow_sensitivity(comparisons: Sequence[PathComparison]) -> Mapping[str, float]:
    """Blind-spot fraction per workflow -- the A94 table, computed.

    Reported per workflow deliberately. A single averaged figure would hide the only interesting
    thing here: that the same defect is worth 0.3% on one workflow and 69% on the other, and that
    `t_c` is what decides.
    """
    out: dict[str, float] = {}
    for c in comparisons:
        f = c.blind_spot_fraction
        if f is not None:
            out[c.trace.workflow_id] = max(out.get(c.trace.workflow_id, 0.0), f)
    return out


__all__ = [
    "PathComparison",
    "compare",
    "ttft_undercount",
    "workflow_sensitivity",
]
