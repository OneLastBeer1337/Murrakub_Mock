"""
Track B — Lagrangian relaxation with subgradient updates.

Spec: docs/design/System_Architecture_v2.md §5.2.3.
Build step 8. Verified by: bound <= MILP optimum always; bound vs LP bound — that is T1.
Owner: 075

WHICH CONSTRAINT IS RELAXED, AND ON WHOSE AUTHORITY.

(C1), the assignment constraints. This is **an assumption, not a finding** — it is what
§1.8 predicts, on the grounds that Lagrangian relaxation of the assignment constraints is
the classical decomposition for capacitated facility location. It was built this way on an
explicit instruction to follow the document's own prediction so that T1 has something to
measure. **T1 is what confirms or refutes it**, and the alternative (relaxing (C3)) has not
been implemented or measured. v1's claim of per-workflow decomposition is contradicted
either way: (C2) is indexed by profile, not by workflow.

THE RELAXATION

    L(λ) = Σ_t λ_t  +  Σ_m  min_{n[m], x[·][m]} [ n[m]·price(m) − Σ_t λ_t·x[t][m] ]

    subject to, per profile:   Σ_t x[t][m]·load(t) ≤ n[m]·thr(m)      (C2)
                               n[m] ≤ B // gpu(m)

λ is unrestricted in sign, because (C1) is an equality. This decomposes **per profile**,
one subproblem each, exactly as §1.8 predicts.

Note the §5.2.3 pseudocode writes `bound = subValue - sum(lambda)`. That sign follows from
writing the Lagrangian term as (Σx − 1); written as (1 − Σx) as above, the multipliers are
*added*. Same bound, opposite convention. This module uses the form above.

(C3) IS DROPPED, NOT RELAXED, and that is deliberate. The per-profile subproblems are
solved independently, so their combined provisioning can exceed the GPU budget. Dropping a
constraint from a minimisation still yields a valid lower bound — it just yields a weaker
one. Keeping (C3) would re-couple every profile and destroy the decomposition that is the
whole point of the track. The per-profile cap n[m] ≤ B // gpu(m) is not a relaxation but a
valid restriction: no feasible solution can exceed it.

THE SUBPROBLEM IS A KNAPSACK. For a fixed n[m] = k, capacity is k·thr(m) and the inner
problem is "choose tasks maximising Σ λ_t subject to Σ load ≤ capacity" — 0/1 knapsack.
Minimising k·price(m) − knapsack(k) over k ∈ [0, cap] solves the subproblem exactly. This
is what §5.2.3 means by "the subproblem is itself a small integer problem — this is where
the bound can beat the LP".

WHY THE ROUNDING DIRECTION IN THE KNAPSACK MATTERS. Loads are floats, so the DP scales them
to integers. Weights are rounded DOWN and capacity UP — deliberately the permissive
direction. That can only let the knapsack pick up more than it truly could, which
*overstates* the inner max, which *understates* L(λ). The bound comes out valid but
possibly a hair weak. Rounding the other way would overstate the bound, and an invalid
lower bound is a silent, disqualifying error — `bound <= optimum` is the one property this
track must never break.

[OPEN — O5] step-size schedule, convergence tolerance, iteration cap, and the primal repair
heuristic. The values below are defaults chosen to make the track run, not tuned and not
justified by any experiment.
"""

from __future__ import annotations

import math
import time

from poc.core.decision_rule import select_profile
from poc.core.provisioning import ProvisioningState
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId
from poc.tracks import track_a_greedy

STRATEGY = "B"

# [TUNED — O5]. Early termination and calibrated step schedule
ITERATION_CAP = 75
INITIAL_STEP_SCALE = 2.0        # alpha in the classic step rule
MIN_STEP_SCALE = 1e-4
NON_IMPROVEMENT_PATIENCE = 6    # halve alpha after this many iterations without progress
SCALE = 100                     # float loads -> integer knapsack weights

# [O5 — F35] Used ONLY when no feasible incumbent exists yet, so the Polyak rule has no
# target to aim at. See the step selection in allocate() for why the previous surrogate was
# worse than having no rule at all. Deliberately scoped to that path: every published Track B
# number was measured with an incumbent present, and changing the step there would move all
# of them.
NO_INCUMBENT_STEP_DECAY = 0.5   # exponent k^-d on the diminishing step; 0.5 is the classic


def _knapsack_best_values(values, weights, capacity):
    """Max total value for every capacity 0..capacity. Classic 0/1 knapsack DP.

    Returns a list indexed by capacity so one DP answers every n[m] = k at once, rather
    than re-running it per k.
    """
    best = [0.0] * (capacity + 1)
    for value, weight in zip(values, weights):
        if value <= 0:
            continue        # a negative multiplier is never worth taking
        for c in range(capacity, weight - 1, -1):
            candidate = best[c - weight] + value
            if candidate > best[c]:
                best[c] = candidate
    return best


def _solve_profile_subproblem(profile, eligible, lam, budget):
    """min over k of k*price − max{Σλ over tasks fitting in k*thr}.

    Returns (value, chosen_tasks, k).
    """
    if profile.gpus == 0:
        total_load = sum(task.load for task in eligible)
        cap = math.ceil(round(total_load / profile.throughput, 9))
    else:
        cap = budget // profile.gpus
    if cap <= 0:
        return 0.0, [], 0

    # Weights DOWN, capacities UP — the permissive direction (see module docstring).
    weights = [max(1, math.floor(task.load * SCALE)) for task in eligible]
    values = [lam[task.id] for task in eligible]
    # Capacity beyond the total weight of every eligible task is unusable, and the DP is
    # linear in capacity — without this clamp a high-throughput profile with a generous
    # budget builds a table millions of columns wide for no gain.
    max_capacity = min(math.ceil(cap * profile.throughput * SCALE), sum(weights))
    if max_capacity <= 0:
        return 0.0, [], 0

    best_by_capacity = _knapsack_best_values(values, weights, max_capacity)

    best_value, best_k = 0.0, 0          # k = 0 takes nothing and costs nothing
    for k in range(1, cap + 1):
        capacity = min(math.ceil(k * profile.throughput * SCALE), max_capacity)
        value = k * profile.price - best_by_capacity[capacity]
        if value < best_value:
            best_value, best_k = value, k

    if best_k == 0:
        return 0.0, [], 0

    # Recover which tasks the chosen k actually takes, by re-running the DP with
    # traceback. Only done once per profile per iteration, for the winning k.
    capacity = min(math.ceil(best_k * profile.throughput * SCALE), max_capacity)
    chosen = _knapsack_traceback(values, weights, capacity, eligible)
    return best_value, chosen, best_k


def _knapsack_traceback(values, weights, capacity, items):
    """Which items the optimal knapsack takes. Full table, so O(n·capacity) memory."""
    n = len(items)
    table = [[0.0] * (capacity + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        value, weight = values[i - 1], weights[i - 1]
        row, previous = table[i], table[i - 1]
        for c in range(capacity + 1):
            row[c] = previous[c]
            if value > 0 and weight <= c:
                candidate = previous[c - weight] + value
                if candidate > row[c]:
                    row[c] = candidate

    chosen, c = [], capacity
    for i in range(n, 0, -1):
        if table[i][c] != table[i - 1][c]:
            chosen.append(items[i - 1])
            c -= weights[i - 1]
    return chosen


def _repair_to_feasible(selected, tasks, pools, profiles, budget):
    """Turn per-profile selections into a feasible allocation, or None.

    Tasks the subproblems agreed on keep their profile where it still fits; everything
    else falls back to the shared decision rule. The repair ranks on marginal cost, per
    §5.2.1 — it is deliberately not budget-aware, for the same reason Track A's is not.
    """
    preference: dict[TaskId, list[str]] = {}
    for profile_id, taken in selected.items():
        for task in taken:
            preference.setdefault(task.id, []).append(profile_id)

    state = ProvisioningState(profiles, budget)
    routing: dict[TaskId, str] = {}

    for task in sorted(tasks, key=lambda t: (-t.load, t.id)):
        choice = None
        candidates = sorted(
            preference.get(task.id, []),
            key=lambda m: (state.cost_to_admit(task, m).extra_cost
                           if state.cost_to_admit(task, m) else float("inf"), m))
        for profile_id in candidates:
            if state.cost_to_admit(task, profile_id) is not None:
                choice = profile_id
                break

        if choice is None:
            choice = select_profile(task, pools[task.id], state,
                                    lambda m, admit: admit.extra_cost)
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
    """warm_start seeds the incumbent with plain greedy's answer.

    IT IS ON BY DEFAULT AND IT CONFOUNDS THE A-vs-B COMPARISON. With it on, Track B can
    never be worse than Track A and can never be infeasible where Track A was feasible —
    both hold by construction, not by merit. The subgradient step rule genuinely wants an
    incumbent upper bound, so this is the standard thing to do and the default stays; but
    any T4 statement of the form "B beats A" must be read off warm_start=False, which
    tracks/track_b_cold.py exposes as its own condition.
    """
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                strategy,
                Infeasible("empty candidate pool — registry or floors too strict",
                           task.id, "C1"),
                time.perf_counter() - started)

    eligible_for = {m: [t for t in tasks if m in pools[t.id]] for m in profiles}
    lam: dict[TaskId, float] = {t.id: 0.0 for t in tasks}

    # An incumbent is needed for the step rule. See the confound warning in the docstring.
    if warm_start:
        incumbent = track_a_greedy.allocate(tasks, pools, profiles, budget, seed=seed)
        best_result = incumbent if incumbent.feasible else None
        upper_bound = incumbent.total_cost if incumbent.feasible else None
    else:
        best_result, upper_bound = None, None

    # lambda[t] is a cost per task, so the natural scale for a step in lambda is the cost of
    # one instance. Used only by the no-incumbent step rule above.
    lambda_scale = max((p.price for p in profiles.values()), default=1.0)

    best_bound = -math.inf
    alpha = INITIAL_STEP_SCALE
    since_improvement = 0
    iterations = 0
    converged = False

    for iterations in range(1, ITERATION_CAP + 1):
        selected: dict[str, list[Task]] = {}
        subtotal = 0.0
        for profile_id, profile in profiles.items():
            value, taken, _ = _solve_profile_subproblem(
                profile, eligible_for[profile_id], lam, budget)
            selected[profile_id] = taken
            subtotal += value

        bound = sum(lam.values()) + subtotal
        if bound > best_bound:
            best_bound = bound
            since_improvement = 0
        else:
            since_improvement += 1

        repaired = _repair_to_feasible(selected, tasks, pools, profiles, budget)
        if repaired is not None:
            state, routing = repaired
            if best_result is None or state.total_cost() < best_result.total_cost:
                best_result = AllocationResult(
                    routing=routing, provisioning=state.build_provisioning(),
                    total_cost=state.total_cost(), gpus_used=state.gpus_used(),
                    strategy=strategy, feasible=True)
                upper_bound = best_result.total_cost

        # Subgradient: g[t] = 1 − (number of profiles that selected t)
        taken_count: dict[TaskId, int] = {}
        for taken in selected.values():
            for task in taken:
                taken_count[task.id] = taken_count.get(task.id, 0) + 1
        gradient = {t.id: 1 - taken_count.get(t.id, 0) for t in tasks}

        norm_sq = sum(g * g for g in gradient.values())
        if norm_sq == 0:
            converged = True        # every task selected exactly once: (C1) satisfied
            break

        # Early termination: if primal-dual gap is closed within 0.5% tolerance
        if upper_bound is not None and (upper_bound - best_bound) <= max(1e-4, 0.005 * upper_bound):
            converged = True
            break

        if since_improvement >= NON_IMPROVEMENT_PATIENCE:
            alpha /= 2.0
            since_improvement = 0
        if alpha < MIN_STEP_SCALE:
            converged = True
            break

        if upper_bound is not None:
            # Polyak's rule, aimed at a real incumbent. Unchanged.
            step = alpha * max(upper_bound - bound, 1e-9) / norm_sq
        else:
            # NO INCUMBENT. The previous code substituted `best_bound + |best_bound| + 1`
            # for the missing upper bound, which is not an upper bound on anything — it is
            # a number the same order of magnitude as the bound itself. The resulting step
            # was proportional to |L(lambda)| rather than to a primal-dual gap, so the
            # multipliers overshot, the bound stopped improving, alpha halved to its floor
            # and the method stalled at a poor dual point. That is the stall F34 measured:
            # 12 of 12 heterogeneous instances non-converged, with the bound sitting BELOW
            # the LP bound, which the dual optimum cannot do.
            #
            # With no upper bound, the textbook choice is a diminishing step on the
            # NORMALISED subgradient, which converges without needing a target. Scaled by
            # the price of one instance so the step is in the units lambda is measured in.
            step = (alpha * lambda_scale
                    / (iterations ** NO_INCUMBENT_STEP_DECAY * math.sqrt(norm_sq)))
        for task in tasks:
            lam[task.id] += step * gradient[task.id]

    elapsed = time.perf_counter() - started

    if best_result is None:
        # The dual bound is valid even though no primal was recovered (F34).
        return AllocationResult.failure(
            strategy,
            Infeasible("no feasible allocation recovered from any subgradient iteration",
                       None, "C3"),
            elapsed,
            lower_bound=best_bound if best_bound > -math.inf else None)

    result = AllocationResult(
        routing=best_result.routing,
        provisioning=best_result.provisioning,
        total_cost=best_result.total_cost,
        gpus_used=best_result.gpus_used,
        strategy=strategy,
        lower_bound=best_bound if best_bound > -math.inf else None,
        iterations=iterations,
        converged=converged,
        compute_time=elapsed,
        feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track B produced a result violating {violations}")

    return result
