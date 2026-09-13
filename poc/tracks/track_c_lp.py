"""
Track C — LP relaxation + rounding.

Spec: docs/design/System_Architecture_v2.md §5.2.4.
Build step 7. Verified by: bound <= MILP optimum; result satisfies I1-I5.
Owner: 075

Solve with x[t][m] in [0,1] and n[m] >= 0 continuous, keep the LP objective as a valid
lower bound, then round the routing and repair it into feasibility.

Rounding is not incidental here. The LP returns fractional n[m]. Rounding down breaks (C2);
rounding up may break (C3); and rounding one profile up changes headroom that affects
whether another profile's rounding is feasible. It is an algorithm, not a policy switch.

O6 IS LARGELY A NON-QUESTION, AND THAT IS A MEASURED RESULT.

O6 asks for "the LP rounding policy". Two alternative policies were built to answer it —
one restricting to profiles the LP had opened (n[m] > 0), one taking the most GPU-efficient
profile among those with LP weight — and both were deleted, because on 76 instances they
produced routings byte-identical to plain argmax, every time.

The reason is structural, not a quirk of the generator. Measured over 80 LP solutions at
8 tasks / 4 profiles:

    x[t][m] integral (0 or 1)        99.5% of values
    LP solutions with fully integral x   96%   (77 of 80)
    n[m] fractional                    53.4% of values

The LP hands back an integral ROUTING almost always. It has no reason to split a task:
n[m] is continuous in the relaxation, so it can buy exactly the capacity a whole task
needs. All the fractionality — and therefore the entire integrality gap — sits in n[m],
exactly where §1.7 predicts it.

The consequence for 075: effort spent on rounding policy is close to wasted. What actually
determines Track C's cost is the REPAIR pass that runs when the LP's integral routing does
not fit once n[m] must be a whole number and (C3) binds. That is the piece worth designing.

What did help, and it is worth knowing why: realising each candidate in two task orders
(large-first and small-first) cut infeasibility from 27 of 64 solvable instances to 21, and
mean gap from 14.6% to 13.2%. That gain is entirely from the second ORDER, not from any
policy.

FAIRNESS, STATED PLAINLY BECAUSE T4 TURNS ON IT. Two realisation orders is a small
multi-start, and Track A is forbidden multi-start by the scope guard (v2 §6.5) precisely
because T4 exists to decide whether that machinery pays. Track C currently gets two
attempts and Track A gets one. That should be a decision, not an accident: set
REALISATION_ORDERS to a single entry for the strictly single-shot comparison.

The repair pass still ranks on extra_cost, per §5.2.1, and is deliberately NOT made
budget-aware — that is the M1 analogue (O2) that T4 exists to evaluate.

Track C's BOUND is unaffected by any of this and remains policy-independent. Only its cost
moves.
"""

from __future__ import annotations

import time

import pulp

from poc.core.decision_rule import select_profile
from poc.core.provisioning import ProvisioningState
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId

STRATEGY = "C"


def _marginal_cost(profile_id: str, admit) -> float:
    return admit.extra_cost


def _solve_relaxation(tasks, pools, profiles, budget):
    """Return (fractional_x, fractional_n, bound), or (None, None, None) if infeasible."""
    problem = pulp.LpProblem("TwoLevelAllocation_LP", pulp.LpMinimize)

    x = {(t.id, m): pulp.LpVariable(
            f"x_{t.id.workflow_id}_{t.id.task_name}_{m}", lowBound=0, upBound=1,
            cat="Continuous")
         for t in tasks for m in pools[t.id]}
    n = {m: pulp.LpVariable(f"n_{m}", lowBound=0, cat="Continuous") for m in profiles}

    problem += pulp.lpSum(n[m] * profiles[m].price for m in profiles), "TotalCost"

    for task in tasks:
        problem += (pulp.lpSum(x[(task.id, m)] for m in pools[task.id]) == 1,
                    f"C1_{task.id.workflow_id}_{task.id.task_name}")
    for m in profiles:
        routed = pulp.lpSum(x[(t.id, m)] * t.load for t in tasks if m in pools[t.id])
        problem += (routed <= n[m] * profiles[m].throughput, f"C2_{m}")
    problem += (pulp.lpSum(n[m] * profiles[m].gpus for m in profiles) <= budget, "C3")

    problem.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=60))
    if pulp.LpStatus[problem.status] != "Optimal":
        return None, None, None

    fractional_x = {key: (var.value() or 0.0) for key, var in x.items()}
    fractional_n = {m: (var.value() or 0.0) for m, var in n.items()}
    return fractional_x, fractional_n, pulp.value(problem.objective)


def _by_largest_weight(tasks, pools, profiles, frac_x, frac_n) -> dict[TaskId, str]:
    """Argmax fractional weight. The obvious policy, and the one O6 named first.

    Expressed as a min over (-weight, id) so the id tie-break is a plain string compare —
    ties are the common case when the LP splits a task evenly.
    """
    return {
        task.id: min(pools[task.id],
                     key=lambda m: (-frac_x.get((task.id, m), 0.0), m))
        for task in tasks
    }


# Tried in order; the cheapest feasible realisation wins.
#
# There is one policy because two others were built, measured, and deleted — see the
# module docstring. The tuple stays so adding a fourth is a one-line change, and so that
# any future addition has to justify itself against the same measurement.
ROUNDING_POLICIES = (
    ("largest-weight", _by_largest_weight),
)

# Task orders each candidate routing is realised in. Large-first is the bin-packing
# instinct; small-first sometimes fits the tail into headroom the big tasks opened.
REALISATION_ORDERS = (
    ("large-first", lambda t: (-t.load, t.id)),
    ("small-first", lambda t: (t.load, t.id)),
)


def _realise(routing, tasks, pools, profiles, budget, order_key):
    """Turn a rounded routing into a provisioning state, repairing what no longer fits.

    Returns (state, routing) or (None, blocking_task_id).
    """
    state = ProvisioningState(profiles, budget)
    realised: dict[TaskId, str] = {}

    for task in sorted(tasks, key=order_key):
        choice = routing[task.id]
        if state.cost_to_admit(task, choice) is None:
            choice = select_profile(task, pools[task.id], state, _marginal_cost)
        if choice is None:
            return None, task.id
        state.admit(task, choice)
        realised[task.id] = choice

    return state, realised


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0,
             orders=None,
             strategy: str = STRATEGY) -> AllocationResult:
    """seed is accepted for interface parity (P5); this track is deterministic.

    `orders` defaults to ONE realisation order, giving Track C the same single attempt per
    instance that plain Track A gets. That is the headline T4 comparison. tracks/track_c_multi
    runs all of REALISATION_ORDERS and is reported as its own condition, so the value of the
    extra attempt is visible as a row in the table rather than baked into Track C.
    """
    orders = REALISATION_ORDERS[:1] if orders is None else orders
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                strategy,
                Infeasible("empty candidate pool — registry or floors too strict",
                           task.id, "C1"),
                time.perf_counter() - started)

    frac_x, frac_n, bound = _solve_relaxation(tasks, pools, profiles, budget)
    if frac_x is None:
        # The LP is a relaxation: if it is infeasible, so is the integer problem.
        return AllocationResult.failure(
            strategy,
            Infeasible("LP relaxation infeasible — no allocation fits the GPU budget",
                       None, "C3"),
            time.perf_counter() - started)

    best_state, best_routing = None, None
    blocking = None

    for _, policy in ROUNDING_POLICIES:
        candidate = policy(tasks, pools, profiles, frac_x, frac_n)
        for _, order_key in orders:
            state, outcome = _realise(candidate, tasks, pools, profiles, budget, order_key)
            if state is None:
                blocking = blocking or outcome
                continue
            if best_state is None or state.total_cost() < best_state.total_cost():
                best_state, best_routing = state, outcome

    if best_state is None:
        # The LP bound survives a failed repair: the relaxation solved, so `bound` is a
        # valid lower bound on the integer optimum whatever the rounding did (F34).
        return AllocationResult.failure(
            strategy,
            Infeasible("every rounding policy failed repair — no profile admissible "
                       "within budget", blocking, "C3"),
            time.perf_counter() - started,
            lower_bound=bound)

    result = AllocationResult(
        routing=best_routing,
        provisioning=best_state.build_provisioning(),
        total_cost=best_state.total_cost(),
        gpus_used=best_state.gpus_used(),
        strategy=strategy,
        lower_bound=bound,
        compute_time=time.perf_counter() - started,
        feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        # v2 §4.1: verification failure is an internal error. Never emit a violating
        # assignment — repair returns Infeasible instead.
        raise RuntimeError(f"Track C produced a result violating {violations}")

    return result
