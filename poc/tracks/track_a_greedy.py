"""
Track A — plain greedy construction.

Spec: docs/design/System_Architecture_v2.md §5.2.2.
Build step 9. Verified by: satisfies I1-I5; returns 300 on adversarial_3t2p.
Owner: 035

PLAIN GREEDY ONLY. One pass, one ordering, no relocate, no consolidate, no multi-start.

That is a deliberate departure from the §5.2.2 pseudocode, which loops over
`orderings(tasks, seed)`. The scope guard (v2 §6.5, CLAUDE.md) is explicit that multi-start
is one of the things T4 decides the value of, so building it now would prejudge the test
this track exists to feed. `restarts` is therefore reported as 1, not None — the harness
should record that this was a single-pass run rather than leaving it ambiguous.

The ordering is decreasing load, ties broken on task id. Every greedy needs some order and
there is no neutral choice; largest-first is the standard bin-packing instinct, on the
reasoning that big tasks are the ones that force new instances and should be placed while
the budget still has room. It is a default, not a finding. `seed` is accepted for interface
parity (P5) and deliberately unused — with no multi-start there is nothing to randomise,
and a seeded shuffle here would quietly become multi-start-of-one.

KNOWN WEAKNESS, BY CONSTRUCTION. cost_to_admit is myopic: it prices a task against the
*current* provisioning state, so early tasks may open instances that later tasks would have
made unnecessary. On adversarial_3t2p this costs 300 against an optimum of 280, and the
fixture records that neither multi-start (all six orderings return 300) nor single-move
relocate (moving t1 alone costs +180 to save 100) recovers it. The improving move is two
tasks together. That is the T2 answer already in hand — it argues for a multi-move
neighbourhood, but T4 decides whether Track A earns that machinery at all.

Complexity: O(|T| * max|C(t)|).
"""

from __future__ import annotations

import time

from poc.core.decision_rule import select_profile
from poc.core.provisioning import ProvisioningState
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId

STRATEGY = "A"


def _marginal_cost(profile_id: str, admit) -> float:
    """Track A's cost_adjust: marginal provisioning cost only (§5.2.1)."""
    return admit.extra_cost


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                STRATEGY,
                Infeasible("empty candidate pool — registry or floors too strict",
                           task.id, "C1"),
                time.perf_counter() - started)

    state = ProvisioningState(profiles, budget)
    routing: dict[TaskId, str] = {}

    for task in sorted(tasks, key=lambda t: (-t.load, t.id)):
        choice = select_profile(task, pools[task.id], state, _marginal_cost)
        if choice is None:
            # Complete or nothing (P9). A partial assignment is never valid output, and
            # plain greedy has no backtracking to fall back on — that is the point of T4's
            # third outcome, "greedy frequently infeasible".
            return AllocationResult.failure(
                STRATEGY,
                Infeasible("no profile admissible within budget", task.id, "C3"),
                time.perf_counter() - started)
        state.admit(task, choice)
        routing[task.id] = choice

    result = AllocationResult(
        routing=routing,
        provisioning=state.build_provisioning(),
        total_cost=state.total_cost(),
        gpus_used=state.gpus_used(),
        strategy=STRATEGY,
        lower_bound=None,           # Track A produces no bound — that is T4's whole question
        restarts=1,
        compute_time=time.perf_counter() - started,
        feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track A produced a result violating {violations}")

    return result
