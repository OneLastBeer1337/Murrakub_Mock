"""
T1, re-run where the budget actually binds.

WHY THIS EXISTS

T1 asks which constraint Track B should relax, and whether its bound beats the LP bound. It
was answered on the two generators that tie price to GPU count, and F31 flagged the answer as
provisional for a specific reason: the (C3) arm was compared on instances where (C3) barely
binds, which is the weakest possible test of a relaxation of (C3).

F33 then built `heterogeneous_generator.py`, where (C3) changes the optimal cost in 24 of 25
instances instead of 0 of 25. This re-runs T1 there.

THE HYPOTHESIS WORTH STATING BEFORE MEASURING

The prior result was that `B-C3`'s bound *matches* the LP bound (agreement to 2e-5), explained
as: relaxing (C3) and the integrality of n[m] together is what buys per-task decomposition,
and restoring nothing means Lagrangian duality guarantees no more than the LP.

That explanation is structural, so it should survive a change of instances. But there is a
competing explanation that is NOT structural — the two agreed because the constraint being
dualised was nearly inert, so its multiplier sat near zero and the relaxation was nearly the
LP by default. Those two stories are indistinguishable on the old instances and make different
predictions here. This measurement separates them.

All three arms are run, so this is a complete T1 answer rather than a spot check:
  B      relaxes (C1)   - the shipped arm
  B-C2   relaxes (C2)
  B-C3   relaxes (C3)   - the arm F31 called provisional
  C      the LP bound   - what they must beat to earn their place

METHOD

Bounds are compared as PAIRED per-instance differences in bound gap against the proven
optimum, per F30. A bound gap is (optimum - lower_bound) / optimum * 100, so SMALLER is
tighter and a positive paired difference means the arm is tighter than the LP.

Run:  python scripts/audit_t1_arms.py
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
from poc.harness.runner import run_conditions
from poc.instances.generator import generate as uniform_generate
from poc.instances.heterogeneous_generator import generate as heterogeneous_generate
from poc.instances.structured_generator import generate as structured_generate

N_TASKS = 16
N_PROFILES = 8
SEEDS = range(15)
TIGHTNESS = (1.0, 0.8)          # 1.0 is feasible by construction; 0.8 makes (C3) bite
ARMS = ["B", "B-C2", "B-C3"]
CONDITIONS = ["MILP", "C"] + ARMS

BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 0


def bootstrap_ci(values, resamples=BOOTSTRAP, alpha=0.05):
    if len(values) < 2:
        return (None, None)
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    stats = sorted(statistics.mean([values[rng.randrange(n)] for _ in range(n)])
                   for _ in range(resamples))
    return (stats[int((alpha / 2) * resamples)],
            stats[int((1 - alpha / 2) * resamples) - 1])


def audit(generator, label):
    rows = []          # (lp_gap, {arm: gap}, lp_bound, {arm: bound})
    for tight in TIGHTNESS:
        for seed in SEEDS:
            try:
                inst = generator(n_tasks=N_TASKS, n_profiles=N_PROFILES,
                                 budget_tightness=tight, seed=seed)
            except RuntimeError:
                continue
            rec = run_conditions(inst, CONDITIONS)
            if not rec.solvable:
                continue

            lp = rec.conditions["C"].result
            lp_gap = metrics.bound_gap(lp, rec.optimum)
            if lp_gap is None:
                continue

            gaps, bounds = {}, {}
            for arm in ARMS:
                r = rec.conditions[arm].result
                g = metrics.bound_gap(r, rec.optimum)
                if g is None:
                    break
                gaps[arm] = g
                bounds[arm] = r.lower_bound
            else:
                rows.append((lp_gap, gaps, lp.lower_bound, bounds))

    print("=" * 76)
    print(f"{label}   ({len(rows)} paired instances)")
    print("=" * 76)
    if len(rows) < 2:
        print("  too few paired instances to say anything.\n")
        return

    print(f"  LP bound gap        : mean {statistics.mean(r[0] for r in rows):6.2f}%   "
          f"median {statistics.median(r[0] for r in rows):6.2f}%")
    print()
    print(f"  {'arm':<7} {'bound gap':>10}  {'vs LP, paired (pp, + = tighter)':>34}  "
          f"{'tighter on':>12}")
    for arm in ARMS:
        gaps = [r[1][arm] for r in rows]
        diffs = [r[0] - r[1][arm] for r in rows]          # LP gap - arm gap
        lo, hi = bootstrap_ci(diffs)
        tighter = sum(1 for d in diffs if d > 1e-9)
        same = sum(1 for d in diffs if abs(d) <= 1e-9)
        verdict = "" if lo is None or lo > 0 else "   (interval includes 0)"
        print(f"  {arm:<7} {statistics.mean(gaps):9.2f}%  "
              f"{statistics.mean(diffs):10.2f} [{lo:6.2f}, {hi:6.2f}]        "
              f"{tighter:>3}/{len(rows)}"
              + (f"  ({same} identical)" if same else "") + verdict)

    # The specific claim F31 called provisional: does B-C3 still equal the LP bound?
    deltas = [abs(r[3]["B-C3"] - r[2]) for r in rows]
    rel = [d / abs(b) if b else 0.0 for d, (_, _, b, _) in zip(deltas, rows)]
    print()
    print(f"  B-C3 vs LP bound, absolute difference:")
    print(f"      max {max(deltas):.3e}   median {statistics.median(deltas):.3e}   "
          f"max relative {max(rel):.2e}")
    identical = sum(1 for d in rel if d < 1e-6)
    print(f"      agree to 1e-6 relative on {identical}/{len(rows)} instances")
    print()


if __name__ == "__main__":
    print("T1 - which constraint should Track B relax, and does its bound beat the LP?\n")
    print(f"{N_TASKS} tasks, {N_PROFILES} profiles, seeds {SEEDS.start}-{SEEDS.stop - 1}, "
          f"tightness {TIGHTNESS}")
    print("Bound gap = (optimum - bound) / optimum. SMALLER is tighter.\n")
    for gen, label in [
        (uniform_generate, "UNIFORM  - (C3) nearly inert"),
        (structured_generate, "STRUCTURED  - (C3) inert"),
        (heterogeneous_generate, "HETEROGENEOUS  - (C3) binds in 96% (F33)"),
    ]:
        audit(gen, label)
