"""
A+rel — plain greedy followed by one relocate pass. T2's method step 2.

Spec: PoC plan §5.3 T2. Owner: 035.

Kept separate from track_a_greedy so T2's two conditions can be compared directly, which is
what the method asks for. §6.5 defers relocate to T4; this is wired only as its own
condition, so plain greedy is unchanged and the addition can still be priced.
"""

from __future__ import annotations

import time

from poc.core.consolidation import evaluate
from poc.core.relocate import relocate
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId
from poc.tracks import track_a_greedy

STRATEGY = "A+rel"


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    started = time.perf_counter()
    base = track_a_greedy.allocate(tasks, pools, profiles, budget, seed=seed)
    if not base.feasible:
        base.strategy = STRATEGY
        return base

    routing = relocate(base.routing, tasks, pools, profiles, budget)
    cost, gpus, provisioning = evaluate(routing, tasks, profiles, budget)

    result = AllocationResult(
        routing=routing, provisioning=provisioning,
        total_cost=cost, gpus_used=gpus,
        strategy=STRATEGY, lower_bound=None, restarts=1,
        compute_time=time.perf_counter() - started, feasible=True,
    )
    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track A+rel produced a result violating {violations}")
    return result
