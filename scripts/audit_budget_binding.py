"""
Does the GPU budget (C3) do anything? F26 re-run across all three generators.

WHY THIS EXISTS

F26 measured that the budget does not change the optimal cost in 40 of 41 instances — (C3)
constrained feasibility, not choice. F31 then showed why: both generators set price to a fixed
multiple of GPU count, so minimising cost and minimising GPUs are nearly the same objective
and the budget has almost nothing to decide. That made F26 a finding about our instances
rather than about the problem, and left T3's operating region and T1's arm comparison measured
where (C3) barely binds.

`heterogeneous_generator.py` is the instrument built to fix that. This script is the
measurement that says whether it worked.

METHOD

For each instance, hold the tasks and profiles fixed and vary ONLY the budget B, then solve to
optimality at each level. If the optimal cost changes as B tightens, (C3) is changing the
decision, not just admitting or rejecting it. That isolates the budget as the single varying
input — the same matched-conditions discipline runner.py applies across tracks (v2 §4.7).

Reported per generator:
  - binding rate: instances where the optimum cost differs across feasible budget levels
  - cost inflation: how much the tightest feasible budget costs over the loosest
  - corr(price, gpus): the F31 quantity, for context

Run:  python scripts/audit_budget_binding.py
"""

from __future__ import annotations

import dataclasses
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np

from poc.instances.generator import generate as uniform_generate
from poc.instances.heterogeneous_generator import generate as heterogeneous_generate
from poc.instances.heterogeneous_generator import price_gpu_correlation
from poc.instances.structured_generator import generate as structured_generate
from poc.tracks import exact_milp

N_TASKS = 16
N_PROFILES = 8
SEEDS = range(25)
# Multiples of the reference allocation. 1.5 is comfortably loose; below 1.0 bites.
BUDGET_MULTIPLIERS = (1.5, 1.25, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5)
TOL = 1e-6


def solve(instance):
    tasks, pools, profiles, budget = instance.unpack()
    result = exact_milp.allocate(tasks, pools, profiles, budget, seed=0)
    if not result.feasible or result.converged is False:
        return None
    return result.total_cost


def audit(generator, label):
    binding = non_binding = unusable = 0
    inflations = []
    corrs = []

    for seed in SEEDS:
        base = generator(n_tasks=N_TASKS, n_profiles=N_PROFILES,
                         budget_tightness=1.0, seed=seed)
        c = price_gpu_correlation(base.profiles)
        if c is not None:
            corrs.append(c)

        costs = []
        for mult in BUDGET_MULTIPLIERS:
            b = max(1, int(round(base.reference_gpus * mult)))
            cost = solve(dataclasses.replace(base, budget=b))
            if cost is not None:
                costs.append((b, cost))

        # Distinct budgets only: two multipliers can round to the same integer B, and
        # counting those as agreement would understate binding.
        by_budget = dict(costs)
        if len(by_budget) < 2:
            unusable += 1
            continue

        lo, hi = min(by_budget.values()), max(by_budget.values())
        if hi - lo > TOL:
            binding += 1
            inflations.append((hi - lo) / lo * 100.0)
        else:
            non_binding += 1

    usable = binding + non_binding
    print("=" * 72)
    print(f"{label}")
    print("=" * 72)
    print(f"  corr(price, gpus)      : {np.mean(corrs):+.3f}  (per-instance mean)")
    print(f"  instances usable       : {usable}/{len(SEEDS)}"
          + (f"   ({unusable} had <2 feasible budget levels)" if unusable else ""))
    if usable:
        print(f"  (C3) CHANGES the optimum : {binding}/{usable}"
              f"   ({binding / usable * 100:.0f}%)")
        print(f"  (C3) inert               : {non_binding}/{usable}")
    if inflations:
        print(f"  cost inflation at the tightest feasible budget:")
        print(f"      mean {statistics.mean(inflations):6.2f}%   "
              f"median {statistics.median(inflations):6.2f}%   "
              f"max {max(inflations):6.2f}%")
    print()
    return binding, usable


if __name__ == "__main__":
    print("Does the GPU budget do anything? (F26 re-run, F31's question)\n")
    print(f"{N_TASKS} tasks, {N_PROFILES} profiles, seeds {SEEDS.start}-{SEEDS.stop - 1}, "
          f"budget multipliers {BUDGET_MULTIPLIERS}\n")
    results = {}
    for gen, label in [(uniform_generate, "UNIFORM  (price = gpus x one rate)"),
                       (structured_generate, "STRUCTURED  (price = gpus x one rate)"),
                       (heterogeneous_generate,
                        "HETEROGENEOUS  (price = gpus x a CLASS rate)")]:
        results[label] = audit(gen, label)

    print("=" * 72)
    print("SUMMARY - (C3) changes the optimal cost in:")
    for label, (b, u) in results.items():
        if u:
            print(f"  {b:>3}/{u:<3} ({b / u * 100:3.0f}%)   {label}")
