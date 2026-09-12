"""
The variables and the seven distinct constraints -- Appendix A.5 eqs. (1)-(7), pp.586-587.

This module builds A.5's constraint system and nothing else. It does not choose an objective, it
does not solve, and it does not decide what a missing number means -- those are `objectives.py`,
`solve.py` and `sets.py` respectively.

FOUR RULES IT OBEYS, each of which is enforced by a test rather than by good intentions:

1. **It imports `MilpInputs` and nothing else from the profile layer.** The boundary of
   DESIGN.md Section 4.3 is one-way.
2. **It never reads a DAG.** A.5 has no precedence constraint and no makespan term, so neither
   does this. `/optimization/milp/` imports nothing from `/development/`. If M4 ever needed
   precedence to be feasible, THAT would be the finding, and it would go to
   `architecture-decisions.md` rather than into this file (DESIGN.md Section 10.1).
3. **It never calls `MilpInputs.coherent()`.** A.5 has no constraint linking `c` to `m` (A51).
   Imposing one here would repair the formulation; the incoherence is MEASURED instead, in
   `critique/incoherence.py`, which this module must not import.
4. **`x^avg` is built over the unfiltered space.** Not an oversight -- A66. See `sets.py`.

THE `mu_m` SEAM. Eq. (3) carries a multiplexing factor the paper defines nowhere (A42).
`_capacity_lhs()` isolates it so M5 changes one function rather than the constraint system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, MutableMapping

import pulp

from optimization.milp import A5
from optimization.milp.sets import Admissible, demand
from optimization.milp.units import EPOCH_SECONDS, Quantity
from optimization.profiles.provenance import Measured, Unavailable
from optimization.profiles.schema import ConfigKey, MilpInputs, ModelProfileKey

PairKey = tuple[ConfigKey, ModelProfileKey]

NO_MULTIPLEXING: float = 1.0
"""`mu_m = 1` for M4.

A.5 introduces `mu_m` in eq. (3) and says only "where mu_m is the model-specific multiplexing
factor" -- no value, no bound, no estimation method, in either version, and it is absent from
Section 3.3's list of what a profile contains (A42). Setting it to 1 is the only choice that adds
no information: it makes eq. (3) say "peak token demand must fit in provisioned throughput", which
is the constraint's evident intent. M5 replaces this and nothing else.
"""


@dataclass
class BuiltModel:
    """A.5's constraint system, assembled but objective-free.

    Carries the variable dictionaries so `objectives.py` can form expressions over them and
    `report.py` can read values back, plus the bookkeeping a result must carry: which constraints
    were omitted and why, and the equation numbers actually emitted.
    """

    problem: pulp.LpProblem
    n: Mapping[ModelProfileKey, pulp.LpVariable]
    x_peak: Mapping[PairKey, pulp.LpVariable]
    x_avg: Mapping[PairKey, pulp.LpVariable]
    admissible: Admissible
    epoch: int
    inactive_constraints: tuple[str, ...] = ()
    emitted_equations: tuple[int, ...] = ()
    cost_budget: float | None = None
    resource_budget: Mapping[str, float] | None = None

    def bounds_n_above(self) -> bool:
        """Whether any active constraint bounds `n_m` from ABOVE.

        Used by Section 4.3's guard. Under objectives (11)/(12) this is irrelevant -- both
        minimise in `n_m`, so eq. (3) bounds them below and the optimum is finite. Under
        objective (13), which does not minimise `n_m` at all, an absent budget leaves the fleet
        unbounded and the "answer" meaningless.
        """
        return self.resource_budget is not None or self.cost_budget is not None


def _capacity_lhs(
    x_peak: Mapping[PairKey, pulp.LpVariable],
    m: ModelProfileKey,
    t_c: Mapping[ConfigKey, Quantity],
    mu: float = NO_MULTIPLEXING,
) -> pulp.LpAffineExpression:
    """Left-hand side of eq. (3): `mu_m * sum_{w,s,c} x^peak_{w,s,c,m} * t_c`.

    **THIS FUNCTION IS MILESTONE 5'S ENTIRE SEAM.** Multiplexing changes `mu` and nothing else --
    not the variables, not the other six constraints, not the objectives.

    Units: `x^peak` is req/s and `t_c` is tokens/req, so the product is tokens/s, matching
    `n_m * theta_m` on the right. That cancellation is asserted in `test_milp_units.py`; getting
    it wrong scales every GPU count in the milestone by 60 while still returning plausible
    integers.

    **What eq. (3) does not capture, and Arno's capacity critique.** This is a per-request
    SLOT-CONSUMPTION model: a request stream consumes throughput in proportion to its token
    count, and instances are provisioned to cover the total. It has no call count -- a
    `D=4, R=4` debate of sixteen LLM invocations is distinguished from a single call ONLY by the
    magnitude of `t_c`. It has no per-node term, no concurrency, no queueing, no memory or KV-cache
    bound, and no notion that a tool stage occupies a stage at all. Reproduced exactly as written,
    because the comparison against an instance-based provisioning model is the point.
    """
    terms = [
        x_peak[(c, mm)] * float(t_c[c].value)
        for (c, mm) in x_peak
        if mm == m
    ]
    return mu * pulp.lpSum(terms) if terms else pulp.lpSum([])


def build_model(
    inputs: MilpInputs,
    admissible: Admissible,
    epoch: int,
    cost_budget: float | None = None,
    resource_budget: Mapping[str, float] | None = None,
    mu: float = NO_MULTIPLEXING,
    name: str = "murakkab_a5",
) -> BuiltModel:
    """Assemble eqs. (1)-(7) for one `(workflow, SLO, epoch)`.

    The constraint set must not vary with the objective -- that is what makes the cross-objective
    comparisons of Figures 7-9 meaningful -- with the single exception of eq. (6), whose presence
    A.5 itself ties to a supplied cost budget. `test_milp_formulation.py` asserts the emitted
    constraint list is identical across the three objectives given identical budget arguments.
    """
    w, s = admissible.workflow, admissible.slo
    problem = pulp.LpProblem(f"{name}_{w}_{s[0]}_{s[1]}_e{epoch}", pulp.LpMinimize)
    inactive: list[str] = []
    emitted: list[int] = []

    # -- variables (A.5 "Decision Variables", p.586) ---------------------------------------
    n: dict[ModelProfileKey, pulp.LpVariable] = {
        m: pulp.LpVariable(f"n_{_slug(m)}", lowBound=0, cat="Integer")
        for m in admissible.models
    }
    # `x` is CONTINUOUS -- A.5 declares `R+` (Section 4.1). A request RATE may be split
    # fractionally across pairs; the consequence is that "the chosen configuration" is a
    # distribution, while Tables 5/6 print one row (A70). report.py prints the support size.
    x_peak: dict[PairKey, pulp.LpVariable] = {
        pair: pulp.LpVariable(f"xp_{_slug(pair)}", lowBound=0, cat="Continuous")
        for pair in admissible.pairs
    }
    x_avg: dict[PairKey, pulp.LpVariable] = {
        pair: pulp.LpVariable(f"xa_{_slug(pair)}", lowBound=0, cat="Continuous")
        for pair in admissible.pairs_unfiltered
    }

    lam_peak, lam_avg = demand(inputs, w, s, epoch)
    alpha = float(inputs.alpha.value)

    # -- eq. (1) demand satisfaction, peak -------------------------------------------------
    if x_peak:
        total_peak = pulp.lpSum(x_peak.values())
        problem += total_peak >= lam_peak.value, "eq1_lower"
        problem += total_peak <= alpha * lam_peak.value, "eq1_upper"
        emitted.append(1)
    else:
        inactive.append("eq1: no admissible peak variable exists (structurally infeasible)")

    # -- eq. (2) demand satisfaction, average ----------------------------------------------
    if x_avg:
        total_avg = pulp.lpSum(x_avg.values())
        problem += total_avg >= lam_avg.value, "eq2_lower"
        problem += total_avg <= alpha * lam_avg.value, "eq2_upper"
        emitted.append(2)

    # -- eq. (3) capacity, with the mu_m seam ----------------------------------------------
    for m in admissible.models:
        lhs = _capacity_lhs(x_peak, m, admissible.t_c, mu)
        problem += lhs <= n[m] * float(admissible.theta_m[m].value), f"eq3_{_slug(m)}"
    emitted.append(3)

    # -- eqs. (4)/(5) are NOT emitted as constraints ---------------------------------------
    # They are assignments (`x = 0 if ...`), realised in sets.py by not creating the variable.
    # Their duplicates (8)/(9) are the same statements (A58) and are likewise not re-emitted.
    emitted.extend([4, 5])

    # -- eq. (6) cost budget ----------------------------------------------------------------
    if cost_budget is not None:
        # Verbatim: sum x^avg * (t_c / theta_m) * g_m * c_g(m) <= Cost_budget.
        # NOTE this prices CONSUMPTION (GPU-seconds of work), while objective (12) prices
        # PROVISIONING (the fleet, idle or not). Nothing in A.5 ties them together (A72).
        terms = []
        for (c, m) in x_avg:
            gpu = m.gpu
            if gpu not in admissible.c_g:
                continue
            coeff = (
                float(admissible.t_c[c].value)
                / float(admissible.theta_m[m].value)
                * admissible.g_m[m]
                * float(admissible.c_g[gpu].value)
            )
            terms.append(x_avg[(c, m)] * coeff)
        if terms:
            problem += pulp.lpSum(terms) <= cost_budget, "eq6_cost_budget"
            emitted.append(6)
    else:
        inactive.append("eq6: no cost budget supplied (A67: tau_{w,cost} is unreported)")

    # -- eq. (7) resource budget -------------------------------------------------------------
    if resource_budget is not None:
        for g, cap in resource_budget.items():
            terms = [n[m] * admissible.g_m[m] for m in admissible.models if m.gpu == g]
            if terms:
                problem += pulp.lpSum(terms) <= cap, f"eq7_{g}"
        emitted.append(7)
    else:
        inactive.append(
            "eq7: no resource budget chosen (A43: Sections 4.2/4.3 state none, so eq. (7) is "
            "inactive for the headline experiments)"
        )

    return BuiltModel(
        problem=problem,
        n=n,
        x_peak=x_peak,
        x_avg=x_avg,
        admissible=admissible,
        epoch=epoch,
        inactive_constraints=tuple(inactive),
        emitted_equations=tuple(sorted(set(emitted))),
        cost_budget=cost_budget,
        resource_budget=dict(resource_budget) if resource_budget else None,
    )


def _slug(obj) -> str:
    """PuLP variable names may not contain characters it uses structurally."""
    return (
        str(obj)
        .replace(" ", "")
        .replace("(", "_")
        .replace(")", "")
        .replace(",", "_")
        .replace("=", "")
        .replace("/", "_")
        .replace("-", "")
        .replace("'", "")
        .replace("+", "")
    )


__all__ = ["BuiltModel", "NO_MULTIPLEXING", "PairKey", "build_model"]
