"""
C2 — Track C given every realisation order, reported as its own condition.

Spec: docs/design/System_Architecture_v2.md §5.2.4; findings F6.
Owner: 075

This exists so that a fairness problem in T4 is a row in the table instead of a footnote.

Track C's rounding can be realised in more than one task order, and trying both measurably
helps: infeasible fell from 27 of 64 solvable instances to 21, and mean gap from 14.6% to
13.2%. But plain Track A is allowed exactly one attempt — the scope guard (v2 §6.5) denies
it multi-start precisely because T4 exists to decide whether that machinery pays. Letting
Track C quietly keep two attempts would answer part of T4 by accident, in Track C's favour.

So:

    C     one realisation order   — the headline comparison, like-for-like with A
    C2    every realisation order — the same track with the extra attempt

The difference between those two rows IS the value of the extra attempt, measured rather
than assumed. If C2 beats C by a lot, that is an argument for giving Track A multi-start
too and re-reading T4; if it barely moves, the fairness worry was noise.
"""

from __future__ import annotations

from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId
from poc.tracks import track_c_lp

STRATEGY = "C2"


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    return track_c_lp.allocate(tasks, pools, profiles, budget, seed=seed,
                               orders=track_c_lp.REALISATION_ORDERS,
                               strategy=STRATEGY)
