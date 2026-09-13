"""
A third instance generator: a LOCAL, OWNED, HETEROGENEOUS fleet.

Spec: not in any document. This exists to close F31, and it is the first generator built to
answer a finding rather than to satisfy a requirement or a methodological objection.
Owner: 083

WHY THIS EXISTS

F31 answered O13 from Murakkab's own published numbers: `price(m)` is **not** a multiple of
`gpu(m)`. Murakkab reports GPU count, energy and dollar cost as three separate figures on one
matched workload and they move by three different factors, because their gains come from
trading A100s for H100s — price per GPU differs by hardware type.

Both existing generators assume the opposite:

    generator.py            price = gpus * U(80, 120)
    structured_generator.py price = gpus * U(95, 105)

so corr(price, gpus) sits at roughly 0.95-1.0 in both. That is a **homogeneous fleet**, where
every GPU costs the same and minimising cost is nearly the same objective as minimising GPUs.
The measured consequence (F26) was that the GPU budget did not change the optimal cost in 40
of 41 instances: (C3) constrained feasibility but almost nothing else.

That is a property of the instances, not of the problem, and it made T3's operating region and
T1's arm comparison the weakest possible test of themselves — both were measured where (C3)
barely binds. This generator is the instrument for re-running them where it does bind.

It also contradicts the project's own premise. The whole point is routing across
*heterogeneous* profiles; a fleet where every GPU is interchangeable is the one case where
that premise does not apply.

THE DEPLOYMENT DECISION THIS ENCODES

Decided 4 September 2026: **local first**. So `price(m)` is amortised capital plus energy over
the horizon for hardware the project owns, not an hourly rental rate. This matters, because
rental is the one regime where price genuinely is close to GPU-hours — a rented A100-hour and
a rented H100-hour differ by maybe 2x, and the correlation would be defensible. Owned mixed
hardware is not that case. A depreciating older node and a current one differ in cost per GPU
by far more, and their throughput per GPU differs too, in the same direction but not by the
same factor.

HOW IT DIFFERS

| | generator.py | structured | this |
|---|---|---|---|
| GPU counts | uniform 1-4 | tiers {1,2,4,8} | tiers, **anti-correlated with class** |
| price vs GPUs | linear, one rate | linear, one rate | **per-class rate spanning ~6x** |
| throughput vs GPUs | linear | sublinear | per-class rate, **non-monotone in price** |
| corr(price, gpus) | ~0.95-1.0 | ~0.95-1.0 | **near zero, by construction** |

Two mechanisms do the decorrelating, and both are things a real machine room does.

1. **Price per GPU is a property of the hardware class, not of the count.** A frontier node
   costs several times per GPU what a depreciated legacy node does.

2. **Node size is anti-correlated with class.** You own a few small frontier boxes and a pile
   of older, larger ones — new hardware arrives in small quantities and old hardware
   accumulates. This is what actually drives the correlation to zero: without it, price still
   rises with count within a class and the correlation survives at ~0.5-0.6.

NON-MONOTONE VALUE, WHICH IS THE POINT

Throughput per GPU rises with class, but **not in proportion to price**, and deliberately not
monotonically in value. `mainstream` is the best throughput-per-currency; `frontier` buys
latency and reliability rather than raw value; `legacy` is cheap per GPU but poor per watt and
per second. So no class dominates, and the optimiser cannot satisfy the budget by a simple
rule like "prefer the cheapest" or "prefer the biggest".

The consequence that matters for T3: minimising cost and minimising GPUs are now **different
objectives**. A routing can be cheap and GPU-hungry, or GPU-lean and expensive. That is the
regime (C3) was written for and the one neither existing generator produces.

WHAT IS DELIBERATELY KEPT IDENTICAL

The budget anchor (`_reference_gpus`), the (C1)-non-empty regeneration guarantee, and the
`ProblemInstance` shape. Changing the anchor as well would confound a generator comparison
with an anchor comparison — the same reasoning structured_generator.py records, and the anchor
is already known to matter (F2, F3).
"""

from __future__ import annotations

import math

import numpy as np

from poc.formulation.types import ProfileSpec, Task, TaskId
from poc.instances.generator import (MAX_REGENERATION_ATTEMPTS, ProblemInstance,
                                     _build_pools, _reference_gpus)


class HardwareClass:
    """One hardware generation in the owned fleet.

    `price_per_gpu` is amortised capital plus energy over the horizon, NOT a rental rate.
    `sizes` is anti-correlated with class on purpose — see the module docstring.
    """

    __slots__ = ("name", "price_per_gpu", "throughput_per_gpu", "sizes",
                 "reliability", "latency_base")

    def __init__(self, name, price_per_gpu, throughput_per_gpu, sizes,
                 reliability, latency_base):
        self.name = name
        self.price_per_gpu = price_per_gpu          # (lo, hi)
        self.throughput_per_gpu = throughput_per_gpu
        self.sizes = sizes
        self.reliability = reliability
        self.latency_base = latency_base


# Cost per GPU spans ~6x across the fleet. Throughput per GPU spans ~2.2x, and NOT in
# proportion — that mismatch is what makes cost and GPU count different objectives.
#
# Value per GPU (throughput per unit price), roughly:
#   legacy      6.5 / 38   = 0.171     cheap, but poor value and slow
#   mainstream  11.0 / 95  = 0.116     -- best absolute throughput per node, mid value
#   frontier    14.5 / 240 = 0.060     buys latency and reliability, not value
#
# Deliberately non-monotone against price: legacy is the best value per GPU and the worst
# choice for a latency-floored task, so neither "cheapest" nor "biggest" is a winning rule.
FLEET = (
    HardwareClass("legacy",     (34.0, 42.0),   (5.5, 7.5),   (4, 8),
                  (0.900, 0.945), 95.0),
    HardwareClass("mainstream", (88.0, 102.0),  (9.5, 12.5),  (2, 4),
                  (0.940, 0.975), 55.0),
    HardwareClass("frontier",   (215.0, 265.0), (13.0, 16.0), (1, 2),
                  (0.980, 0.999), 26.0),
)


def _draw_profiles(rng, n_profiles: int) -> dict[str, ProfileSpec]:
    profiles = {}
    for i in range(n_profiles):
        pid = f"m{i + 1}"
        hw = FLEET[int(rng.integers(0, len(FLEET)))]
        gpus = int(hw.sizes[int(rng.integers(0, len(hw.sizes)))])

        # Price is gpus x a CLASS rate, not gpus x a global rate. Because the class also
        # selects the size range, and does so inversely, gpus carries little information
        # about price -- which is the whole construction.
        price = float(np.round(gpus * rng.uniform(*hw.price_per_gpu), 2))
        throughput = float(np.round(gpus * rng.uniform(*hw.throughput_per_gpu), 2))

        profiles[pid] = ProfileSpec(
            id=pid,
            declared_type=hw.name,
            throughput=throughput,
            gpus=gpus,
            price=price,
            reliability=float(np.round(rng.uniform(*hw.reliability), 3)),
            # Newer hardware is faster per token. Larger nodes within a class pay a small
            # coordination penalty, so latency is not purely a class property.
            latency=float(np.round(hw.latency_base + 6.0 * math.log2(gpus)
                                   + rng.uniform(-6.0, 14.0), 1)),
        )
    return profiles


def _draw_tasks(rng, n_tasks: int, profiles: dict[str, ProfileSpec]) -> list[Task]:
    """Floors drawn from the profiles' own values, as in both existing generators.

    Kept identical rather than made novel: the point of this generator is the PRICE
    structure, and varying the task side as well would confound which change moved a result.
    """
    reliabilities = sorted(p.reliability for p in profiles.values())
    latencies = sorted(p.latency for p in profiles.values())
    tasks = []
    for i in range(n_tasks):
        tasks.append(Task(
            id=TaskId("wf" + str(int(rng.integers(1, 4))), f"t{i + 1}"),
            task_type="generic",
            load=float(np.round(rng.uniform(1.0, 20.0), 2)),
            rel_floor=float(rng.choice(reliabilities)),
            lat_ceil=float(rng.choice(latencies)),
        ))
    return tasks


def price_gpu_correlation(profiles: dict[str, ProfileSpec]) -> float | None:
    """corr(price, gpus) over one instance's profiles. None if either side is constant.

    Exposed because it is the quantity F31 is about: ~0.95-1.0 in the two existing
    generators, and the thing this one is built to break. Tests assert on it.
    """
    prices = np.array([p.price for p in profiles.values()], dtype=float)
    gpus = np.array([float(p.gpus) for p in profiles.values()], dtype=float)
    if len(prices) < 2 or prices.std() == 0.0 or gpus.std() == 0.0:
        return None
    return float(np.corrcoef(prices, gpus)[0, 1])


def generate(n_tasks: int, n_profiles: int, budget_tightness: float,
             seed: int) -> ProblemInstance:
    if not 0.0 < budget_tightness <= 3.0:
        raise ValueError(f"budget_tightness must be in (0, 3], got {budget_tightness}")
    if n_tasks < 1 or n_profiles < 1:
        raise ValueError("n_tasks and n_profiles must be >= 1")

    for attempt in range(MAX_REGENERATION_ATTEMPTS):
        rng = np.random.default_rng([seed, attempt])
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
