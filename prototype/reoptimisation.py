"""
J9 — re-optimisation, global and scoped (§3.3).

Outside PoC scope — see prototype/README.md. Owner: 077.

THE QUESTION THIS EXISTS TO ANSWER (O9)

§3.3 specifies J9 as re-invoking J3 "for affected workflows only", and then immediately
doubts its own specification:

    "[OPEN — scoping of re-optimisation.] Under (C2), re-routing one workflow changes load
     on shared profiles, which changes instance counts, which affects every other workflow
     using those profiles. Scoped re-optimisation may not be well-defined."

It is deferred to Semester 2. But the doubt is precise enough to test, and if scoped
re-optimisation is not well-defined then a component someone would otherwise spend a
semester building does not work — which is exactly the class of discovery §5.0 argues for
making early.

WHAT "SCOPED" HAS TO MEAN

Re-optimising a subset of workflows requires freezing the rest. The tasks that stay put keep
consuming capacity on their profiles, so the scoped run must be given that as a starting
condition rather than an empty state. That is `frozen_load` below.

The subtlety, and the reason for the doubt: instance counts are a **ceiling** over aggregate
load. A frozen workflow contributes load but the ceiling is shared, so headroom that the
frozen tasks paid for is available to the re-optimised ones — and whether the frozen tasks'
own instances are still the right count depends on what the re-optimised tasks do. The two
sets cannot be separated cleanly. This module makes that concrete instead of arguing it.

Both strategies produce a complete allocation, so they can be compared like for like.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from poc.formulation.types import AllocationResult, ProfileSpec, Task, TaskId

_ROUND_DP = 9


@dataclass(frozen=True)
class ReoptOutcome:
    strategy: str                   # "global" | "scoped"
    routing: dict[TaskId, str]
    total_cost: float
    gpus_used: int
    provisioning: dict[str, int]
    feasible: bool
    reason: str = ""


def _evaluate(routing, tasks, profiles, budget):
    load: dict[str, float] = {}
    load_of = {t.id: t.load for t in tasks}
    for task_id, profile_id in routing.items():
        load[profile_id] = load.get(profile_id, 0.0) + load_of[task_id]
    provisioning = {m: math.ceil(round(v / profiles[m].throughput, _ROUND_DP))
                    for m, v in load.items() if v > 0}
    gpus = sum(n * profiles[m].gpus for m, n in provisioning.items())
    cost = sum(n * profiles[m].price for m, n in provisioning.items())
    return cost, gpus, provisioning, gpus <= budget


def reoptimise_global(allocate, tasks, pools, profiles, budget,
                      candidate: AllocationResult | None = None) -> ReoptOutcome:
    """Re-run J3 over the whole batch. The baseline, and always well-defined."""
    result = candidate if candidate is not None else allocate(tasks, pools, profiles, budget)
    if not result.feasible:
        return ReoptOutcome("global", {}, 0.0, 0, {}, False,
                            "no feasible allocation over the full batch")
    return ReoptOutcome("global", result.routing, result.total_cost, result.gpus_used,
                        result.provisioning, True)


def reoptimise_scoped(allocate, tasks, pools, profiles, budget,
                      affected_workflows: set[str],
                      current_routing: dict[TaskId, str]) -> ReoptOutcome:
    """Re-run J3 for affected workflows only, freezing the rest — §3.3 as written.

    The frozen tasks keep their profiles. The re-optimised tasks are allocated against
    whatever budget the frozen ones leave, which is where the definition strains: the
    frozen tasks' instance counts are a ceiling over their own load, and that ceiling may
    have headroom the re-optimised tasks could use — but a scoped run that hands them a
    reduced budget cannot see it, and one that hands them the full budget double-counts.

    Implemented the conservative way: frozen instances are paid for and their GPUs are
    deducted. That is the reading under which "affected workflows only" is a real
    restriction rather than a relabelled global run.
    """
    frozen = [t for t in tasks if t.id.workflow_id not in affected_workflows]
    movable = [t for t in tasks if t.id.workflow_id in affected_workflows]

    if not movable:
        cost, gpus, prov, ok = _evaluate(current_routing, tasks, profiles, budget)
        return ReoptOutcome("scoped", dict(current_routing), cost, gpus, prov, ok,
                            "no affected workflows; nothing to re-optimise")

    frozen_routing = {t.id: current_routing[t.id] for t in frozen}
    frozen_cost, frozen_gpus, frozen_prov, _ = _evaluate(
        frozen_routing, frozen, profiles, budget) if frozen else (0.0, 0, {}, True)

    remaining_budget = budget - frozen_gpus
    if remaining_budget < 0:
        return ReoptOutcome("scoped", {}, 0.0, 0, {}, False,
                            "frozen workflows alone exceed the budget")

    sub = allocate(movable, {t.id: pools[t.id] for t in movable},
                   profiles, remaining_budget)
    if not sub.feasible:
        return ReoptOutcome(
            "scoped", {}, 0.0, 0, {}, False,
            f"affected workflows infeasible within the {remaining_budget} GPUs left after "
            f"freezing the rest")

    combined = {**frozen_routing, **sub.routing}
    cost, gpus, prov, ok = _evaluate(combined, tasks, profiles, budget)
    return ReoptOutcome("scoped", combined, cost, gpus, prov, ok,
                        f"froze {len(frozen)} tasks, re-optimised {len(movable)}")


def compare(allocate, tasks, pools, profiles, budget,
            affected_workflows: set[str], current_routing: dict[TaskId, str]):
    """Run both and return (global, scoped). The comparison IS the O9 experiment."""
    return (reoptimise_global(allocate, tasks, pools, profiles, budget),
            reoptimise_scoped(allocate, tasks, pools, profiles, budget,
                              affected_workflows, current_routing))
