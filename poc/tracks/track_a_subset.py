"""
A+subset — Track A followed by multi-move subset consolidation.

Spec: Track A is §5.2.2; the subset move pass is in core/consolidation.py.
Owner: 035

This module implements the subset-move neighborhood that directly addresses T2.
On adversarial_3t2p, plain greedy is trapped at 300 because moving single tasks is
locally worsening, while moving all tasks on m1 is blocked by t3's strict reliability floor.
Evaluating k-subset relocations allows t1 and t2 to move together to m2, reaching the
true optimum (280).
"""

from __future__ import annotations

import time

from poc.core.consolidation import consolidate_subsets, evaluate
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId
from poc.tracks import track_a_greedy, track_a_m1

STRATEGY = "A+subset"


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    started = time.perf_counter()
    base = track_a_greedy.allocate(tasks, pools, profiles, budget, seed=seed)
    if not base.feasible:
        # Feasibility fallback: if plain greedy stranded tasks, try M1 lookahead
        base = track_a_m1.allocate(tasks, pools, profiles, budget, seed=seed)
        if not base.feasible:
            base.strategy = STRATEGY
            return base

    routing = consolidate_subsets(base.routing, tasks, pools, profiles, budget, max_k=2)
    outcome = evaluate(routing, tasks, profiles, budget)
    if outcome is None:
        raise RuntimeError("subset consolidation produced an over-budget routing")
    cost, gpus, provisioning = outcome

    result = AllocationResult(
        routing=routing, provisioning=provisioning,
        total_cost=cost, gpus_used=gpus,
        strategy=STRATEGY,
        lower_bound=None,
        restarts=1,
        compute_time=time.perf_counter() - started,
        feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track A+subset produced a result violating {violations}")
    return result
