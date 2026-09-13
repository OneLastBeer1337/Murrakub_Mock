"""
Executor Registry (§4.3) and Eligibility Resolver (§4.2).

Outside PoC scope — see prototype/README.md. Owner: 083 (registry), 035 (resolver).

WHY THESE ARE WORTH BUILDING EARLY

§4.2 makes a specific design claim that has never been exercised by any code:

    "Exact match only — no fuzzy or semantic matching, so registry gaps surface as
     failures rather than silent quality loss."

In the PoC, `C(t)` is handed over pre-built by the instance generator, so nothing has ever
built a pool from a registry, and nothing has ever tested what happens when the registry is
missing a task type. That is the claim these forty lines exist to make testable.

The resolver is deliberately unforgiving in two separate ways, and they fail differently:

  * **Unknown task type** — the registry has no entry at all. This is a registry gap and it
    raises, because a silent empty pool would be indistinguishable from "declared but every
    candidate filtered out", and those need different fixes.
  * **Known type, everything filtered** — the registry has entries but the floors exclude
    all of them. This returns an empty pool, which the Optimizer reports as Infeasible on
    C1 naming the task (§4.1).

Conflating those two is exactly the "silent quality loss" §4.2 is guarding against.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from poc.formulation.types import ProfileSpec, Task, TaskId


class UnknownTaskType(Exception):
    """The registry declares no profile for a task type. A registry gap, not a floor."""


@dataclass
class ExecutorRegistry:
    """Curated catalogue of profiles. Read-only at runtime (§4.3), manually maintained.

    No auto-discovery: a developer registers each executor by hand under a task type.
    """

    _by_type: dict[str, list[ProfileSpec]] = field(default_factory=dict)

    def register(self, profile: ProfileSpec) -> None:
        self._by_type.setdefault(profile.declared_type, []).append(profile)

    def declared_types(self) -> set[str]:
        return set(self._by_type)

    def profiles_for(self, task_type: str) -> list[ProfileSpec]:
        """Exact match only. Raises rather than returning [] for an unknown type."""
        if task_type not in self._by_type:
            raise UnknownTaskType(
                f"no profile registered for task type {task_type!r}; "
                f"registered types are {sorted(self._by_type)}")
        return list(self._by_type[task_type])

    def all_profiles(self) -> dict[str, ProfileSpec]:
        return {p.id: p for group in self._by_type.values() for p in group}


def resolve(tasks: list[Task], registry: ExecutorRegistry,
            reliability_of=None) -> dict[TaskId, list[str]]:
    """Build C(t) for every task: exact type match, then floor filtering (§1.6).

        C(t) = { m : declared_type(m) == taskType(t)
                     and rel(m) >= R_min(t) and lat(t,m) <= L_max(t) }

    Raises UnknownTaskType if any task's type is not in the registry. Returns an empty pool
    for a task whose type is registered but whose floors exclude everything — the Optimizer
    turns that into Infeasible(C1) naming the task.
    """
    pools: dict[TaskId, list[str]] = {}
    for task in tasks:
        candidates = registry.profiles_for(task.task_type)      # may raise
        def reliability(profile):
            # Default: the point estimate, which is what §1.6 specifies. Passing an
            # upper-bound function instead excludes a profile only when the evidence is
            # strong enough to be confident it is below floor (F23/F25).
            return profile.reliability if reliability_of is None else reliability_of(profile.id)

        pools[task.id] = sorted(
            p.id for p in candidates
            if reliability(p) >= task.rel_floor and p.latency <= task.lat_ceil)
    return pools


def unservable(pools: dict[TaskId, list[str]]) -> list[TaskId]:
    """Tasks whose type is registered but whose floors exclude every candidate."""
    return [task_id for task_id, pool in pools.items() if not pool]
