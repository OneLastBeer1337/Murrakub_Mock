# v1 — Superseded

Nothing in this directory is current. It is kept because it records advisor reasoning and
hand-worked results that `System_Architecture_v2.md` does not repeat, not because any of it
should be built from.

| File | Superseded by | Why |
|---|---|---|
| `ARCHITECTURE.md` | `../System_Architecture_v2.md` | Specified algorithms against a problem it never stated (v2 §0.2). Uses HEFT and a per-task slot ledger, both now retracted |
| `SCHEDULE.md` | `../PoC_and_Validation_Plan.md` §5.4 | Relative week numbering, v1 stage structure, references a Gantt image that predates the pivot |
| `offline_baselines/` | `../../poc/tracks/exact_milp.py` | Models capacity as `Σ gpu(t,c)·x[t,c] ≤ B` — consumed per task assignment. Under (C2)–(C3) capacity is consumed by provisioned instances; there is no `n[m]` anywhere in these scripts |

## The two errors, stated plainly

Both are listed as settled in `CLAUDE.md` — do not reintroduce either.

**HEFT.** v1's Track A ranked tasks by upward rank. Neither Murakkab nor Cheng & Nguyen has
precedence constraints or a makespan term, so upward rank orders tasks by a quantity absent
from the objective. Replaced by greedy construction. The v1 tree had `phase_b/heft/` with
three modules; they were empty stubs and have been deleted.

**Per-task capacity.** v1 modelled a slot pool decremented once per task assignment. Tasks do
not consume capacity — they add *load*, which may or may not force a new instance. This is the
correction at the heart of v2 (§0.1, §4.4).

## What is still worth reading here

`offline_baselines/README.md` answers the advisor's "MILP → solver, CPLEX?" question, and its
PuLP + CBC scaffolding is the pattern `poc/tracks/exact_milp.py` follows — the modelling
harness carries over even though the formulation does not.
