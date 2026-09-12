"""
The three arms of Table 2 / Figure 18 -- "Mkb Opt" vs "Mkb Opt+Mult", and the arm the paper omits.

    Table 2 (p.576) reports multiplexing cutting GPUs by 21.6%, energy by 20.2%, cost by 17.4%
    ([OSDI]; 21.1 / 20.2 / 17.3 in [ARXIV], A47).

THREE ARMS, NOT TWO. The paper compares two things; we compute three, and the third is the one
that matters:

    A. SEPARATE   -- each workflow solved alone, GPU counts summed. mu = 1.
    B. JOINT      -- both workflows in one problem, sharing `n_m`. mu = 1. **Mkb Opt.**
    C. JOINT+MULT -- the same problem with mu < 1.                  **Mkb Opt+Mult.**

`B - A` isolates what A.5's STRUCTURE can achieve by sharing instances. `C - B` isolates what the
`mu` coefficient contributes. The paper reports only a combined figure and attributes it to
multiplexing, so separating the two is the whole point of this module.

A80 -- WHAT THE MEASUREMENT SHOWS, AND IT IS THE MILESTONE'S STRONGEST RESULT. `B - A` is
**zero, or at most integrality rounding**. Eq. (3) is linear in `x` and `n`: the instances a model
needs are proportional to the token demand landing on it, so pooling two workflows' demand onto
one `n_m` requires `ceil((d1 + d2) / theta)` instead of `ceil(d1 / theta) + ceil(d2 / theta)`. The
difference is at most one instance per shared model -- under a percent at this scale, and measured
at exactly 0.00% on the Section 4.3 setup even with a model genuinely shared between both
workflows.

So **A.5's structure cannot produce Table 2's 21.6%.** The entire reported gain enters through
`mu`, a coefficient the paper never defines, bounds, or reports. And since we can only obtain
`mu` by fitting it to that same 21.6% (`mu.py`), reproducing the figure is arithmetic, not
validation. The calibration is spent; this module states so on every comparison it prints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from optimization.milp.joint import JointResult, solve_joint
from optimization.milp.mu import MuChoice, from_table_2, no_multiplexing, out_of_sample_targets
from optimization.milp.objectives import Objective
from optimization.milp.scenarios import BudgetChoice
from optimization.milp.solve import MilpStatus
from optimization.profiles.schema import ProfileSet

SECTION_4_3_SLOS: tuple[tuple[str, str], ...] = (("accuracy", "good"), ("latency", "good"))
"""Section 4.3 (p.576): "70% requests to be high-accuracy and 30% requests to low-latency, both
with *good* tier". The 70/30 split lives in M3's `SloMix`, which shapes the arrival rates."""

SECTION_4_3_WORKFLOWS: tuple[str, ...] = ("video_qa", "code_generation")


@dataclass(frozen=True)
class MultiplexingComparison:
    """The three arms, with the two deltas kept apart."""

    separate: tuple[JointResult, ...]
    joint: JointResult
    joint_mult: JointResult
    profile_set_name: str

    @property
    def separate_gpus(self) -> int:
        return sum(r.total_gpus for r in self.separate)

    @property
    def all_feasible(self) -> bool:
        runs = list(self.separate) + [self.joint, self.joint_mult]
        return all(r.status is MilpStatus.OPTIMAL for r in runs)

    @property
    def structural_sharing_pct(self) -> float | None:
        """`B - A`: what A.5's STRUCTURE achieves by sharing `n_m`. Predicted ~0 (A80)."""
        if not self.all_feasible or self.separate_gpus == 0:
            return None
        return 100.0 * (self.separate_gpus - self.joint.total_gpus) / self.separate_gpus

    @property
    def mu_contribution_pct(self) -> float | None:
        """`C - B`: what the `mu` COEFFICIENT contributes. Predicted ~= 1 - mu."""
        if not self.all_feasible or self.joint.total_gpus == 0:
            return None
        return (
            100.0 * (self.joint.total_gpus - self.joint_mult.total_gpus) / self.joint.total_gpus
        )

    @property
    def combined_pct(self) -> float | None:
        """What the paper reports as one number, against Table 2's 21.6%."""
        if not self.all_feasible or self.separate_gpus == 0:
            return None
        return (
            100.0 * (self.separate_gpus - self.joint_mult.total_gpus) / self.separate_gpus
        )

    def shared_models(self) -> tuple[str, ...]:
        """Models carrying load from more than one workflow -- where sharing could occur at all."""
        by_model: dict[str, set[str]] = {}
        for (w, _s, _c, m), mass in self.joint.x_peak.items():
            if mass > 1e-9:
                by_model.setdefault(str(m), set()).add(w)
        return tuple(sorted(m for m, ws in by_model.items() if len(ws) > 1))

    def render(self) -> str:
        lines = [
            "Multiplexing comparison -- Table 2 / Figure 18",
            f"profile set: {self.profile_set_name}   mu: {self.joint_mult.mu.describe()}",
            "",
        ]
        if not self.all_feasible:
            lines.append("NOT ALL ARMS FEASIBLE -- no delta can be computed.")
            for run in list(self.separate) + [self.joint, self.joint_mult]:
                if run.status is not MilpStatus.OPTIMAL:
                    lines.append(f"  {run.workflows} {run.status.value}")
                    for k, v in run.nearest_misses.items():
                        lines.append(f"    {k}: {v}")
            return "\n".join(lines)

        lines += [
            f"A. separate  (mu=1, summed)   {self.separate_gpus:5d} GPUs",
            f"B. joint     (mu=1, shared)   {self.joint.total_gpus:5d} GPUs"
            f"   -> structural sharing: {self.structural_sharing_pct:+.2f}%",
            f"C. joint+mult                 {self.joint_mult.total_gpus:5d} GPUs"
            f"   -> mu contribution:    {self.mu_contribution_pct:+.2f}%",
            "",
            f"combined (A -> C): {self.combined_pct:.2f}%   "
            f"Table 2 reports {out_of_sample_targets()['gpu_pct']}%",
            "",
            f"models shared between workflows: {len(self.shared_models())} "
            f"{self.shared_models()}",
            "",
            "A80: the structural arm (B - A) is the only part A.5 produces on its own, and it is",
            "     bounded by integrality rounding -- at most one instance per shared model. The",
            "     rest enters through mu, which the paper never defines and which we could only",
            "     obtain by fitting it to the very number above. CALIBRATION SPENT: this is",
            "     arithmetic, not validation.",
            "",
            "GPU counts are for LLM executors only (11 of 26 executors are tools with no "
            "profile; M3 Section 12.3).",
        ]
        return "\n".join(lines)


def compare(
    profile_set_obj: ProfileSet,
    objective: Objective,
    budget: BudgetChoice,
    mu: MuChoice | None = None,
    workflows: Sequence[str] = SECTION_4_3_WORKFLOWS,
    slos: Sequence[tuple[str, str]] = SECTION_4_3_SLOS,
    epoch: int = 0,
) -> MultiplexingComparison:
    """Run all three arms on one profile set."""
    mu = mu or from_table_2()
    separate = tuple(
        solve_joint(profile_set_obj, [w], slos, objective, budget, no_multiplexing(), epoch)
        for w in workflows
    )
    joint = solve_joint(
        profile_set_obj, workflows, slos, objective, budget, no_multiplexing(), epoch
    )
    joint_mult = solve_joint(profile_set_obj, workflows, slos, objective, budget, mu, epoch)
    return MultiplexingComparison(
        separate=separate,
        joint=joint,
        joint_mult=joint_mult,
        profile_set_name=profile_set_obj.name,
    )


__all__ = [
    "MultiplexingComparison",
    "SECTION_4_3_SLOS",
    "SECTION_4_3_WORKFLOWS",
    "compare",
]
