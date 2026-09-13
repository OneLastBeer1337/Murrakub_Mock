"""
Track B-C3 — Lagrangian relaxation of the GPU budget constraint (C3).

Spec: docs/design/System_Architecture_v2.md §1.8, §5.2.3.
Owner: 075

THE ALTERNATIVE RELAXATION FOR T1.
Track B in track_b_lagr.py relaxes (C1), decomposing per profile into 0/1 knapsack subproblems.
This module relaxes (C3) instead:

    L(μ) = -μ · B + min_{x, n} Σ_m n[m] · (price(m) + μ · gpu(m))
    subject to (C1) Σ_{m ∈ C(t)} x[t][m] = 1   ∀t
               (C2) Σ_t x[t][m] · load(t) ≤ n[m] · thr(m)   ∀m
               x[t][m] ∈ {0,1}, n[m] ∈ Z⁺, μ ≥ 0

Under continuous n[m], the subproblem decomposes completely PER TASK:
each task independently chooses m ∈ C(t) minimizing effective rate:
    (price(m) + μ · gpu(m)) / thr(m)

The dual problem max_{μ ≥ 0} L(μ) is a 1-dimensional concave maximization problem.
Because μ is a scalar, finding the optimal multiplier μ* is solved efficiently
via 1D subgradient search and bisection.

This answers T1 / O2: comparing the bound of (C3) relaxation against (C1) relaxation
and Track C's LP bound.
"""

from __future__ import annotations

import math
import time

from poc.core.decision_rule import select_profile
from poc.core.provisioning import ProvisioningState
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId
from poc.tracks import track_a_greedy

STRATEGY = "B-C3"

# Search parameters for 1D dual optimization
MAX_DUAL_ITERATIONS = 60
MU_MAX = 500.0


def _evaluate_dual(mu: float, tasks: list[Task], pools: dict[TaskId, list[str]],
                   profiles: dict[str, ProfileSpec], budget: int):
    """Evaluate L(mu) under continuous instance relaxation and compute subgradient."""
    total_task_val = 0.0
    best_picks: dict[TaskId, str] = {}
    fractional_gpus = 0.0

    for task in tasks:
        best_m = None
        best_rate = float("inf")
        for m in pools[task.id]:
            p = profiles[m]
            eff_rate = (p.price + mu * p.gpus) / p.throughput
            if eff_rate < best_rate or (eff_rate == best_rate and (best_m is None or m < best_m)):
                best_rate = eff_rate
                best_m = m

        best_picks[task.id] = best_m
        total_task_val += task.load * best_rate
        p_best = profiles[best_m]
        fractional_gpus += (task.load / p_best.throughput) * p_best.gpus

    bound = total_task_val - mu * budget
    subgradient = fractional_gpus - budget  # > 0 means over budget, increase mu
    return bound, best_picks, subgradient


def _repair_primal(candidate_routing: dict[TaskId, str],
                    tasks: list[Task],
                    pools: dict[TaskId, list[str]],
                    profiles: dict[str, ProfileSpec],
                    budget: int) -> tuple[ProvisioningState, dict[TaskId, str]] | None:
    """Attempt to realize the candidate routing within budget, repairing unplaceable tasks."""
    state = ProvisioningState(profiles, budget)
    routing: dict[TaskId, str] = {}

    for task in sorted(tasks, key=lambda t: (-t.load, t.id)):
        preferred = candidate_routing.get(task.id)
        choice = None
        if preferred is not None and state.cost_to_admit(task, preferred) is not None:
            choice = preferred
        else:
            choice = select_profile(task, pools[task.id], state, lambda m, admit: admit.extra_cost)

        if choice is None:
            return None

        state.admit(task, choice)
        routing[task.id] = choice

    return state, routing


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0,
             warm_start: bool = True,
             strategy: str = STRATEGY) -> AllocationResult:
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                strategy,
                Infeasible("empty candidate pool — registry or floors too strict",
                           task.id, "C1"),
                time.perf_counter() - started)

    # 1. Warm start
    best_result: AllocationResult | None = None
    if warm_start:
        incumbent = track_a_greedy.allocate(tasks, pools, profiles, budget, seed=seed)
        if incumbent.feasible:
            best_result = incumbent

    # 2. 1D Bisection / Ternary Search for max_{mu >= 0} L(mu)
    low_mu = 0.0
    high_mu = MU_MAX

    best_bound = 0.0
    best_candidate_routing = {}

    # Ternary search on concave 1D dual function
    for _ in range(MAX_DUAL_ITERATIONS):
        m1 = low_mu + (high_mu - low_mu) / 3.0
        m2 = high_mu - (high_mu - low_mu) / 3.0

        b1, r1, _ = _evaluate_dual(m1, tasks, pools, profiles, budget)
        b2, r2, _ = _evaluate_dual(m2, tasks, pools, profiles, budget)

        if b1 > best_bound:
            best_bound = b1
            best_candidate_routing = r1
        if b2 > best_bound:
            best_bound = b2
            best_candidate_routing = r2

        if b1 < b2:
            low_mu = m1
        else:
            high_mu = m2

    # 3. Attempt primal recovery with best candidate routing
    repaired = _repair_primal(best_candidate_routing, tasks, pools, profiles, budget)
    if repaired is not None:
        state, routing = repaired
        candidate_result = AllocationResult(
            routing=routing,
            provisioning=state.build_provisioning(),
            total_cost=state.total_cost(),
            gpus_used=state.gpus_used(),
            strategy=strategy,
            lower_bound=best_bound,
            compute_time=time.perf_counter() - started,
            feasible=True,
        )
        if best_result is None or candidate_result.total_cost < best_result.total_cost:
            best_result = candidate_result

    if best_result is None or not best_result.feasible:
        # The dual bound is valid even though the repair failed (F34).
        return AllocationResult.failure(
            strategy,
            Infeasible("dual subproblem could not be repaired into budget feasibility",
                       None, "C3"),
            time.perf_counter() - started,
            lower_bound=best_bound if math.isfinite(best_bound) else None)

    best_result.strategy = strategy
    best_result.lower_bound = best_bound
    best_result.compute_time = time.perf_counter() - started

    violations = invariants.check(best_result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"{strategy} produced a result violating {violations}")

    return best_result
