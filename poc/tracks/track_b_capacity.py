"""
B-C2 — Lagrangian relaxation of the CAPACITY constraint. T1's third arm.

Spec: PoC plan §5.3, T1 method step 3 — "Repeat relaxing (2) instead". Owner: 075.

The plan asks for three relaxations and until now two existed:

    relax (C1) assignment  -> track_b_lagr.py     decomposes PER PROFILE
    relax (C3) budget      -> track_b_budget.py   does not decompose
    relax (C2) capacity    -> this file           decomposes PER TASK

THE RELAXATION

    L(lambda) = Sum_m n[m] * (price(m) - lambda_m * thr(m))
              + Sum_t Sum_m lambda_m * load(t) * x[t][m]

    subject to (C1), (C3);  lambda_m >= 0

It splits into two independent pieces, and neither is per profile:

  * **The routing piece decomposes PER TASK.** With (C2) gone, nothing links one task's
    choice to another's, so each task independently takes the profile with the smallest
    `lambda_m * load(t)`. That is a third decomposition axis, and it is the one §3.1.7
    originally reached for when it claimed per-workflow subproblems — tasks are cheap to
    separate precisely because the constraint that couples them has been removed.

  * **The provisioning piece is an unbounded knapsack** over the GPU budget. A profile is
    worth opening only when `lambda_m * thr(m) > price(m)`; those with a negative coefficient
    are bought as heavily as (C3) allows.

WHY THE BOUND IS EXPECTED TO BE WEAK, AND WHY THAT IS THE POINT

(C2) is the constraint that carries the coupling. §1.7 says so explicitly: it couples tasks
to instances and tasks to each other, and the integrality gap lives in it. Relaxing the one
constraint that makes the problem hard buys an easy subproblem at the cost of a bound that
knows very little.

At lambda = 0 the bound is exactly 0 — every profile costs more than nothing, so nothing is
provisioned and no task contributes. The multiplier has to be driven up before the bound says
anything at all. Measuring how far it gets is what T1 asked for.
"""

from __future__ import annotations

import math
import time

from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId
from poc.tracks import track_a_greedy

STRATEGY = "B-C2"

ITERATION_CAP = 200
INITIAL_STEP = 2.0
PATIENCE = 15
MIN_STEP = 1e-4


def _provisioning_knapsack(profiles, lam, budget):
    """min Sum n[m]*(price - lambda*thr) s.t. Sum n[m]*gpu <= B, n integer >= 0.

    Only profiles with a negative coefficient are ever worth opening, so this is an
    unbounded knapsack over those, maximising the total saving within the GPU budget.
    """
    items = []
    for m, profile in profiles.items():
        coefficient = profile.price - lam[m] * profile.throughput
        if coefficient < 0:
            items.append((m, -coefficient, profile.gpus))     # saving per instance

    if not items or budget <= 0:
        return 0.0, {}

    best = [0.0] * (budget + 1)
    choice: list[str | None] = [None] * (budget + 1)
    for capacity in range(1, budget + 1):
        for m, saving, gpus in items:
            if gpus <= capacity and best[capacity - gpus] + saving > best[capacity]:
                best[capacity] = best[capacity - gpus] + saving
                choice[capacity] = m

    counts: dict[str, int] = {}
    capacity = budget
    while capacity > 0 and choice[capacity] is not None:
        m = choice[capacity]
        counts[m] = counts.get(m, 0) + 1
        capacity -= profiles[m].gpus

    return -best[budget], counts


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                STRATEGY, Infeasible("empty candidate pool", task.id, "C1"),
                time.perf_counter() - started)

    lam = {m: 0.0 for m in profiles}
    best_bound = -math.inf
    alpha, stale, iterations, converged = INITIAL_STEP, 0, 0, False

    # An incumbent for the step rule only; the bound never uses it.
    incumbent = track_a_greedy.allocate(tasks, pools, profiles, budget, seed=seed)
    upper = incumbent.total_cost if incumbent.feasible else None

    for iterations in range(1, ITERATION_CAP + 1):
        # --- routing piece: one independent decision per task --------------------
        routing_value = 0.0
        chosen: dict[TaskId, str] = {}
        for task in tasks:
            pick = min(pools[task.id], key=lambda m: (lam[m] * task.load, m))
            chosen[task.id] = pick
            routing_value += lam[pick] * task.load

        # --- provisioning piece: unbounded knapsack over the budget --------------
        provisioning_value, counts = _provisioning_knapsack(profiles, lam, budget)

        bound = routing_value + provisioning_value
        if bound > best_bound + 1e-9:
            best_bound, stale = bound, 0
        else:
            stale += 1

        # --- subgradient: violation of (C2) per profile --------------------------
        routed: dict[str, float] = {}
        for task in tasks:
            routed[chosen[task.id]] = routed.get(chosen[task.id], 0.0) + task.load
        gradient = {m: routed.get(m, 0.0) - counts.get(m, 0) * profiles[m].throughput
                    for m in profiles}

        norm_sq = sum(g * g for g in gradient.values())
        if norm_sq < 1e-12:
            converged = True
            break
        if stale >= PATIENCE:
            alpha /= 2.0
            stale = 0
        if alpha < MIN_STEP:
            converged = True
            break

        reference = upper if upper is not None else best_bound + abs(best_bound) + 1.0
        step = alpha * max(reference - bound, 1e-9) / norm_sq
        for m in profiles:
            lam[m] = max(0.0, lam[m] + step * gradient[m])

    elapsed = time.perf_counter() - started

    # This arm produces a BOUND. Its relaxed solution ignores (C2) entirely, so it has no
    # primal of its own; greedy's answer is reported as the incumbent and labelled as such.
    if not incumbent.feasible:
        # This arm's bound never depended on the incumbent in the first place (F34).
        return AllocationResult.failure(
            STRATEGY, Infeasible("no feasible incumbent", None, "C3"), elapsed,
            lower_bound=best_bound if best_bound > -math.inf else None)

    result = AllocationResult(
        routing=incumbent.routing, provisioning=incumbent.provisioning,
        total_cost=incumbent.total_cost, gpus_used=incumbent.gpus_used,
        strategy=STRATEGY,
        lower_bound=best_bound if best_bound > -math.inf else None,
        iterations=iterations, converged=converged,
        compute_time=elapsed, feasible=True,
    )
    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track B-C2 produced a result violating {violations}")
    return result
