# `poc/` — the September proof-of-concept

Scope-guarded. Everything here exists to answer T1–T4 and nothing else. If a module does not
help answer one of those four questions, it belongs in `prototype/` or nowhere.

`poc/` imports nothing from `prototype/`. The dependency only runs the other way.

## Layout

```
formulation/   the problem as data (types) and as assertions (invariants I1-I5)
instances/     two generators, deliberately different, plus the hand-verified fixture
core/          ProvisioningState, the shared decision rule, and the move neighbourhoods
tracks/        every allocation strategy, one file each
harness/       matched-condition runner and the metrics that stop survivor bias
tests/         property, unit, component, bound, sweep and adversarial levels
```

## The conditions

| condition | file | role |
|---|---|---|
| `MILP` | `exact_milp.py` | Ground truth, and the Murakkab baseline. Reports `converged` — only trust it when true |
| `STATIC` | `static_baseline.py` | No optimisation. The scale everything else is read against |
| `A` | `track_a_greedy.py` | Plain greedy. Kept for reference, **not reported in results** |
| `A+M1` | `track_a_m1.py` | Greedy plus a feasibility lookahead |
| `A+rel` | `track_a_relocate.py` | Greedy plus single-move relocate (T2's method) |
| `B` | `track_b_lagr.py` | Lagrangian, relaxing (C1). The best bound |
| `B-cold` | `track_b_cold.py` | Same, no warm start — proves the warm start is inert |
| `B-C2` | `track_b_capacity.py` | Relaxing capacity. Decomposes per task, bound no better than the LP |
| `B-C3` | `track_b_budget.py` | Relaxing the budget. Does not decompose |
| `C` | `track_c_lp.py` | LP relaxation plus rounding. **The result** |
| `C2` | `track_c_multi.py` | Track C with a second realisation order |
| `C+cons` | `track_c_consolidate.py` | Track C plus multi-move consolidation |

## Running it

```bash
pytest poc/tests                 # everything
python -m poc.harness.runner     # the comparison table
```

## Two things that will bite you if you do not know them

**`n[m]` is derived, never stored.** `ProvisioningState` computes it as `ceil(load/thr)`, so
admit and release are exact inverses and no repair pass can strand an instance. Invariants
I2 and I5 are true by construction as a result.

**Read `infeas` beside `mean gap%`, always.** A condition that only solves the easy instances
posts the best-looking gap. `harness/metrics.py` counts failures rather than averaging over
them for exactly this reason, and the first scale scripts got it wrong by bypassing it.
