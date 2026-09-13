"""
B-cold — Track B with no warm start, so the A-vs-B comparison is independent.

Spec: docs/design/System_Architecture_v2.md §5.2.3. Owner: 075

Track B's subgradient step rule wants an incumbent upper bound, and plain greedy is the
cheapest honest source of one. But seeding with greedy's answer means Track B can never be
worse than Track A, and can never be infeasible where Track A was feasible — both by
construction rather than by merit. Any T4 claim that B beats A, read off the warm-started
condition, would be partly circular.

This condition runs the identical relaxation with warm_start=False. The step rule falls
back to a bound-derived reference until the first feasible primal is recovered.

    B        warm-started  — the sensible default, and what a real implementation would ship
    B-cold   independent   — what T4 should be read off

The gap between the two rows is how much of Track B's result is really Track A's.
"""

from __future__ import annotations

from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId
from poc.tracks import track_b_lagr

STRATEGY = "B-cold"


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    return track_b_lagr.allocate(tasks, pools, profiles, budget, seed=seed,
                                 warm_start=False, strategy=STRATEGY)
