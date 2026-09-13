"""
Track A + M1 — greedy construction with feasibility lookahead.

Spec: docs/design/System_Architecture_v2.md §5.2.2; Paper P3 (Cheng & Nguyen, 2026, arXiv:2604.07472).
Owner: 035

WHY THIS IS A SEPARATE MODULE AND NOT A CHANGE TO track_a_greedy.

T4 asks whether Track A's machinery earns its complexity. Folding the lookahead into
`track_a_greedy` would answer that question by assumption — the plain track would cease to
exist and there would be nothing to price the addition against. So plain greedy stays
exactly as it was, this is a fourth condition, and the harness reports both. The cost of
the machinery is then literally the difference between two rows in the table.

THE M1 MECHANISM AND PRECEDENT (RECONCILED AGAINST CHENG & NGUYEN 2026).

Reconciles against Paper P3 (Cheng & Nguyen, 2026, arXiv:2604.07472, "Scalable Joint Resource
Allocation for SLO-Constrained LLM Inference in Heterogeneous GPU Clouds") and concept
C_FEASFIRST. In Cheng & Nguyen §3.3, greedy decisions enforce feasibility of remaining tasks
under residual capacity before optimizing marginal cost.

The observed failure (findings F3): plain greedy ranks on `extra_cost` — price — and never
looks at `extra_gpus`. It buys cheap, GPU-hungry profiles early, exhausts the budget, and
strands later tasks with no admissible profile at all. It fails on 27 of 64 solvable
instances, including 7 at the loosest budget where a solution is guaranteed to exist.

The fix here is a one-step feasibility lookahead. For each task, walk its candidates in
ascending marginal cost; tentatively admit; then check that **every remaining unassigned
task still has at least one admissible profile**. If any is stranded, undo and try the next
candidate. Take the first choice that leaves the rest of the batch placeable, falling back
to plain cheapest if none does.

Two properties worth stating:

  * **No tuning parameter.** No scarcity multiplier, no budget-pressure threshold, nothing
    to fit to the generator. It is a feasibility test, not a re-weighting, which makes it
    much harder to accidentally tune against the instances it is measured on.
  * **It is not a bound, an optimiser, or a repair.** It never revisits a placed task. A
    task it strands anyway is still a hard failure — this narrows the failure mode, it does
    not remove it.

`snapshot`/`restore` exist on ProvisioningState for exactly this (§4.4).

Complexity: O(|T|² · max|C(t)|²) — quadratic in tasks where plain greedy is linear. At PoC
sizes that is nothing; at scale it is the cost T4 should be weighing.
"""

from __future__ import annotations

import time

from poc.core.provisioning import ProvisioningState
from poc.formulation import invariants
from poc.formulation.types import AllocationResult, Infeasible, ProfileSpec, Task, TaskId

STRATEGY = "A+M1"


def _leaves_everyone_placeable(state: ProvisioningState, remaining, pools) -> bool:
    """Does every not-yet-assigned task still have at least one admissible profile?

    One step, not a full feasibility proof: it checks each remaining task in isolation
    against the current state, so it cannot see that two of them need the same last GPU.
    A cheap necessary condition, not a sufficient one.
    """
    return all(
        any(state.cost_to_admit(task, m) is not None for m in pools[task.id])
        for task in remaining
    )


def allocate(tasks: list[Task],
             pools: dict[TaskId, list[str]],
             profiles: dict[str, ProfileSpec],
             budget: int,
             seed: int = 0) -> AllocationResult:
    """Same ordering and same ranking as plain greedy — only the lookahead is added."""
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
    order = sorted(tasks, key=lambda t: (-t.load, t.id))

    for index, task in enumerate(order):
        remaining = order[index + 1:]

        # Candidates in the order plain greedy would consider them: cheapest marginal
        # cost first, ties on profile id, exactly matching core.decision_rule.
        admissible = []
        for profile_id in pools[task.id]:
            admit = state.cost_to_admit(task, profile_id)
            if admit is not None:
                admissible.append((admit.extra_cost, profile_id))
        admissible.sort()

        if not admissible:
            return AllocationResult.failure(
                STRATEGY,
                Infeasible("no profile admissible within budget", task.id, "C3"),
                time.perf_counter() - started)

        chosen = None
        snapshot = state.snapshot()
        for _, profile_id in admissible:
            state.admit(task, profile_id)
            if _leaves_everyone_placeable(state, remaining, pools):
                chosen = profile_id
                break
            state.restore(snapshot)

        if chosen is None:
            # Nothing keeps the whole batch placeable. Take the cheapest and let the
            # failure surface honestly rather than pretending the lookahead helped.
            chosen = admissible[0][1]
            state.admit(task, chosen)

        routing[task.id] = chosen

    result = AllocationResult(
        routing=routing,
        provisioning=state.build_provisioning(),
        total_cost=state.total_cost(),
        gpus_used=state.gpus_used(),
        strategy=STRATEGY,
        lower_bound=None,       # still no bound — the lookahead does not produce one
        restarts=1,
        compute_time=time.perf_counter() - started,
        feasible=True,
    )

    violations = invariants.check(result, tasks, pools, profiles, budget)
    if violations:
        raise RuntimeError(f"Track A+M1 produced a result violating {violations}")

    return result
