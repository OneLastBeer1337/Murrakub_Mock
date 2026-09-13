"""
Single-move relocate: move ONE task to a different profile, keep strict improvements.

Spec: PoC plan §5.3, T2's method step 2 — "Greedy + one relocate pass".
Owner: 035.

WHY THIS EXISTS SEPARATELY FROM core/consolidation.py

They are different neighbourhoods and they fail on different instances:

    relocate      move one task                  -> this file
    consolidate   move ALL tasks off a profile   -> core/consolidation.py

T2's method explicitly calls for the single-move version. Until now the claim that it cannot
rescue greedy on the adversarial fixture rested on the enumeration recorded in CLAUDE.md
rather than on running it. This makes it measurable.

The expected result is that it does NOT help on the fixture, and the reason is arithmetic:
moving t1 alone to m2 costs a whole 180 instance and saves only 100, so no single move is an
improvement even though moving t1 AND t2 together is. A neighbourhood that considers one
task at a time cannot see that move.
"""

from __future__ import annotations

from poc.core.consolidation import evaluate
from poc.formulation.types import ProfileSpec, Task, TaskId


def relocate(routing: dict[TaskId, str],
             tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             max_passes: int = 8) -> dict[TaskId, str]:
    """Repeatedly move a single task to a different eligible profile, keeping improvements.

    Deterministic: tasks and destinations are tried in sorted order and only strict
    improvements are accepted, so there is no cycling (P10).
    """
    routing = dict(routing)
    current = evaluate(routing, tasks, profiles, budget)
    if current is None:
        return routing
    best_cost = current[0]

    for _ in range(max_passes):
        improved = False
        for task in sorted(tasks, key=lambda t: (t.id.workflow_id, t.id.task_name)):
            here = routing[task.id]
            for destination in sorted(set(pools[task.id]) - {here}):
                trial = dict(routing)
                trial[task.id] = destination
                outcome = evaluate(trial, tasks, profiles, budget)
                if outcome is not None and outcome[0] < best_cost - 1e-9:
                    routing, best_cost, improved = trial, outcome[0], True
                    break
            if improved:
                break
        if not improved:
            break

    return routing
