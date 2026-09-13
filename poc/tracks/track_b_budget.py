"""
B-C3 — Lagrangian relaxation of the BUDGET constraint, the other arm of T1.

Spec: docs/design/System_Architecture_v2.md §5.2.3. Owner: 075.

WHY THIS EXISTS

T1 asks which constraint Track B should relax, and §5.2.3 offers two candidates:

    relax (C1) assignment  -> (C2) per profile, (C3) global -> decomposes PER PROFILE
    relax (C3) budget      -> (C1) still couples profiles through tasks -> does not decompose

`track_b_lagr.py` implements the first, on §1.8's prediction. Until this module existed, the
second had never been built, so T1's central question was answered by assumption rather than
by measurement. This is the control.

THE RELAXATION

    L(mu) = min  Sum_m n[m]*price(m) + mu * (Sum_m n[m]*gpu(m) - B)
          = -mu*B  +  min Sum_m n[m] * (price(m) + mu*gpu(m))

    subject to (C1), (C2), x binary, n integer;  mu >= 0

Because (C3) is an inequality, mu is restricted to be non-negative.

WHAT IS LEFT BEHIND IS THE PROBLEM, MINUS A BUDGET

Dropping (C3) does not simplify the structure. (C1) still forces each task to choose exactly
one profile, and that choice still couples every profile to every other through the tasks.
The remaining problem is an uncapacitated-budget facility location instance — **still
NP-hard, and still not decomposable**.

So the subproblem here has to be solved by the MILP itself, with GPU-adjusted prices. That
is the finding rather than an implementation shortcut: **each iteration costs a full exact
solve.** A relaxation whose subproblem is as hard as the original problem cannot pay for
itself, and the multiplier only has to be searched because the budget was removed in the
first place.

Contrast `track_b_lagr.py`, where relaxing (C1) leaves one independent knapsack per profile.
That is what "decomposes" means, and it is the difference T1 is asking about.
"""

from __future__ import annotations

import time

import pulp

from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId

STRATEGY = "B-C3"

ITERATION_CAP = 25          # each iteration is a full MILP solve, so this is deliberately low
INITIAL_MU = 0.0
STEP_SCALE = 1.5


def _solve_budget_relaxed(tasks, pools, profiles, mu):
    """min Sum n[m]*(price + mu*gpu) subject to (C1) and (C2). No budget.

    Returns (objective_without_the_mu_B_term, provisioning, routing) or None.
    """
    problem = pulp.LpProblem("BudgetRelaxed", pulp.LpMinimize)

    x = {(t.id, m): pulp.LpVariable(
            f"x_{t.id.workflow_id}_{t.id.task_name}_{m}", cat="Binary")
         for t in tasks for m in pools[t.id]}
    total_load = sum(t.load for t in tasks)
    n = {m: pulp.LpVariable(
            f"n_{m}", lowBound=0,
            upBound=int(-(-total_load // p.throughput)) + 1, cat="Integer")
         for m, p in profiles.items()}

    problem += pulp.lpSum(n[m] * (profiles[m].price + mu * profiles[m].gpus)
                          for m in profiles)

    for task in tasks:
        problem += pulp.lpSum(x[(task.id, m)] for m in pools[task.id]) == 1
    for m in profiles:
        routed = pulp.lpSum(x[(t.id, m)] * t.load for t in tasks if m in pools[t.id])
        problem += routed <= n[m] * profiles[m].throughput

    # This is called once per subgradient iteration, so an unbounded solve here is
    # far worse than in exact_milp. Deliberately tighter.
    problem.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=30))
    if pulp.LpStatus[problem.status] != "Optimal":
        return None

    provisioning = {m: int(round(n[m].value() or 0)) for m in profiles
                    if round(n[m].value() or 0) > 0}
    routing = {t.id: m for t in tasks for m in pools[t.id]
               if round(x[(t.id, m)].value() or 0) == 1}
    return pulp.value(problem.objective), provisioning, routing


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    """Subgradient ascent on the single budget multiplier."""
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                STRATEGY,
                Infeasible("empty candidate pool", task.id, "C1"),
                time.perf_counter() - started)

    mu = INITIAL_MU
    best_bound = -float("inf")
    best_feasible = None
    iterations = 0
    converged = False

    for iterations in range(1, ITERATION_CAP + 1):
        outcome = _solve_budget_relaxed(tasks, pools, profiles, mu)
        if outcome is None:
            break
        adjusted, provisioning, routing = outcome

        bound = adjusted - mu * budget
        best_bound = max(best_bound, bound)

        gpus = sum(count * profiles[m].gpus for m, count in provisioning.items())

        # The relaxed solution happens to respect the budget: it is feasible for the
        # original problem, and it is optimal for it too, so we can stop.
        if gpus <= budget:
            cost = sum(count * profiles[m].price for m, count in provisioning.items())
            if best_feasible is None or cost < best_feasible[0]:
                best_feasible = (cost, routing, provisioning, gpus)
            converged = True
            break

        # Subgradient on mu: g = Sum n[m]*gpu(m) - B, positive when over budget.
        gradient = gpus - budget
        step = STEP_SCALE * max(abs(bound), 1.0) / max(gradient ** 2, 1)
        mu = max(0.0, mu + step * gradient)

    elapsed = time.perf_counter() - started

    if best_feasible is None:
        return AllocationResult.failure(
            STRATEGY,
            Infeasible("budget-relaxed search never produced a within-budget allocation",
                       None, "C3"),
            elapsed)

    cost, routing, provisioning, gpus = best_feasible
    result = AllocationResult(
        routing=routing, provisioning=provisioning,
        total_cost=cost, gpus_used=gpus,
        strategy=STRATEGY,
        lower_bound=best_bound if best_bound > -float("inf") else None,
        iterations=iterations, converged=converged,
        compute_time=elapsed, feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track B-C3 produced a result violating {violations}")
    return result
