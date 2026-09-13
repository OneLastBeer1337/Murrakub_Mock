"""
Synthetic instance generator.

Spec: docs/design/System_Architecture_v2.md §6.4.
Build step 3. Verified by: instances well-formed; every C(t) non-empty.
Owner: 083 (deliverable D2, due 8 Sep)

    generate(n_tasks, n_profiles, budget_tightness, seed) -> ProblemInstance

budget_tightness ∈ (0, 1] is the PRIMARY EXPERIMENTAL AXIS (T3). The comparison has no
signal where the budget is loose, so this is the knob the sweep turns.

NAMING. §6.4 calls the return value an "Instance", but §5.1 already uses Instance for a
provisioned count {profile_id, count}. Two different things, one word. The problem is a
ProblemInstance here; types.Instance keeps its §5.1 meaning.

DEVIATION FROM §6.4 — DELIBERATE, AND IT NEEDS 083's SIGN-OFF.

§6.4 defines the budget as "a fraction of the GPUs needed by a naive one-instance-per-
profile solution", i.e. Σ_m gpu(m). That was implemented literally first, and measured:
it does not work. The anchor does not depend on the tasks at all, so a batch of 8 tasks
routinely needs more instances than one-per-profile, and the budget lands below
feasibility almost everywhere. On 25 seeds at 8 tasks / 4 profiles, the exact solver found
NO feasible allocation at tightness 0.3 or 0.4, and only 16 of 25 were solvable even at
1.0 — the loosest the parameter allows. T3's sweep had no room to move.

The anchor here is instead a concrete feasible reference allocation (see _reference_gpus),
which gives the property the sweep actually needs:

    budget_tightness = 1.0  ->  always feasible, by construction
    decreasing tightness    ->  monotonically tighter, into infeasibility

`budget_tightness` keeps its §6.4 meaning — a fraction of an anchor — so the sweep reads
the same way. Only the anchor changed. Note the parameter name still runs backwards
against its value: 1.0 is the LOOSEST budget, not the tightest. That inversion is §6.4's
and is left alone rather than silently redefined.

reference_gpus is exposed on the result so T3 can sweep absolute B and ignore the anchor
entirely, which is the more defensible thing to report.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from poc.formulation.types import ProfileSpec, Task, TaskId

MAX_REGENERATION_ATTEMPTS = 100


@dataclass(frozen=True)
class ProblemInstance:
    tasks: list[Task]
    pools: dict[TaskId, list[str]]
    profiles: dict[str, ProfileSpec]
    budget: int
    reference_gpus: int
    seed: int
    budget_tightness: float

    def unpack(self):
        """(tasks, pools, profiles, budget) — the argument order every track takes."""
        return self.tasks, self.pools, self.profiles, self.budget


def _draw_profiles(rng, n_profiles: int) -> dict[str, ProfileSpec]:
    profiles = {}
    for i in range(n_profiles):
        pid = f"m{i + 1}"
        gpus = int(rng.integers(1, 5))
        # Throughput and price both scale with GPUs, with noise, so that no profile is
        # dominated outright and the cheap-small vs expensive-large tradeoff is real.
        throughput = float(np.round(gpus * rng.uniform(8.0, 14.0), 2))
        price = float(np.round(gpus * rng.uniform(80.0, 120.0), 2))
        profiles[pid] = ProfileSpec(
            id=pid,
            declared_type="generic",
            throughput=throughput,
            gpus=gpus,
            price=price,
            reliability=float(np.round(rng.uniform(0.90, 0.999), 3)),
            latency=float(np.round(rng.uniform(20.0, 150.0), 1)),
        )
    return profiles


def _draw_tasks(rng, n_tasks: int, profiles: dict[str, ProfileSpec]) -> list[Task]:
    reliabilities = sorted(p.reliability for p in profiles.values())
    latencies = sorted(p.latency for p in profiles.values())
    tasks = []
    for i in range(n_tasks):
        # Floors are drawn from the profiles' own value range rather than an absolute
        # scale, so a generated instance cannot ask for reliability no profile offers.
        # This makes empty pools rare; the regeneration loop below is the guarantee.
        rel_floor = float(rng.choice(reliabilities))
        lat_ceil = float(rng.choice(latencies))
        tasks.append(Task(
            id=TaskId("wf" + str(int(rng.integers(1, 4))), f"t{i + 1}"),
            task_type="generic",
            load=float(np.round(rng.uniform(1.0, 20.0), 2)),
            rel_floor=rel_floor,
            lat_ceil=lat_ceil,
        ))
    return tasks


def _build_pools(tasks, profiles) -> dict[TaskId, list[str]]:
    """C(t) = { m : rel(m) ≥ R_min(t) and lat(t,m) ≤ L_max(t) } — v2 §1.6."""
    return {
        task.id: sorted(m.id for m in profiles.values()
                        if m.reliability >= task.rel_floor and m.latency <= task.lat_ceil)
        for task in tasks
    }


def _reference_gpus(tasks, pools, profiles) -> int:
    """GPUs used by a concrete, always-achievable reference allocation.

    Every task goes to its most GPU-efficient eligible profile — the one with the lowest
    gpu(m)/thr(m), i.e. the fewest GPUs per unit of throughput bought — and instance
    counts follow from the routed load. This is a real feasible allocation, not a bound,
    so a budget equal to it always admits at least one solution.

    It is not the GPU-minimal allocation: choosing per task ignores the aggregate ceiling,
    so consolidating two tasks onto one shared instance can beat it. That is fine and in
    fact wanted — the anchor should sit at "obviously affordable", leaving the interesting
    structure below it.
    """
    load: dict[str, float] = {}
    for task in tasks:
        cheapest = min(pools[task.id],
                       key=lambda m: (profiles[m].gpus / profiles[m].throughput, m))
        load[cheapest] = load.get(cheapest, 0.0) + task.load

    return sum(math.ceil(round(routed / profiles[m].throughput, 9)) * profiles[m].gpus
               for m, routed in load.items())


def generate(n_tasks: int, n_profiles: int, budget_tightness: float,
             seed: int) -> ProblemInstance:
    # Range extended past 1.0 deliberately. F15: the reference allocation is a CLIFF, not a
    # neutral upper bound -- every track goes from 0 of 5 feasible at 1.0x to 5 of 5 at
    # 1.25x. A sweep that stops at the cliff can only ever measure the cliff. The name is
    # left as budget_tightness for continuity, though it is really a ratio and larger means
    # looser.
    if not 0.0 < budget_tightness <= 3.0:
        raise ValueError(f"budget_tightness must be in (0, 3], got {budget_tightness}")
    if n_tasks < 1 or n_profiles < 1:
        raise ValueError("n_tasks and n_profiles must be >= 1")

    for attempt in range(MAX_REGENERATION_ATTEMPTS):
        # Derive a distinct stream per attempt so a discarded instance is not simply
        # redrawn identically, while the whole sequence stays a function of `seed` (P10).
        rng = np.random.default_rng([seed, attempt])
        profiles = _draw_profiles(rng, n_profiles)
        tasks = _draw_tasks(rng, n_tasks, profiles)
        pools = _build_pools(tasks, profiles)

        if any(not pool for pool in pools.values()):
            continue        # discard and regenerate — §6.4

        reference_gpus = _reference_gpus(tasks, pools, profiles)
        budget = max(1, int(round(budget_tightness * reference_gpus)))
        return ProblemInstance(tasks=tasks, pools=pools, profiles=profiles,
                               budget=budget, reference_gpus=reference_gpus, seed=seed,
                               budget_tightness=budget_tightness)

    raise RuntimeError(
        f"could not generate an instance with all pools non-empty in "
        f"{MAX_REGENERATION_ATTEMPTS} attempts (n_tasks={n_tasks}, "
        f"n_profiles={n_profiles}, seed={seed})")
