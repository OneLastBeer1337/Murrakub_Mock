"""
A multi-move neighbourhood: relocate every task on one profile to another, together.

Spec: not in any document. Built from a diagnosed failure (findings F17).
Owner: 035 / 075 — it applies to both Track A and Track C.

WHAT IT FIXES

Both the LP relaxation and greedy construction can leave a large profile carrying far less
load than it can hold, because both price a profile by its *rate* — cost per unit of
throughput — while an integer allocation pays for whole instances. A profile with the best
price/throughput ratio can be the worst choice if the load routed to it fills a fraction of
one instance.

The diagnosed case (F17): the LP routed 7.88 units of load to a 4-GPU profile at 401.74
because its price/throughput was 11.98, against a 2-GPU profile's 12.79. Fractionally that
is correct — 0.235 instances is cheaper than 0.506. Integrally it wastes 76% of a large
instance and costs twice the optimum.

WHY SINGLE-MOVE RELOCATE CANNOT FIX IT

Moving one task off the underused profile leaves the instance open and still paid for, so
the move saves nothing and usually costs something at the destination. Every single-move
neighbourhood therefore sees a local optimum. The improving move is to relocate *all* of a
profile's tasks at once, which closes the instance and recovers its whole price.

This is the same shape as the fixture in instances/fixtures/adversarial_3t2p.py, where the
improving move is t1 and t2 *together* and CLAUDE.md records by exhaustion that multi-start
plus single-move relocate is provably insufficient. That fixture and this failure are the
same phenomenon seen from opposite ends — one where consolidating is right, one where
de-consolidating is.

SCOPE NOTE

v2 §6.5 defers Track A's relocate/consolidate to T4. This lives in core/ and is wired into
a separate condition rather than into any track, so T4 can still price it. Nothing that
exists today changes behaviour because of this file.
"""

from __future__ import annotations

import math

from poc.formulation.types import ProfileSpec, Task, TaskId

_ROUND_DP = 9


def evaluate(routing: dict[TaskId, str],
             tasks: list[Task],
             profiles: dict[str, ProfileSpec],
             budget: int):
    """(cost, gpus, provisioning) for a routing, or None if it breaks the budget."""
    load: dict[str, float] = {}
    load_of = {t.id: t.load for t in tasks}
    for task_id, profile_id in routing.items():
        load[profile_id] = load.get(profile_id, 0.0) + load_of[task_id]

    provisioning = {m: math.ceil(round(v / profiles[m].throughput, _ROUND_DP))
                    for m, v in load.items() if v > 0}
    gpus = sum(n * profiles[m].gpus for m, n in provisioning.items())
    if gpus > budget:
        return None
    cost = sum(n * profiles[m].price for m, n in provisioning.items())
    return cost, gpus, provisioning


def consolidate(routing: dict[TaskId, str],
                tasks: list[Task],
                pools: dict[TaskId, list[str]],
                profiles: dict[str, ProfileSpec],
                budget: int,
                max_passes: int = 8) -> dict[TaskId, str]:
    """Repeatedly move all tasks on one profile to another, keeping strict improvements.

    Deterministic: profiles and destinations are tried in sorted order, and only strict
    improvements are accepted, so no cycling and no dependence on dict ordering (P10).

    Complexity: O(passes · |M|² · |T|). Trivial next to an LP solve.
    """
    routing = dict(routing)
    current = evaluate(routing, tasks, profiles, budget)
    if current is None:
        return routing
    best_cost = current[0]

    by_id = {t.id: t for t in tasks}

    for _ in range(max_passes):
        improved = False

        for source in sorted({m for m in routing.values()}):
            movers = sorted((tid for tid, m in routing.items() if m == source),
                            key=lambda tid: (by_id[tid].id.workflow_id,
                                             by_id[tid].id.task_name))
            if not movers:
                continue

            # A destination must be eligible for every task being moved.
            eligible = sorted(set.intersection(
                *(set(pools[tid]) for tid in movers)) - {source})

            for destination in eligible:
                trial = dict(routing)
                for tid in movers:
                    trial[tid] = destination

                outcome = evaluate(trial, tasks, profiles, budget)
                if outcome is not None and outcome[0] < best_cost - 1e-9:
                    routing, best_cost, improved = trial, outcome[0], True
                    break

            if improved:
                break

        if not improved:
            break

    return routing


def consolidate_subsets(routing: dict[TaskId, str],
                        tasks: list[Task],
                        pools: dict[TaskId, list[str]],
                        profiles: dict[str, ProfileSpec],
                        budget: int,
                        max_k: int = 2,
                        max_passes: int = 8) -> dict[TaskId, str]:
    """Repeatedly move all tasks, or subsets of up to max_k tasks, from one profile to another.

    Extends consolidate() to multi-move subset neighborhoods. This directly closes the
    aggregate-coupling gap diagnosed on instances/fixtures/adversarial_3t2p.py, where
    moving all tasks is blocked by an ineligible tail task, but moving a subset of tasks
    together opens an instance on an efficient profile with lower aggregate cost.

    Deterministic: candidates and destinations are explored in sorted order; strict
    improvements only (P10).
    """
    import itertools

    routing = dict(routing)
    current = evaluate(routing, tasks, profiles, budget)
    if current is None:
        return routing
    best_cost = current[0]

    by_id = {t.id: t for t in tasks}

    for _ in range(max_passes):
        improved = False

        # First, run the full-profile consolidation pass
        routing_after_all = consolidate(routing, tasks, pools, profiles, budget, max_passes=1)
        if routing_after_all != routing:
            current_after = evaluate(routing_after_all, tasks, profiles, budget)
            if current_after is not None and current_after[0] < best_cost - 1e-9:
                routing, best_cost, improved = routing_after_all, current_after[0], True
                continue

        # Next, search for subset moves of size k in [max_k, ..., 2, 1]
        for k in range(max_k, 0, -1):
            for source in sorted({m for m in routing.values()}):
                movers = sorted((tid for tid, m in routing.items() if m == source),
                                key=lambda tid: (by_id[tid].id.workflow_id,
                                                 by_id[tid].id.task_name))
                if len(movers) < k:
                    continue

                for subset in itertools.combinations(movers, k):
                    eligible = sorted(set.intersection(
                        *(set(pools[tid]) for tid in subset)) - {source})
                    if not eligible:
                        continue

                    for destination in eligible:
                        trial = dict(routing)
                        for tid in subset:
                            trial[tid] = destination

                        outcome = evaluate(trial, tasks, profiles, budget)
                        if outcome is not None and outcome[0] < best_cost - 1e-9:
                            routing, best_cost, improved = trial, outcome[0], True
                            break

                    if improved:
                        break
                if improved:
                    break
            if improved:
                break

        if not improved:
            break

    return routing

