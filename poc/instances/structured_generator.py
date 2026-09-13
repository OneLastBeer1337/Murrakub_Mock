"""
A second instance generator, structurally different from the first on purpose.

Spec: not in any document. This exists to answer a methodological objection recorded
against the findings, not to satisfy a requirement.
Owner: 083

WHY THIS EXISTS

Every finding in docs/evidence/poc_findings.md traces to one generator whose distributions, budget
anchor, tracks and metrics were all written by the same hand. That is the setup in which
unconscious selection is hardest to see, and no amount of re-slicing the same data touches
it. The only real check is instances with different structure.

So this generator is built to disagree with `generator.py` wherever it plausibly can, while
staying defensible as a model of GPU serving. If a finding survives both, it is a finding
about the problem. If it holds on one and not the other, it was a finding about the
generator — which is worth knowing before any of it reaches Chapter 3.

HOW IT DIFFERS, AND WHY EACH CHOICE IS PLAUSIBLE

| | generator.py | this |
|---|---|---|
| GPU counts | uniform 1-4 | tiers {1, 2, 4, 8} |
| throughput vs GPUs | linear, gpus x U(8,14) | **sublinear**, gpus^0.75 |
| price vs GPUs | linear, gpus x U(80,120) | linear (you pay per GPU) |
| loads | uniform U(1,20) | **lognormal** — heavy-tailed |
| floors | sampled from profile values | correlated: a minority of tasks are strict |

The consequential change is **sublinear throughput against linear price**. Tensor and
pipeline parallelism carry real communication overhead, so an 8-GPU instance does not serve
8x the traffic of a 1-GPU one — but it costs 8x. That inverts the incentive in the first
generator, where throughput and price both scaled linearly with GPUs and large instances
were roughly cost-neutral. Here, **large profiles are actively bad value per GPU**, and the
optimiser should prefer many small instances except where a single task is too large to
fit on one.

Heavy-tailed loads then supply exactly that exception: a few tasks are far larger than the
rest and force a large profile no matter how poor its value. That is a bin-packing
structure the uniform generator never produces.

Correlated floors mean strictness clusters on a minority of tasks rather than being
sprinkled evenly, so pools vary in size much more sharply.

WHAT IS DELIBERATELY KEPT IDENTICAL

The budget anchor (`_reference_gpus` from generator.py) and the (C1)-non-empty guarantee.
Changing the anchor too would confound a generator comparison with an anchor comparison,
and the anchor is already known to matter (findings F2, and F3's rate caveat).
"""

from __future__ import annotations

import math

import numpy as np

from poc.formulation.types import ProfileSpec, Task, TaskId
from poc.instances.generator import (MAX_REGENERATION_ATTEMPTS, ProblemInstance,
                                     _build_pools, _reference_gpus)

GPU_TIERS = (1, 2, 4, 8)
PARALLELISM_EXPONENT = 0.75     # throughput ~ gpus^0.75; below 1 means overhead


def _draw_profiles(rng, n_profiles: int) -> dict[str, ProfileSpec]:
    profiles = {}
    for i in range(n_profiles):
        gpus = int(GPU_TIERS[rng.integers(0, len(GPU_TIERS))])
        # Sublinear throughput against linear price: big instances cost proportionally
        # more and deliver proportionally less. This is the inversion.
        throughput = float(np.round((gpus ** PARALLELISM_EXPONENT) * rng.uniform(9.0, 12.0), 2))
        price = float(np.round(gpus * rng.uniform(95.0, 105.0), 2))
        profiles[f"m{i + 1}"] = ProfileSpec(
            id=f"m{i + 1}",
            declared_type="generic",
            throughput=throughput,
            gpus=gpus,
            price=price,
            # Larger tiers are slightly more reliable and slower — a mild, plausible
            # correlation rather than the first generator's independent draws.
            reliability=float(np.round(min(0.999, 0.93 + 0.02 * math.log2(gpus)
                                           + rng.uniform(-0.01, 0.02)), 3)),
            latency=float(np.round(30.0 + 12.0 * math.log2(gpus) + rng.uniform(0, 40), 1)),
        )
    return profiles


def _draw_tasks(rng, n_tasks: int, profiles: dict[str, ProfileSpec]) -> list[Task]:
    reliabilities = sorted(p.reliability for p in profiles.values())
    latencies = sorted(p.latency for p in profiles.values())
    tasks = []
    for i in range(n_tasks):
        # Lognormal: most tasks small, a few very large. The large ones are what force a
        # big profile to be opened at all.
        load = float(np.round(np.clip(rng.lognormal(mean=1.4, sigma=0.9), 0.5, 60.0), 2))

        # Strictness clusters: ~30% of tasks demand an upper-tier reliability, the rest
        # accept the loosest. Pools therefore vary sharply in size.
        #
        # Strictness is applied on ONE axis at a time, never both. Demanding top
        # reliability AND tightest latency together is almost always unsatisfiable here,
        # because the most reliable profiles are the large ones and the large ones are the
        # slow ones. Instances built that way were being silently discarded by the
        # regeneration loop, so the generator produced no strict tasks at all — the
        # opposite of the variety this file exists to create.
        roll = rng.random()
        if roll < 0.30:
            rel_floor = float(reliabilities[max(0, len(reliabilities) - 2)])
            lat_ceil = float(latencies[-1])
        elif roll < 0.45:
            rel_floor = float(reliabilities[0])
            lat_ceil = float(latencies[max(0, len(latencies) - 2)])
        else:
            rel_floor = float(reliabilities[0])
            lat_ceil = float(latencies[-1])

        tasks.append(Task(
            id=TaskId("wf" + str(int(rng.integers(1, 4))), f"t{i + 1}"),
            task_type="generic",
            load=load,
            rel_floor=rel_floor,
            lat_ceil=lat_ceil,
        ))
    return tasks


def generate(n_tasks: int, n_profiles: int, budget_tightness: float,
             seed: int) -> ProblemInstance:
    """Same signature and same return type as generator.generate, so every track,
    the harness and the metrics work unchanged."""
    # Range matches generator.py: extended past 1.0 because the reference allocation is a
    # cliff rather than a neutral upper bound (F15).
    if not 0.0 < budget_tightness <= 3.0:
        raise ValueError(f"budget_tightness must be in (0, 3], got {budget_tightness}")
    if n_tasks < 1 or n_profiles < 1:
        raise ValueError("n_tasks and n_profiles must be >= 1")

    for attempt in range(MAX_REGENERATION_ATTEMPTS):
        # Offset the stream so a given seed does not reproduce generator.py's draws.
        rng = np.random.default_rng([seed, attempt, 7919])
        profiles = _draw_profiles(rng, n_profiles)
        tasks = _draw_tasks(rng, n_tasks, profiles)
        pools = _build_pools(tasks, profiles)

        if any(not pool for pool in pools.values()):
            continue

        reference_gpus = _reference_gpus(tasks, pools, profiles)
        budget = max(1, int(round(budget_tightness * reference_gpus)))
        return ProblemInstance(tasks=tasks, pools=pools, profiles=profiles,
                               budget=budget, reference_gpus=reference_gpus, seed=seed,
                               budget_tightness=budget_tightness)

    raise RuntimeError(
        f"could not generate an instance with all pools non-empty in "
        f"{MAX_REGENERATION_ATTEMPTS} attempts (n_tasks={n_tasks}, "
        f"n_profiles={n_profiles}, seed={seed})")
