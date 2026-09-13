"""
I1-I5 — asserted on every allocation result, in every test.

Spec: docs/design/System_Architecture_v2.md §5.1, §6.3.
Build step 2. Verified by: hand-built valid and violating results.
Owner: 083

    I1  every task appears exactly once in routing                    (C1)
    I2  for every m: Σ load routed to m  ≤  n[m] · thr(m)             (C2)
    I3  Σ n[m] · gpu(m)  ≤  B                                          (C3)
    I4  every routed profile is in C(t) for its task                  (floors)
    I5  n[m] ≥ 1 for every profile appearing in routing

All three tracks have relaxation or rounding steps that can silently produce violating
results. Asserting I1-I5 on every output catches that class of bug regardless of source.
"""

from __future__ import annotations

from .types import AllocationResult, ProfileSpec, Task, TaskId

# (C2) sums floats. Compare with a tolerance so accumulated representation error is not
# reported as a capacity violation — but keep it far below any realistic load.
TOL = 1e-9


def check(result: AllocationResult,
          tasks: list[Task],
          pools: dict[TaskId, list[str]],
          profiles: dict[str, ProfileSpec],
          budget: int) -> list[str]:
    """Return a list of violated invariant IDs. Empty list means valid.

    A result with feasible=False is a declared failure, not a violating allocation —
    I1-I5 do not apply to it and this returns []. Callers that want to assert a track
    succeeded should check `result.feasible` themselves; the harness records failures
    as data.
    """
    if not result.feasible:
        return []

    violations: list[str] = []
    by_id = {t.id: t for t in tasks}
    routing = result.routing
    provisioning = result.provisioning

    # I1 — every task routed exactly once. routing is a dict, so "at most once" is
    # structural; what can actually break is a missing task or a routed stranger.
    if set(routing) != set(by_id):
        violations.append("I1")

    # I2 — provisioned throughput covers routed load, per profile.
    load: dict[str, float] = {}
    for task_id, profile_id in routing.items():
        task = by_id.get(task_id)
        if task is not None:
            load[profile_id] = load.get(profile_id, 0.0) + task.load
    for profile_id, routed in load.items():
        profile = profiles.get(profile_id)
        if profile is None:
            violations.append("I2")
            break
        capacity = provisioning.get(profile_id, 0) * profile.throughput
        if routed > capacity + TOL:
            violations.append("I2")
            break

    # I3 — total GPUs within budget.
    gpus = sum(count * profiles[m].gpus
               for m, count in provisioning.items() if m in profiles)
    if gpus > budget:
        violations.append("I3")

    # I4 — every routed profile is eligible for its task.
    for task_id, profile_id in routing.items():
        if profile_id not in pools.get(task_id, []):
            violations.append("I4")
            break

    # I5 — any profile carrying a task has at least one instance.
    for profile_id in set(routing.values()):
        if provisioning.get(profile_id, 0) < 1:
            violations.append("I5")
            break

    return violations
