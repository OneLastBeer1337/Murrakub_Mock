"""
The MILP Workflow Optimizer -- Murakkab (OSDI '26) Section 3.3.1 (p.574) and Appendix A.5
(pp.586-587).

    "The workflow optimizer ... jointly selects, for every workflow, a configuration and a model
    profile, and decides how many instances of each model to run." (Section 3.3.1)

WHAT THIS PACKAGE IS. Once per epoch, given a demand forecast and M3's profiles, it answers:
which version of the workflow, on which model, on which hardware, and how many instances? It
decides **assignment** (`x`) and **provisioning** (`n`). It does not decide **ordering** -- there
is no precedence, no start time, no makespan, because A.5 has none.

THE ONE IMPORT RULE. `MilpInputs` is the only thing this package takes from the profile layer,
and nothing from `/development/` is imported at all -- M4 must not read a DAG (DESIGN.md Section
10.1). Both are asserted by static import analysis in `tests/test_milp_formulation.py`.

WHAT YOU MUST SUPPLY, BECAUSE IT HAS NO DEFAULT:

  * `workflow` -- M4 is single-workflow (`|W| = 1`). There is no "all workflows" default; an
    unintended two-workflow solve would pre-empt M5's multiplexing experiment.
  * `budget` -- a `BudgetChoice`, including the explicitly-named `no_budget()`. Eq. (7) is the
    only thing bounding allocation, so falling into its absence is not allowed (A43).

WHAT THE ANSWERS ARE NOT. Read `MilpResult.caveats()` before quoting any number. Every GPU count
is for LLM executors only; roughly an eighth of the profile set is `Unavailable` and the excluded
set differs between runs (A71); and under `baseline`, latency-tier runs are EXPECTED to be
infeasible (A37) -- that is a result, not a bug.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from optimization.milp.critique import incoherence, structural_record
from optimization.milp.model import NO_MULTIPLEXING, build_model
from optimization.milp.objectives import (
    AccuracyWeighting,
    Objective,
    UnboundedObjective,
    attach,
)
from optimization.milp.report import MilpResult, compare_runs, support_size
from optimization.milp.scenarios import BudgetChoice, cost_budget, no_budget, table_3
from optimization.milp.sets import build_admissible, demand, epochs_of, slo_space
from optimization.milp.solve import DEFAULT_BACKEND, Backend, MilpStatus, solve_model
from optimization.profiles.schema import MilpInputs, ProfileSet
from optimization.profiles.sources.tables import SOLVER_TIME_LIMIT_S

FIDELITY_NOTES: tuple[str, ...] = (
    "A57: c_g and B_g are per GPU, not per instance -- eqs. (6), (7) and (12) multiply by g_m",
    "A58: A.5's 13 numbered equations are 10 distinct ones; (8)=(4), (9)=(5), (10)=(6)",
    "A66: the SLO filters constrain x^peak only; x^avg is unfiltered and never sizes the fleet",
    "A69: no inter-epoch coupling exists in A.5 -- fleets may be rebuilt hourly at zero cost",
    "A72: eq. (6) prices consumption while eq. (12) prices provisioning; nothing ties them",
    "eq. (11) cannot distinguish two models on the same GPU type (A41)",
)


def solve(
    profile_set_obj: ProfileSet,
    workflow: str,
    slo: tuple[str, str],
    objective: Objective,
    budget: BudgetChoice,
    epoch: int = 0,
    weighting: AccuracyWeighting = AccuracyWeighting.AVG,
    backend: Backend | None = None,
    inputs: MilpInputs | None = None,
) -> MilpResult:
    """Solve one `(workflow, SLO, epoch)` under one objective. The package's entry point.

    `budget` is required and has no default -- see the module docstring. For objective (13) it
    must activate eq. (6) or eq. (7), or `UnboundedObjective` is raised rather than a
    plausible-looking number returned.
    """
    # NOTE: the budget is NOT pushed back through `to_milp_inputs()`. `B_g` stays `Unavailable`
    # there, which is the truthful profile-layer statement (A43 -- the paper reports none), and
    # `model.py` receives the chosen budget directly as plain GPU counts. Round-tripping it
    # through the profile layer would have dressed a caller's experiment coordinate up as
    # profile data.
    inputs = inputs or profile_set_obj.to_milp_inputs()
    needs_energy = objective is Objective.ENERGY
    adm = build_admissible(inputs, workflow, slo, objective_needs_energy=needs_energy)

    cost_limit: float | None = None
    if budget.eq6_active:
        # Q23: the cost budget is a MULTIPLE of eq. (12)'s optimum for the same run, never an
        # absolute dollar figure -- absolutes are not comparable across profile sets.
        o2 = solve(
            profile_set_obj, workflow, slo, Objective.COST, no_budget(), epoch,
            weighting, backend, inputs,
        )
        if o2.objective_value is not None:
            cost_limit = o2.objective_value * budget.cost_multiplier

    built = build_model(
        inputs,
        adm,
        epoch=epoch,
        cost_budget=cost_limit,
        resource_budget=budget.resource,
    )

    lam_avg_total = None
    if objective is Objective.ACCURACY:
        _, avg = demand(inputs, workflow, slo, epoch)
        lam_avg_total = float(avg.value)

    if not adm.is_empty:
        attach(built, objective, weighting, lam_avg_total)

    outcome = solve_model(built, backend, SOLVER_TIME_LIMIT_S)

    x_for_reporting = outcome.x_peak or outcome.x_avg
    tau_value = inputs.tau.get((workflow, slo[0], slo[1]))
    tau_float = None
    if tau_value is not None and hasattr(tau_value, "value"):
        try:
            tau_float = float(tau_value.value)
        except Exception:
            tau_float = None

    return MilpResult(
        profile_set_name=profile_set_obj.name,
        operating_point_policy=inputs.operating_point_policy,
        token_policy=inputs.token_policy,
        workflow=workflow,
        slo=slo,
        epoch=epoch,
        objective=objective,
        budget_choice=budget.describe(),
        cost_budget=cost_limit,
        solver=outcome.backend,
        time_limit_s=SOLVER_TIME_LIMIT_S,
        status=outcome.status,
        objective_value=outcome.objective_value,
        n=outcome.n,
        x_peak=outcome.x_peak,
        x_avg=outcome.x_avg,
        wall_clock_s=outcome.wall_clock_s,
        gap=outcome.gap,
        data_excluded=tuple(e.element for e in adm.ledger.data_excluded),
        exclusion_ledger=adm.ledger,
        inactive_constraints=built.inactive_constraints,
        equation_map=dict(_DUPLICATES),
        incoherent_mass=incoherence.measure(inputs, x_for_reporting),
        support_size=support_size(x_for_reporting),
        structural_record=structural_record.build_record(
            workflow=workflow,
            slo=slo,
            x=x_for_reporting,
            t_c={c: float(q.value) for c, q in adm.t_c.items()},
            l_ttft={m: v for m, v in _floats(inputs.l_ttft_m).items()},
            l_tpot={m: v for m, v in _floats(inputs.l_tpot_m).items()},
            eq5=adm.eq5_value,
            tau=tau_float,
        ),
        fidelity_notes=FIDELITY_NOTES,
        accuracy_weighting=weighting,
        structural_reason=adm.empty.emptied_by if adm.is_empty else "",
        nearest_miss=adm.empty.nearest_miss if adm.is_empty else "",
    )


def _floats(mapping) -> dict:
    out = {}
    for k, v in mapping.items():
        try:
            out[k] = float(v.value)
        except Exception:
            continue
    return out


_DUPLICATES = {8: 4, 9: 5, 10: 6}

__all__ = [
    "AccuracyWeighting",
    "BudgetChoice",
    "FIDELITY_NOTES",
    "MilpResult",
    "MilpStatus",
    "NO_MULTIPLEXING",
    "Objective",
    "UnboundedObjective",
    "compare_runs",
    "cost_budget",
    "epochs_of",
    "no_budget",
    "slo_space",
    "solve",
    "table_3",
]
