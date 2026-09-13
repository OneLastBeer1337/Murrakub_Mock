"""
Exact reference — direct MILP encoding of §1.4-1.6 in PuLP with CBC.

Spec: docs/design/System_Architecture_v2.md §5.2.5.
Build step 4 — BEFORE any heuristic.
Verified by: returns 280 on instances/fixtures/adversarial_3t2p.
Owner: 089

Not a track. Ground truth for small-instance testing and the evaluation baseline.

    minimize   Σ_m n[m]·price(m)
    s.t.       (C1)  Σ_{m ∈ C(t)} x[t][m] = 1                       ∀t
               (C2)  Σ_t x[t][m]·load(t)  ≤  n[m]·thr(m)            ∀m
               (C3)  Σ_m n[m]·gpu(m)  ≤  B
               x[t][m] ∈ {0,1},  n[m] ∈ Z⁺

Two things this encoding does NOT do, both deliberate:

  * No linking constraint. If x[t][m]=1 and load(t)>0, (C2) forces n[m] ≥ 1, so an
    explicit x ≤ y would be redundant (v2 §1.6). Note the load(t)>0 caveat is load-bearing:
    a zero-load task would leave n[m] free at 0 and violate I5. The generator draws
    load > 0 and this asserts it rather than trusting it.
  * No floor constraints. Floors are applied when building C(t); x variables only exist
    for eligible pairs, so an ineligible assignment is not representable.

The PuLP + CBC scaffolding follows docs/v1_superseded/offline_baselines/milp_baseline.py,
but not its formulation — that one has no n[m] at all and charges GPUs per task assignment.
"""

from __future__ import annotations

import math
import time

import pulp

from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId

STRATEGY = "MILP"

# Seconds. CBC has no default limit, and on a pathological 128-task instance it will grind
# essentially without bound — a statistics run was killed after an hour on one. The limit is
# generous enough that ordinary instances still solve to proven optimality.
DEFAULT_TIME_LIMIT = 120


def _instance_upper_bound(profile: ProfileSpec, total_load: float, budget: int) -> int:
    """A finite, valid cap on n[m]. Unbounded integers make CBC work harder than it needs.

    Never provisioning more than covers all load, nor more than the budget can pay for.

    THIS CAP MUST NOT BIND. It exists only to keep CBC from searching an unbounded integer
    range; if it were ever tighter than the true optimum needs, CBC would return a
    suboptimal answer — or none — and report it as optimal. Every other number in the PoC
    is measured against this solver, so that failure would be silent and total.

    Hence the deliberate slack: covering the entire batch's load on a single profile is
    already far more than any optimal solution provisions, and there is a further +1 on
    top. test_the_instance_cap_never_binds checks this empirically against a generous cap.

    An earlier version scaled to integers by hand (int(total_load * 100)), which truncated
    and quietly assumed the generator's 2-decimal loads. It is a plain ceiling now.
    """
    by_load = math.ceil(round(total_load / profile.throughput, 9)) + 1
    if profile.gpus == 0:
        return max(0, by_load)
    by_budget = budget // profile.gpus
    return max(0, min(by_load, by_budget))


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0,
             time_limit: int | None = None) -> AllocationResult:
    """Solve to proven optimality where possible. seed is accepted for interface parity (P5).

    `converged` is the honest signal and callers MUST check it:

        converged=True   CBC proved optimality. Safe to use as ground truth.
        converged=False  the time limit was hit. The result is feasible but NOT proven
                         optimal, so any gap measured against it is meaningless.

    Without a limit CBC can run unboundedly on a hard instance. Without `converged`, a
    timed-out answer would be silently reported as the optimum and every gap in the project
    measured against it would be wrong — the same class of failure the n[m] cap test guards
    against, arriving from a different direction.
    """
    started = time.perf_counter()
    # Read at call time, not bound at definition, so experiments can lower it globally.
    if time_limit is None:
        time_limit = DEFAULT_TIME_LIMIT

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                STRATEGY,
                Infeasible("empty candidate pool — registry or floors too strict",
                           task.id, "C1"),
                time.perf_counter() - started)
        if task.load <= 0:
            raise ValueError(
                f"task {task.id} has load {task.load}; the no-linking-constraint argument "
                f"in v2 §1.6 requires load > 0")

    total_load = sum(t.load for t in tasks)
    problem = pulp.LpProblem("TwoLevelAllocation", pulp.LpMinimize)

    x = {(t.id, m): pulp.LpVariable(f"x_{t.id.workflow_id}_{t.id.task_name}_{m}",
                                    cat="Binary")
         for t in tasks for m in pools[t.id]}
    n = {m: pulp.LpVariable(f"n_{m}", lowBound=0,
                            upBound=_instance_upper_bound(p, total_load, budget),
                            cat="Integer")
         for m, p in profiles.items()}

    problem += pulp.lpSum(n[m] * profiles[m].price for m in profiles), "TotalCost"

    for task in tasks:
        problem += (pulp.lpSum(x[(task.id, m)] for m in pools[task.id]) == 1,
                    f"C1_{task.id.workflow_id}_{task.id.task_name}")

    for m in profiles:
        routed = pulp.lpSum(x[(t.id, m)] * t.load for t in tasks if m in pools[t.id])
        problem += (routed <= n[m] * profiles[m].throughput, f"C2_{m}")

    problem += (pulp.lpSum(n[m] * profiles[m].gpus for m in profiles) <= budget, "C3")

    problem.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    elapsed = time.perf_counter() - started
    status = pulp.LpStatus[problem.status]

    if status == "Infeasible":
        return AllocationResult.failure(
            STRATEGY,
            Infeasible("no allocation fits the GPU budget", None, "C3"),
            elapsed)

    has_solution = all(x[(t.id, m)].value() is not None
                       for t in tasks for m in pools[t.id])
    if status != "Optimal" and not has_solution:
        return AllocationResult.failure(
            STRATEGY,
            Infeasible(f"MILP returned {status} within {time_limit}s with no incumbent",
                       None, "C3"),
            elapsed)

    proven = status == "Optimal"

    routing = {t.id: m for t in tasks for m in pools[t.id]
               if round(x[(t.id, m)].value() or 0) == 1}
    provisioning = {m: int(round(n[m].value() or 0)) for m in profiles
                    if round(n[m].value() or 0) > 0}
    total_cost = sum(count * profiles[m].price for m, count in provisioning.items())
    gpus_used = sum(count * profiles[m].gpus for m, count in provisioning.items())

    result = AllocationResult(
        routing=routing, provisioning=provisioning,
        total_cost=total_cost, gpus_used=gpus_used,
        strategy=STRATEGY,
        # The bound equals the cost only when optimality was PROVEN. A timed-out incumbent
        # is an upper bound on the optimum, not the optimum, so it reports no lower bound.
        lower_bound=total_cost if proven else None,
        converged=proven,
        compute_time=elapsed, feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        if proven:
            # v2 §4.1: verification failure is an internal error. Fail loudly — a MILP that
            # PROVED optimality yet violates its own constraints means the encoding is wrong.
            raise RuntimeError(f"exact MILP produced a result violating {violations}")
        # Not proven, and the incumbent does not satisfy the constraints. CBC can return
        # leftover variable values when it times out before finding anything feasible, so
        # this is a normal outcome of a tight limit rather than a bug. Report no incumbent
        # instead of trusting values that were never a solution.
        return AllocationResult.failure(
            STRATEGY,
            Infeasible(f"MILP hit its {time_limit}s limit with no feasible incumbent "
                       f"(violated {violations})", None, "C3"),
            elapsed)

    return result
