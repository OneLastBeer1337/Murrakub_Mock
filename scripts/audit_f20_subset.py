"""
Paired statistical audit of F20's subset-consolidation claim.

WHY THIS EXISTS. F29/F30 audited `main`'s headline numbers and found a systemic defect:
`mean(A) / mean(B)` is not a typical ratio when either distribution has a tail. Three claims
were corrected. F20 arrived from `mickie` in the step-1 merge *after* that audit, carrying the
same defect untested — "mean gap 32.37% down to 1.57%" was being quoted as "a twenty-fold
improvement", which is 32.37 / 1.57, one mean divided by another.

This computes what F30 would have computed: the PAIRED per-instance difference, same instance,
both conditions, with an interval. A paired interval that crosses zero means the effect is not
established at all.

The instance set is NOT claimed to reproduce F20's original run — that run's parameters were
not recorded beyond "the extended sweep", and its structured arm had 21 solvable instances.
This deliberately runs a larger set and states its parameters, exactly as F29 did when it
re-ran the 3-seed speedup claim with 10 seeds.

Run:  python scripts/audit_f20_subset.py
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from poc.harness import metrics
from poc.harness.runner import scale_sweep
from poc.instances.generator import generate as uniform_generate
from poc.instances.structured_generator import generate as structured_generate

SCALES = [(8, 4), (16, 6), (32, 8), (64, 10)]
SEEDS = range(10)
BUDGET_MULTIPLIER = 1.25
STRATEGIES = ["MILP", "A", "A+subset"]

BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 0


def bootstrap_ci(values, statistic=statistics.mean, resamples=BOOTSTRAP, alpha=0.05):
    """Percentile bootstrap interval. Reported rather than a t-interval because the paired
    differences are not assumed normal — that assumption is what got us here."""
    if len(values) < 2:
        return (None, None)
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    stats = []
    for _ in range(resamples):
        stats.append(statistic([values[rng.randrange(n)] for _ in range(n)]))
    stats.sort()
    lo = stats[int((alpha / 2) * resamples)]
    hi = stats[int((1 - alpha / 2) * resamples) - 1]
    return (lo, hi)


def audit(generator, label):
    records = scale_sweep(SCALES, seeds=SEEDS, strategies=STRATEGIES,
                          generator=generator, budget_multiplier=BUDGET_MULTIPLIER)

    total = len(records)
    solvable = [r for r in records if r.solvable]

    # The paired set: instances where the MILP PROVED an optimum and BOTH conditions returned
    # a feasible allocation. Dropping an instance from one arm only is the survivor bias
    # metrics.summarise was written to prevent.
    paired = []
    a_only_infeasible = sub_only_infeasible = both_infeasible = 0
    for r in solvable:
        a, sub = r.conditions["A"], r.conditions["A+subset"]
        if a.feasible and sub.feasible:
            paired.append((
                r,
                metrics.gap_to_optimum(a.result, r.optimum),
                metrics.gap_to_optimum(sub.result, r.optimum),
            ))
        elif a.feasible and not sub.feasible:
            sub_only_infeasible += 1
        elif sub.feasible and not a.feasible:
            a_only_infeasible += 1
        else:
            both_infeasible += 1

    print("=" * 78)
    print(f"{label} GENERATOR")
    print("=" * 78)
    print(f"instances run          : {total}  (scales {SCALES}, seeds {list(SEEDS)}, "
          f"budget x{BUDGET_MULTIPLIER})")
    print(f"solvable (MILP proved) : {len(solvable)}")
    print(f"paired, both feasible  : {len(paired)}")
    print(f"  dropped - A infeasible only        : {a_only_infeasible}")
    print(f"  dropped - A+subset infeasible only : {sub_only_infeasible}")
    print(f"  dropped - both infeasible          : {both_infeasible}")

    if len(paired) < 2:
        print("\nNOT ENOUGH PAIRED INSTANCES. No claim can be made.")
        return

    gaps_a = [g for _, g, _ in paired]
    gaps_sub = [s for _, _, s in paired]
    diffs = [g - s for _, g, s in paired]

    print(f"\n-- the means F20 quoted (both arms, same {len(paired)} instances) --")
    print(f"  A         mean gap : {statistics.mean(gaps_a):7.2f}%   "
          f"median {statistics.median(gaps_a):7.2f}%")
    print(f"  A+subset  mean gap : {statistics.mean(gaps_sub):7.2f}%   "
          f"median {statistics.median(gaps_sub):7.2f}%")
    ratio_of_means = (statistics.mean(gaps_a) / statistics.mean(gaps_sub)
                      if statistics.mean(gaps_sub) > 0 else float("inf"))
    print(f"  RATIO OF MEANS     : {ratio_of_means:7.2f}x   <-- the defect, do not quote")

    print("\n-- the paired statistic (what replaces it) --")
    lo, hi = bootstrap_ci(diffs)
    print(f"  paired difference  : {statistics.mean(diffs):7.2f} pp  "
          f"[{lo:.2f}, {hi:.2f}]  (95% bootstrap, {BOOTSTRAP} resamples)")
    print(f"  median difference  : {statistics.median(diffs):7.2f} pp")
    mlo, mhi = bootstrap_ci(diffs, statistic=statistics.median)
    print(f"  median difference CI: [{mlo:.2f}, {mhi:.2f}]")

    # Per-instance ratio, the honest version of "twenty-fold".
    ratios = [g / s for _, g, s in paired if s > 1e-9]
    zero_gap = sum(1 for _, _, s in paired if s <= 1e-9)
    if ratios:
        print(f"  median per-instance ratio : {statistics.median(ratios):7.2f}x  "
              f"(n={len(ratios)}; {zero_gap} instances excluded, A+subset gap is exactly 0)")
    else:
        print(f"  median per-instance ratio : undefined (A+subset gap is 0 on all)")

    better = sum(1 for d in diffs if d > 1e-9)
    same = sum(1 for d in diffs if abs(d) <= 1e-9)
    worse = sum(1 for d in diffs if d < -1e-9)
    print(f"\n  A+subset better / same / WORSE : {better} / {same} / {worse}")

    opt_a = sum(1 for _, g, _ in paired if g <= 1e-9)
    opt_sub = sum(1 for _, _, s in paired if s <= 1e-9)
    print(f"  matched the optimum  A: {opt_a}/{len(paired)}   "
          f"A+subset: {opt_sub}/{len(paired)}")

    # Per-scale, because chapter3_benchmark_results.md claims "<2% at all scales" and a
    # pooled mean cannot confirm or refute a per-scale claim.
    print("\n-- per scale (checks the \"<2% at all scales\" claim) --")
    print(f"  {'scale':>10}  {'n':>3}  {'A mean':>8}  {'A+sub mean':>11}  "
          f"{'A+sub median':>13}  {'paired diff':>11}")
    for n_tasks, n_profiles in SCALES:
        rows = [(g, s) for r, g, s in paired if len(r.instance.tasks) == n_tasks]
        if not rows:
            continue
        ga = [g for g, _ in rows]
        gs = [s for _, s in rows]
        dd = [g - s for g, s in rows]
        flag = "" if statistics.mean(gs) < 2.0 else "   <-- NOT <2%"
        print(f"  {str(n_tasks) + 't':>10}  {len(rows):>3}  {statistics.mean(ga):7.2f}%  "
              f"{statistics.mean(gs):10.2f}%  {statistics.median(gs):12.2f}%  "
              f"{statistics.mean(dd):10.2f}pp{flag}")

    established = lo is not None and lo > 0
    print(f"\n  VERDICT: effect {'ESTABLISHED' if established else 'NOT established'} "
          f"- the paired interval {'excludes' if established else 'includes'} zero.")
    print()


if __name__ == "__main__":
    print("F20 paired audit - subset consolidation vs plain greedy")
    print("Method: paired per-instance gap difference, percentile bootstrap interval.\n")
    audit(structured_generate, "STRUCTURED")
    audit(uniform_generate, "UNIFORM")
