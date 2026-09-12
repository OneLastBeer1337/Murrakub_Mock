"""
`MilpResult` and its rendering -- DESIGN.md Section 9.

THE CAVEAT GATE. There is **no code path here that prints an objective value without also
printing** the profile set name, the operating-point policy, and the excluded-for-lack-of-data
count with a one-line reason breakdown. Q19 makes that mandatory, and a convention enforced by
discipline would have failed the first time someone wanted a quick number.
`test_milp_reporting.py::test_no_headline_number_without_its_caveats` asserts it.

Every GPU count is additionally labelled **"for LLM executors only"**. Eleven of the twenty-six
executors in the library are tools with no profile, and the two workflows are not affected
equally -- Video Q/A has three tool stages, Code Generation one (M3 Section 12.3). So every count
this milestone produces is a LOWER BOUND on the deployment the paper describes, and the qualifier
belongs in the sentence rather than in an appendix.

A71's banner: because a missing `l^TTFT_m` only matters on a latency run and a missing `a_c` only
on an accuracy run, the eight Section 4.2 runs are each solved over a DIFFERENT feasible set.
`compare_runs()` refuses to tabulate them without saying so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from optimization.milp.critique.incoherence import IncoherenceReport
from optimization.milp.critique.structural_record import StructuralRecord
from optimization.milp.objectives import AccuracyWeighting, Objective
from optimization.milp.sets import ExclusionLedger
from optimization.milp.solve import MilpStatus
from optimization.profiles.schema import (
    ConfigKey,
    ModelProfileKey,
    OperatingPointPolicy,
    TokenPolicy,
)

GPU_QUALIFIER = "for LLM executors only (11 of 26 executors are tools with no profile; M3 Section 12.3)"


@dataclass(frozen=True)
class MilpResult:
    """One solved (or unsolved) run, with everything a reader must not be allowed to miss."""

    # -- provenance of the answer: all mandatory, none defaulted --------------------------
    profile_set_name: str
    operating_point_policy: OperatingPointPolicy
    token_policy: TokenPolicy
    workflow: str
    slo: tuple[str, str]
    epoch: int
    objective: Objective
    budget_choice: str
    cost_budget: float | None
    solver: str
    time_limit_s: int

    # -- the answer ------------------------------------------------------------------------
    status: MilpStatus
    objective_value: float | None
    n: Mapping[ModelProfileKey, int]
    x_peak: Mapping[tuple[ConfigKey, ModelProfileKey], float]
    x_avg: Mapping[tuple[ConfigKey, ModelProfileKey], float]
    wall_clock_s: float
    gap: float | None = None

    # -- what the reader must not be allowed to miss ---------------------------------------
    data_excluded: tuple[str, ...] = ()
    exclusion_ledger: ExclusionLedger | None = None
    inactive_constraints: tuple[str, ...] = ()
    equation_map: Mapping[int, int] = field(default_factory=dict)
    incoherent_mass: IncoherenceReport | None = None
    support_size: int = 0
    structural_record: StructuralRecord | None = None
    fidelity_notes: tuple[str, ...] = ()
    accuracy_weighting: AccuracyWeighting = AccuracyWeighting.AVG
    structural_reason: str = ""
    nearest_miss: str = ""

    @property
    def total_gpus(self) -> int:
        """Sum of `n_m * g_m`. ALWAYS quote with `GPU_QUALIFIER`."""
        return sum(self.n.values())

    def caveats(self) -> tuple[str, ...]:
        """The block that must accompany any number from this run."""
        lines = [
            f"profile set: {self.profile_set_name}",
            f"operating point: {self.operating_point_policy.value} "
            f"(the ~6.8x sensitivity lever, A37b)",
            f"token policy: p{self.token_policy.percentile} (A46: [OSDI]-only sentence)",
            f"excluded for lack of data: {len(self.data_excluded)}",
        ]
        if self.exclusion_ledger is not None:
            s = self.exclusion_ledger.summary()
            lines.append(
                f"  of which: {s['excluded_for_lack_of_data']} data-lack, "
                f"{s['excluded_by_slo_filter']} SLO-filtered "
                "(NEVER summed -- different claims)"
            )
        for note in self.inactive_constraints:
            lines.append(f"inactive: {note}")
        return tuple(lines)

    def headline(self) -> str:
        """The objective value -- and it is IMPOSSIBLE to obtain it without the caveats."""
        if not self.status.is_answer:
            body = f"{self.status.value.upper()}"
            if self.structural_reason:
                body += f" -- {self.structural_reason}"
            if self.nearest_miss:
                body += f"\n  nearest miss: {self.nearest_miss}"
        else:
            unit = {
                Objective.ENERGY: "kWh",
                Objective.COST: "USD",
                Objective.ACCURACY: "accuracy-minus-cost score",
            }[self.objective]
            body = (
                f"eq. ({self.objective.value}) = {self.objective_value:.4f} {unit} over one "
                f"60-min epoch; {self.total_gpus} GPUs {GPU_QUALIFIER}"
            )
        head = f"[{self.workflow} / {self.slo[0]}-{self.slo[1]} / epoch {self.epoch}] {body}"
        return head + "\n  " + "\n  ".join(self.caveats())

    def render(self) -> str:
        out = [self.headline()]
        if self.support_size:
            out.append(
                f"  support: {self.support_size} (c,m) pair(s) carry non-zero mass"
                + (
                    "  <-- A70: Tables 5/6 print ONE row per tier; the formulation blended"
                    if self.support_size > 1
                    else ""
                )
            )
        if self.incoherent_mass is not None:
            out.append(f"  A51: {self.incoherent_mass.summary()}")
        if self.structural_record is not None:
            out.append(f"  A.5 latency model: {self.structural_record.blind_spot_note()}")
        for note in self.fidelity_notes:
            out.append(f"  note: {note}")
        return "\n".join(out)


def support_size(x: Mapping[tuple[ConfigKey, ModelProfileKey], float], tol: float = 1e-9) -> int:
    return sum(1 for v in x.values() if v > tol)


def compare_runs(results: Sequence[MilpResult]) -> str:
    """A cross-run table -- refusing to print one silently when the feasible sets differ (A71).

    A missing `l^TTFT_m` excludes a model on latency runs only; a missing `a_c` excludes a
    configuration on accuracy runs only. So two rows of this table can be solved over different
    index spaces, and comparing their GPU counts compares partly the data coverage rather than
    the SLO. The banner is not decoration.
    """
    if not results:
        return "(no runs)"
    sets = {frozenset(r.data_excluded) for r in results}
    lines: list[str] = []
    if len(sets) > 1:
        lines += [
            "!! EXCLUDED SETS DIFFER ACROSS THESE RUNS (A71) -- they are solved over different",
            "!! feasible sets and their objective values are NOT strictly comparable.",
            "",
        ]
    lines.append(
        f"{'workflow':<14}{'SLO':<18}{'objective':<11}{'status':<24}"
        f"{'value':>12}  {'GPUs':>5}  excluded"
    )
    for r in results:
        value = "-" if r.objective_value is None else f"{r.objective_value:.4f}"
        lines.append(
            f"{r.workflow:<14}{r.slo[0] + '-' + r.slo[1]:<18}"
            f"eq.{r.objective.value:<8}{r.status.value:<24}{value:>12}  "
            f"{r.total_gpus:>5}  {len(r.data_excluded)}"
        )
    lines.append("")
    lines.append(f"GPU counts are {GPU_QUALIFIER}.")
    lines.append(f"profile set: {results[0].profile_set_name}")
    return "\n".join(lines)


def churn(results_by_epoch: Sequence[MilpResult]) -> int:
    """Total instance churn across epochs -- A69, measured rather than remarked upon.

    A.5 has no inter-epoch coupling of any kind: no warm start, no switching cost, no minimum
    instance lifetime. So the optimizer will tear down and rebuild an entire fleet between two
    adjacent hours at zero modelled cost. This counts how much of that it actually does.
    """
    total = 0
    previous: Mapping[ModelProfileKey, int] = {}
    for r in results_by_epoch:
        keys = set(previous) | set(r.n)
        total += sum(abs(r.n.get(k, 0) - previous.get(k, 0)) for k in keys)
        previous = r.n
    return total


__all__ = ["GPU_QUALIFIER", "MilpResult", "churn", "compare_runs", "support_size"]
