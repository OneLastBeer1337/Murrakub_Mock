"""
STATIC — the no-optimisation baseline.

Spec: docs/design/System_Architecture_v2.md §4.7 names a "static baseline" as one of five
evaluation conditions but never says what it allocates. This is that gap filled, and the
definition below is a **[PROPOSED]** one, not a specified one.

Owner: 089

WHAT "NO OPTIMISATION" MEANS HERE. Every task independently picks the cheapest profile it
is eligible for, by price(m). Nothing else is consulted:

  * no aggregate coupling — it never asks whether the profile already has headroom, so it
    cannot notice that two tasks would share an instance
  * no budget awareness — it does not look at (C3) while choosing, only afterwards
  * no ordering, no repair, no backtracking

That is the point. This condition exists to show what the optimisation buys. If Tracks A,
B and C cannot beat "pick the cheapest eligible executor for each task", the project has a
problem that no amount of algorithm work fixes.

Because it ignores the budget while choosing, STATIC reports infeasible far more often than
the tracks do. That is not a defect of the baseline — it is the measurement.

ON THE MURAKKAB CONDITION. §4.7's five conditions are Tracks A/B/C, a static baseline, and
the exact MILP. There is no separate Murakkab condition to build: per §9's reference map,
what this project takes from Murakkab is the capacity model and the MILP baseline, and the
formulation in §1 IS Murakkab's model. So "re-run Murakkab under matched conditions"
(§4.7's own requirement) means running `tracks/exact_milp.py`. Registering a second entry
that calls the same solver would report the same number twice and imply an independent
comparison that does not exist. If the team means something narrower by "Murakkab" — their
published heuristic rather than their exact solve — that is a different condition and needs
the paper open to specify.
"""

from __future__ import annotations

import math
import time

from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId

STRATEGY = "STATIC"


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    """Cheapest eligible profile per task, independently. seed is unused (P5 parity)."""
    started = time.perf_counter()

    for task in tasks:
        if not pools.get(task.id):
            return AllocationResult.failure(
                STRATEGY,
                Infeasible("empty candidate pool — registry or floors too strict",
                           task.id, "C1"),
                time.perf_counter() - started)

    # Deliberately not ProvisioningState: that class refuses to admit past the budget, and
    # this baseline is defined by not looking. Provisioning is derived afterwards, the same
    # way — n[m] = ceil(load/thr) — so the two agree on everything except the budget check.
    routing: dict[TaskId, str] = {}
    load: dict[str, float] = {}
    for task in tasks:
        choice = min(pools[task.id], key=lambda m: (profiles[m].price, m))
        routing[task.id] = choice
        load[choice] = load.get(choice, 0.0) + task.load

    provisioning = {m: math.ceil(round(routed / profiles[m].throughput, 9))
                    for m, routed in load.items()}
    gpus_used = sum(count * profiles[m].gpus for m, count in provisioning.items())
    total_cost = sum(count * profiles[m].price for m, count in provisioning.items())
    elapsed = time.perf_counter() - started

    if gpus_used > budget:
        return AllocationResult.failure(
            STRATEGY,
            Infeasible(f"cheapest-per-task allocation needs {gpus_used} GPUs, budget is "
                       f"{budget}", None, "C3"),
            elapsed)

    result = AllocationResult(
        routing=routing, provisioning=provisioning,
        total_cost=total_cost, gpus_used=gpus_used,
        strategy=STRATEGY,
        lower_bound=None,       # no relaxation, no bound
        compute_time=elapsed, feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"STATIC produced a result violating {violations}")

    return result
