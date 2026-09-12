"""
The joint, multi-workflow solve -- Appendix A.5 with `|W| = 2`, and Section 4.3's experiment.

WHY THIS FILE EXISTS AT ALL, WHICH IS ITSELF THE FINDING (A75). M4's design claimed multiplexing
would be a one-line change to `_capacity_lhs()`. The `mu` scalar genuinely is. But M4 keyed `x` as
`(c, m)` -- it ELIDED A.5's `w` and `s` indices, because a single-workflow solve has no use for
them -- and emitted eqs. (1)/(2) as single scalar constraints rather than families. So the
coefficient was a one-line change and the MECHANISM was not.

That gap is not an accident of our implementation. It mirrors the paper: **A.5 names the
coefficient `mu_m` and never names the mechanism.** Eq. (3) already sums over `w`, and `n_m` is
already keyed by `m` alone, so the structure for sharing was always there -- but nothing in A.5
says that sharing is what `mu_m` measures, or how the two relate. We had to build the mechanism to
discover that the formulation does not describe it.

    Section 4.3 (p.576), identical in both versions:
    "we run video Q/A and code generation requests together and assign 70% requests to be
    high-accuracy and 30% requests to low-latency, both with good tier"

WHAT IS SHARED. `n_m` is keyed by `m` alone and eq. (3) sums over all `(w, s, c)`. That is the
entire sharing mechanism: two workflows' peak token demand lands on one instance count. Everything
else is per-`(w,s)`.

THE INFEASIBILITY COUPLING. Eq. (1) is `for all w in W, s in S`. If any one `(w,s)` has no
admissible pair, its demand cannot be met, and the WHOLE joint problem is infeasible -- Code
Generation goes down with Video Q/A. Under `baseline` that is the predicted outcome (A37), and it
is reported with the offending `(w,s)` named rather than as a global failure. We do not repair it
by dropping the latency share, loosening `tau`, or solving the workflows separately and calling
the result joint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import pulp

from optimization.milp.model import _slug
from optimization.milp.mu import MuChoice
from optimization.milp.objectives import Objective, UnboundedObjective
from optimization.milp.scenarios import BudgetChoice
from optimization.milp.sets import Admissible, ExclusionLedger, build_admissible, demand
from optimization.milp.solve import (
    Backend,
    MilpStatus,
    solve_model,
)
from optimization.milp.units import EPOCH_SECONDS
from optimization.milp import A5
from optimization.profiles.schema import ConfigKey, MilpInputs, ModelProfileKey, ProfileSet
from optimization.profiles.sources.tables import SOLVER_TIME_LIMIT_S

#: A.5's full four-index key, restored.
JointKey = tuple[str, tuple[str, str], ConfigKey, ModelProfileKey]


@dataclass(frozen=True)
class JointAdmissible:
    """Admissibility for every `(w, s)` in one joint problem, plus what emptied it."""

    per_slo: Mapping[tuple[str, tuple[str, str]], Admissible]
    empty_slos: tuple[tuple[str, tuple[str, str]], ...]

    @property
    def is_infeasible(self) -> bool:
        """ANY empty `(w,s)` makes the joint problem infeasible -- eq. (1) is a `for all`."""
        return bool(self.empty_slos)

    def merged_ledger(self) -> ExclusionLedger:
        """One ledger across the whole problem, still partitioned by data-lack vs SLO-filter.

        Merged for reporting only. The two KINDS stay separate, as at M4: "the paper never
        reported this" and "this cannot meet its promise" remain different claims however many
        workflows are in the solve.
        """
        out = ExclusionLedger()
        for (w, s), adm in self.per_slo.items():
            for entry in adm.ledger.entries:
                out.add(
                    f"[{w}/{s[0]}-{s[1]}] {entry.element}",
                    entry.kind,
                    entry.parameter,
                    entry.reason,
                    entry.arithmetic,
                )
        return out

    def models(self) -> tuple[ModelProfileKey, ...]:
        """`M` across the joint problem -- the set `n_m` is defined over, and what gets shared."""
        seen: list[ModelProfileKey] = []
        for adm in self.per_slo.values():
            for m in adm.models:
                if m not in seen:
                    seen.append(m)
        return tuple(seen)


def build_joint_admissible(
    inputs: MilpInputs,
    workflows: Sequence[str],
    slos: Sequence[tuple[str, str]],
    objective: Objective,
) -> JointAdmissible:
    per_slo: dict[tuple[str, tuple[str, str]], Admissible] = {}
    empty: list[tuple[str, tuple[str, str]]] = []
    for w in workflows:
        for s in slos:
            adm = build_admissible(
                inputs, w, s, objective_needs_energy=(objective is Objective.ENERGY)
            )
            per_slo[(w, s)] = adm
            if adm.is_empty:
                empty.append((w, s))
    return JointAdmissible(per_slo=per_slo, empty_slos=tuple(empty))


@dataclass
class JointModel:
    problem: pulp.LpProblem
    n: Mapping[ModelProfileKey, pulp.LpVariable]
    x_peak: Mapping[JointKey, pulp.LpVariable]
    x_avg: Mapping[JointKey, pulp.LpVariable]
    admissible: JointAdmissible
    epoch: int
    mu: MuChoice
    inactive_constraints: tuple[str, ...] = ()
    cost_budget: float | None = None
    resource_budget: Mapping[str, float] | None = None

    def bounds_n_above(self) -> bool:
        return self.resource_budget is not None or self.cost_budget is not None


def _capacity_lhs_joint(
    x_peak: Mapping[JointKey, pulp.LpVariable],
    m: ModelProfileKey,
    t_c: Mapping[ConfigKey, float],
    mu: float,
) -> pulp.LpAffineExpression:
    """eq. (3)'s left side, summed over ALL `(w, s, c)` -- the sharing, made concrete.

    Identical in form to M4's `_capacity_lhs`; the only difference is that the sum now ranges
    over two workflows' variables landing on one `n_m`. A.5 never changed: its `sum_{w,s,c}` was
    always written this way. M4 simply had one workflow to sum over.

    `mu` multiplies the whole demand side. Note what that means algebraically: this is identical
    to dividing `theta_m` by `mu`, so "multiplexing" is a throughput bonus under another name
    (A78). The optimizer is TOLD the gain rather than deriving it from the sharing it chose.
    """
    terms = [
        var * t_c[c]
        for (_w, _s, c, mm), var in x_peak.items()
        if mm == m and c in t_c
    ]
    return mu * pulp.lpSum(terms) if terms else pulp.lpSum([])


def build_joint_model(
    inputs: MilpInputs,
    admissible: JointAdmissible,
    mu: MuChoice,
    epoch: int,
    cost_budget: float | None = None,
    resource_budget: Mapping[str, float] | None = None,
) -> JointModel:
    """A.5's seven constraints over `(W x S)`, with `n_m` shared."""
    problem = pulp.LpProblem(f"murakkab_a5_joint_e{epoch}", pulp.LpMinimize)
    inactive: list[str] = []
    models = admissible.models()

    n = {
        m: pulp.LpVariable(f"n_{_slug(m)}", lowBound=0, cat="Integer") for m in models
    }
    x_peak: dict[JointKey, pulp.LpVariable] = {}
    x_avg: dict[JointKey, pulp.LpVariable] = {}
    t_c_all: dict[ConfigKey, float] = {}

    for (w, s), adm in admissible.per_slo.items():
        for c, q in adm.t_c.items():
            t_c_all[c] = float(q.value)
        for (c, m) in adm.pairs:
            x_peak[(w, s, c, m)] = pulp.LpVariable(
                f"xp_{_slug(w)}_{_slug(s)}_{_slug((c, m))}", lowBound=0, cat="Continuous"
            )
        for (c, m) in adm.pairs_unfiltered:
            x_avg[(w, s, c, m)] = pulp.LpVariable(
                f"xa_{_slug(w)}_{_slug(s)}_{_slug((c, m))}", lowBound=0, cat="Continuous"
            )

    alpha = float(inputs.alpha.value)

    # -- eqs. (1) and (2): now FAMILIES, one two-sided pair per (w, s) ----------------------
    for (w, s) in admissible.per_slo:
        lam_peak, lam_avg = demand(inputs, w, s, epoch)
        peak_vars = [v for (ww, ss, _c, _m), v in x_peak.items() if ww == w and ss == s]
        avg_vars = [v for (ww, ss, _c, _m), v in x_avg.items() if ww == w and ss == s]
        tag = f"{_slug(w)}_{_slug(s)}"
        if peak_vars:
            total = pulp.lpSum(peak_vars)
            problem += total >= lam_peak.value, f"eq1_lo_{tag}"
            problem += total <= alpha * lam_peak.value, f"eq1_hi_{tag}"
        else:
            inactive.append(f"eq1[{w}/{s[0]}-{s[1]}]: no admissible peak variable")
        if avg_vars:
            total = pulp.lpSum(avg_vars)
            problem += total >= lam_avg.value, f"eq2_lo_{tag}"
            problem += total <= alpha * lam_avg.value, f"eq2_hi_{tag}"

    # -- eq. (3): ONE constraint per model, summing across BOTH workflows -------------------
    theta = {}
    g_m = {}
    for adm in admissible.per_slo.values():
        theta.update({m: float(q.value) for m, q in adm.theta_m.items()})
        g_m.update(adm.g_m)
    for m in models:
        lhs = _capacity_lhs_joint(x_peak, m, t_c_all, mu.of(m))
        problem += lhs <= n[m] * theta[m], f"eq3_{_slug(m)}"

    # -- eq. (6) ----------------------------------------------------------------------------
    c_g: dict[str, float] = {}
    for adm in admissible.per_slo.values():
        c_g.update({g: float(q.value) for g, q in adm.c_g.items()})
    if cost_budget is not None:
        terms = []
        for (_w, _s, c, m), var in x_avg.items():
            if m.gpu not in c_g or c not in t_c_all:
                continue
            terms.append(var * (t_c_all[c] / theta[m]) * g_m[m] * c_g[m.gpu])
        if terms:
            problem += pulp.lpSum(terms) <= cost_budget, "eq6_cost_budget"
    else:
        inactive.append("eq6: no cost budget supplied (A67: tau_{w,cost} is unreported)")

    # -- eq. (7) ----------------------------------------------------------------------------
    if resource_budget is not None:
        for g, cap in resource_budget.items():
            terms = [n[m] * g_m[m] for m in models if m.gpu == g]
            if terms:
                problem += pulp.lpSum(terms) <= cap, f"eq7_{g}"
    else:
        inactive.append(
            "eq7: no resource budget chosen (A43: Sections 4.2/4.3 state none)"
        )

    return JointModel(
        problem=problem,
        n=n,
        x_peak=x_peak,
        x_avg=x_avg,
        admissible=admissible,
        epoch=epoch,
        mu=mu,
        inactive_constraints=tuple(inactive),
        cost_budget=cost_budget,
        resource_budget=dict(resource_budget) if resource_budget else None,
    )


def attach_joint(
    built: JointModel,
    objective: Objective,
    lam_avg_total: float,
) -> JointModel:
    """Objectives (11)/(12)/(13), unchanged in FORM from M4.

    (11) and (12) sum over `m` only and were never workflow-indexed, so widening `W` does not
    touch them. (13) normalises by `sum_{w,s} lambda^avg`, which now spans two workflows -- and
    that is A76: its numerator adds `a_c` values from Code Generation (HumanEval pass@1) and
    Video Q/A (VideoMME), two different benchmarks with different meanings. A.5 averages them
    anyway, so the optimizer trades quality in one workflow against the other at an exchange rate
    that has no meaning.
    """
    adm = built.admissible
    e_m: dict[ModelProfileKey, float] = {}
    g_m: dict[ModelProfileKey, int] = {}
    c_g: dict[str, float] = {}
    a_c: dict[ConfigKey, float] = {}
    for sub in adm.per_slo.values():
        e_m.update({m: float(q.value) for m, q in sub.e_m.items()})
        g_m.update(sub.g_m)
        c_g.update({g: float(q.value) for g, q in sub.c_g.items()})
        a_c.update(sub.a_c)

    models = adm.models()
    if objective is Objective.ENERGY:
        expr = pulp.lpSum(
            built.n[m] * e_m[m] * g_m[m] * EPOCH_SECONDS for m in models if m in e_m
        )
        built.problem.sense = pulp.LpMinimize
        built.problem += expr, "eq11_energy_kwh"
    elif objective is Objective.COST:
        expr = pulp.lpSum(
            built.n[m] * g_m[m] * c_g[m.gpu] * EPOCH_SECONDS
            for m in models
            if m.gpu in c_g
        )
        built.problem.sense = pulp.LpMinimize
        built.problem += expr, "eq12_cost_usd"
    else:
        if not built.bounds_n_above():
            raise UnboundedObjective(
                "objective (13) does not minimise n_m, and neither eq. (6) nor eq. (7) is "
                "active, so the shared fleet is unbounded. Supply a budget."
            )
        if lam_avg_total <= 0:
            raise UnboundedObjective("objective (13) divides by sum lambda^avg; it is zero")
        accuracy = pulp.lpSum(
            var * a_c[c] for (_w, _s, c, _m), var in built.x_avg.items() if c in a_c
        ) / lam_avg_total
        cost_total = pulp.lpSum(
            built.n[m] * g_m[m] * c_g[m.gpu] * EPOCH_SECONDS
            for m in models
            if m.gpu in c_g
        )
        built.problem.sense = pulp.LpMaximize
        built.problem += accuracy - A5.EPSILON * cost_total, "eq13_accuracy_minus_cost"
    return built


@dataclass(frozen=True)
class JointResult:
    """One joint solve. Deliberately a NEW type rather than a widened `MilpResult` (Q29).

    M4's `MilpResult` carries single-workflow guarantees that 467 tests rely on. Widening it in
    place would have meant relaxing those guarantees everywhere to serve one new caller.
    """

    profile_set_name: str
    workflows: tuple[str, ...]
    slos: tuple[tuple[str, str], ...]
    epoch: int
    objective: Objective
    mu: MuChoice
    budget_choice: str
    status: MilpStatus
    objective_value: float | None
    n: Mapping[ModelProfileKey, int]
    x_peak: Mapping[JointKey, float]
    x_avg: Mapping[JointKey, float]
    wall_clock_s: float
    solver: str
    inactive_constraints: tuple[str, ...] = ()
    empty_slos: tuple[tuple[str, tuple[str, str]], ...] = ()
    nearest_misses: Mapping[str, str] = field(default_factory=dict)
    data_excluded: tuple[str, ...] = ()

    @property
    def total_gpus(self) -> int:
        return sum(self.n.values())

    def gpus_by_workflow(self) -> Mapping[str, float]:
        """**[OURS], and the answer is that it cannot be done honestly.**

        A GPU serves an `m`, and `n_m` is shared across workflows by construction -- that IS the
        multiplexing. Attributing it to a workflow requires a rule A.5 does not supply. We
        apportion by peak token demand, label it `[OURS]`, and note that any other rule would
        give different numbers with equal justification.
        """
        share: dict[str, float] = {w: 0.0 for w in self.workflows}
        by_model: dict[ModelProfileKey, float] = {}
        for (w, _s, _c, m), mass in self.x_peak.items():
            by_model[m] = by_model.get(m, 0.0) + mass
        for (w, _s, _c, m), mass in self.x_peak.items():
            if by_model.get(m, 0.0) > 0 and m in self.n:
                share[w] += self.n[m] * (mass / by_model[m])
        return share


def solve_joint(
    profile_set_obj: ProfileSet,
    workflows: Sequence[str],
    slos: Sequence[tuple[str, str]],
    objective: Objective,
    budget: BudgetChoice,
    mu: MuChoice,
    epoch: int = 0,
    backend: Backend | None = None,
    inputs: MilpInputs | None = None,
) -> JointResult:
    """Solve A.5 jointly over several workflows. `mu` and `budget` are both required."""
    inputs = inputs or profile_set_obj.to_milp_inputs()
    adm = build_joint_admissible(inputs, workflows, slos, objective)

    cost_limit = None
    if budget.eq6_active:
        o2 = solve_joint(
            profile_set_obj, workflows, slos, Objective.COST,
            BudgetChoice(name="tmp", resource=budget.resource), mu, epoch, backend, inputs,
        )
        if o2.objective_value is not None:
            cost_limit = o2.objective_value * budget.cost_multiplier

    built = build_joint_model(
        inputs, adm, mu, epoch, cost_budget=cost_limit, resource_budget=budget.resource
    )

    lam_avg_total = 0.0
    for (w, s) in adm.per_slo:
        _, avg = demand(inputs, w, s, epoch)
        lam_avg_total += float(avg.value)

    if not adm.is_infeasible:
        attach_joint(built, objective, lam_avg_total)

    if adm.is_infeasible:
        outcome_status = MilpStatus.INFEASIBLE_STRUCTURAL
        values_n, values_xp, values_xa = {}, {}, {}
        elapsed, backend_name, value = 0.0, (backend.name if backend else "CBC"), None
    else:
        outcome = solve_model(_AsBuilt(built), backend, SOLVER_TIME_LIMIT_S)
        outcome_status = outcome.status
        values_n = {m: int(round(v.value() or 0)) for m, v in built.n.items()}
        values_xp = {k: float(v.value() or 0.0) for k, v in built.x_peak.items()}
        values_xa = {k: float(v.value() or 0.0) for k, v in built.x_avg.items()}
        elapsed, backend_name, value = (
            outcome.wall_clock_s, outcome.backend, outcome.objective_value
        )

    ledger = adm.merged_ledger()
    return JointResult(
        profile_set_name=profile_set_obj.name,
        workflows=tuple(workflows),
        slos=tuple(slos),
        epoch=epoch,
        objective=objective,
        mu=mu,
        budget_choice=budget.describe(),
        status=outcome_status,
        objective_value=value,
        n=values_n,
        x_peak=values_xp,
        x_avg=values_xa,
        wall_clock_s=elapsed,
        solver=backend_name,
        inactive_constraints=built.inactive_constraints,
        empty_slos=adm.empty_slos,
        nearest_misses={
            f"{w}/{s[0]}-{s[1]}": adm.per_slo[(w, s)].empty.nearest_miss
            for (w, s) in adm.empty_slos
        },
        data_excluded=tuple(e.element for e in ledger.data_excluded),
    )


class _AsBuilt:
    """Adapter so `solve_model()` -- written for M4's `BuiltModel` -- can run a `JointModel`.

    Deliberately thin. The alternative was to widen `solve_model`'s signature, which would have
    made M4's single-workflow path carry joint-solve concerns for no benefit.
    """

    def __init__(self, joint: JointModel) -> None:
        self.problem = joint.problem
        self.n = joint.n
        self.x_peak = joint.x_peak
        self.x_avg = joint.x_avg

        class _Adm:
            is_empty = False

        self.admissible = _Adm()


__all__ = [
    "JointAdmissible",
    "JointKey",
    "JointModel",
    "JointResult",
    "attach_joint",
    "build_joint_admissible",
    "build_joint_model",
    "solve_joint",
]
