"""
C+cons — Track C followed by the multi-move consolidation pass.

Spec: Track C is §5.2.4; the pass is core/consolidation.py, built from findings F17.
Owner: 075

Kept separate from track_c_lp for the same reason A+M1 is kept separate from plain greedy:
T4 has to be able to price the addition. Folding it in would answer by assumption whether
the extra machinery pays.

This is also the concrete answer to what F6 left open. F6 found the LP returns an integral
routing 96% of the time and concluded that O6's "rounding policy" is the wrong question and
the repair pass is the right one. This is a repair pass, targeting a diagnosed failure
rather than a guess: the LP prices profiles by rate and cannot see that a large profile's
integer instance will sit mostly empty.
"""

from __future__ import annotations

import time

from poc.core.consolidation import consolidate, evaluate
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId
from poc.tracks import track_c_lp

STRATEGY = "C+cons"


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    started = time.perf_counter()
    base = track_c_lp.allocate(tasks, pools, profiles, budget, seed=seed)
    if not base.feasible:
        base.strategy = STRATEGY
        return base

    routing = consolidate(base.routing, tasks, pools, profiles, budget)
    outcome = evaluate(routing, tasks, profiles, budget)
    if outcome is None:            # cannot happen: consolidate only keeps feasible moves
        raise RuntimeError("consolidation produced an over-budget routing")
    cost, gpus, provisioning = outcome

    result = AllocationResult(
        routing=routing, provisioning=provisioning,
        total_cost=cost, gpus_used=gpus,
        strategy=STRATEGY,
        lower_bound=base.lower_bound,      # the LP bound is unaffected by the repair
        compute_time=time.perf_counter() - started,
        feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track C+cons produced a result violating {violations}")
    return result
