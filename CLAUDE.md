# CLAUDE.md

Context for the PoC implementation. Read `System_Architecture_v2.md` for full detail; this file
is the working summary and the guardrails.

---

## What this is

A proof-of-concept for a **two-level resource allocation problem**: route tasks to model
profiles, and decide how many instances of each profile to provision, minimising provisioning
cost under a GPU budget.

The PoC exists to answer four questions before the real system is built. It is **not** a
scaled-down version of the system.

| Test | Question |
|---|---|
| T1 | Which constraint should Track B relax, and does its bound beat the LP bound? |
| T2 | Can greedy construction be defeated by aggregate coupling? |
| T3 | Over what budget range does the problem have interesting structure? |
| T4 | Is Track A worth its complexity relative to Track C? |

**Deadline: 30 September 2026.**

---

## The problem

```text
Variables
  x[t][m] ∈ {0,1}    task t routed to profile m ∈ C(t)      (routing)
  n[m]    ∈ Z⁺       instances of profile m provisioned      (provisioning)

Objective
  minimize  Σ_m n[m] · price(m)

Constraints
  (C1)  Σ_{m ∈ C(t)} x[t][m] = 1                              ∀t
  (C2)  Σ_{t} x[t][m] · load(t)  ≤  n[m] · thr(m)             ∀m
  (C3)  Σ_m n[m] · gpu(m)  ≤  B

Eligibility (applied when building C(t), not as constraints)
  C(t) = { m : rel(m) ≥ R_min(t)  and  lat(t,m) ≤ L_max(t) }
```

**Problem class:** modular capacitated facility location with a budget constraint. Profiles are
sites, `n[m]` is units opened at a site, tasks are customers, (C2) is site capacity.

**Where the difficulty is:** (C2) couples tasks to each other. A task's marginal cost depends on
whether its profile already has headroom — which depends on assignments not yet made. This is
the central issue Track A must handle and T2 tests.

---

## Ground-truth instance (verified by hand)

Use this to validate the MILP at build step 4. **Do not change these numbers** — the optimum
below was computed by exhaustion.

```text
Profiles
  m1:  thr=10  gpu=1  price=100  rel=0.99  lat=50
  m2:  thr=25  gpu=2  price=180  rel=0.95  lat=80

Tasks
  t1:  load=8  relFloor=0.90  latCeil=100   → C(t1) = {m1, m2}
  t2:  load=6  relFloor=0.90  latCeil=100   → C(t2) = {m1, m2}
  t3:  load=9  relFloor=0.98  latCeil=100   → C(t3) = {m1}     (m2 fails reliability)

Budget  B = 4
```

Full enumeration (t3 is forced to m1; enumerate subsets of {t1,t2} routed to m2):

| Routing | n[m1] | n[m2] | GPUs | Cost |
|---|---|---|---|---|
| all on m1 | ceil(23/10)=3 | 0 | 3 | **300** |
| t1→m2 | ceil(15/10)=2 | 1 | 4 | 380 |
| t2→m2 | ceil(17/10)=2 | 1 | 4 | 380 |
| **t1,t2→m2** | ceil(9/10)=1 | 1 | 3 | **280 ← OPTIMUM** |

**Optimum: 280**, routing `{t1→m2, t2→m2, t3→m1}`, provisioning `{m1:1, m2:1}`, 3 GPUs.

### Why this instance matters beyond validating the MILP

Traced by hand, **greedy construction returns 300, not 280.**

```text
t1: m1 costs 100 (open 1 instance), m2 costs 180  → picks m1.  n[m1]=1, load=8
t2: m1 headroom 2 < 6 → +1 instance = 100; m2 = 180  → picks m1.  n[m1]=2, load=14
t3: m1 headroom 6 < 9 → +1 instance = 100; m2 ineligible  → m1.   n[m1]=3, load=23
Total: 300
```

Greedy's myopia is exactly the aggregate-coupling problem: `t1` and `t2` are individually
cheaper on `m1`, but *together* they fit one `m2` instance with room left over.

Further, verified by exhaustive enumeration:

- **Multi-start does not rescue it.** All six orderings of `{t1,t2,t3}` return 300. Greedy
  always takes `m1` first because it is individually cheaper, and the cascade follows.
- **Single-move relocate does not rescue it.** Moving `t1` alone to `m2` costs +180 and saves
  only 100. Net worse. Same for `t2` alone. The improving move is *both together*, which a
  one-at-a-time relocate cannot find.

So this fixture establishes a specific T2/T4 result: **Track A needs a multi-move
neighbourhood or a consolidation step; multi-start plus single-move relocate is provably
insufficient on this instance.**

Store as `instances/fixtures/adversarial_3t2p.py`.

---

## Build order

Do not reorder. Each step is verifiable before the next.

| # | Build | Verify by |
|---|---|---|
| 1 | `formulation/types.py` | Types instantiate |
| 2 | `formulation/invariants.py` | Hand-built valid and violating results |
| 3 | `instances/generator.py` | Instances well-formed; every `C(t)` non-empty |
| 4 | `tracks/exact_milp.py` | **Returns 280 on the fixture above** |
| 5 | `core/provisioning.py` | admit/release/snapshot/restore; budget rejection |
| 6 | `core/decision_rule.py` | Known pools, known picks; all-infeasible returns None |
| 7 | `tracks/track_c_lp.py` | Bound ≤ MILP optimum; satisfies I1–I5 |
| 8 | `tracks/track_b_lagr.py` | Bound ≤ optimum; compare to LP bound (T1) |
| 9 | `tracks/track_a_greedy.py` | Satisfies I1–I5; **returns 300 on the fixture** |
| 10 | `harness/` | Reproduces a known result end-to-end |

All ten steps are built. Conditions beyond the ten: `STATIC` (no-optimisation baseline),
`A+M1` (feasibility lookahead), `C2` (Track C with the extra realisation attempt). Run
`python -m poc.harness.runner`; results in `docs/poc_findings.md`.

**Build the exact solver before any heuristic.** Nothing can be checked for correctness without
ground truth.

---

## Invariants — assert on every result, in every test

```text
I1  every task appears exactly once in routing                    (C1)
I2  for every m: Σ load routed to m  ≤  n[m] · thr(m)             (C2)
I3  Σ n[m] · gpu(m)  ≤  B                                          (C3)
I4  every routed profile is in C(t) for its task                  (floors)
I5  n[m] ≥ 1 for every profile appearing in routing
```

All three tracks have relaxation or rounding steps that can silently emit violating results.
`formulation/invariants.check()` is the single highest-value piece of test infrastructure here —
wire it in at step 2 and call it everywhere.

---

## Key module contracts

```python
# core/provisioning.py — the central component
class ProvisioningState:
    def __init__(self, profiles, budget): ...
    def cost_to_admit(self, task, profile_id) -> AdmitCost | None   # None = over budget
    def admit(self, task, profile_id) -> None
    def release(self, task, profile_id) -> None
    def snapshot(self) -> dict
    def restore(self, snap: dict) -> None
    def build_provisioning(self) -> dict[str, int]                  # n[m]
    def total_cost(self) -> float
    def gpus_used(self) -> int

# AdmitCost.extra_instances = 0 when existing headroom covers the task
# This state-dependence IS the aggregate-coupling problem. Get it right first.

# core/decision_rule.py
def select_profile(task, pool, state, cost_adjust) -> str | None

# every track
def allocate(tasks, pools, profiles, budget, seed=0) -> AllocationResult
# returns feasible=False rather than raising, so the harness records failures as data
```

---

## Scope guard — do not build

- Executor Registry — the generator supplies profiles directly
- Profiling Subsystem — profiles are static inputs in the PoC
- Execution Engine — nothing is executed
- Drift detection, re-optimisation, J9
- Zookeeper / LogHub domain data — synthetic instances only
- Track A's relocate, consolidate, or elaborate multi-start — **T4 decides whether these are
  worth building.** `track_a_greedy.py` stays plain greedy. The M1 analogue lives in
  `track_a_m1.py` as a *separate condition* so T4 can price it rather than have it assumed.
- Monitoring, fallback, framework integration

> If a module does not help answer T1, T2, T3, or T4, it does not belong in the PoC.

---

## Things that are settled — do not reintroduce

- **HEFT is not used.** Neither Murakkab nor Cheng & Nguyen has precedence constraints or a
  makespan term. Upward rank orders tasks by a quantity absent from the objective. This was a
  real error in an earlier design; do not reintroduce it.
- **Capacity is consumed by instances, not by task assignments.** An earlier design had a slot
  ledger decremented per task. Wrong. Tasks add *load*; load may or may not force a new
  instance.
- **Precedence does not enter the optimisation.** DAG edges determine execution order only.

---

## Open questions the code is meant to answer

These are **not** assumptions to encode. If the implementation needs one settled, flag it
rather than picking silently.

| ID | Question |
|---|---|
| O2 | Which constraint does Track B relax? **Built against (C1)** per §1.8. Still an assumption — relaxing (C3) is unmeasured |
| O3 | Is Track B's bound strictly better than Track C's LP bound? **Preliminary: yes, 30/30** |
| O4 | Can greedy be defeated by aggregate coupling? **Yes** — fixture confirmed, and it fails on feasibility far more often than on cost |
| O5 | Step-size schedule, tolerance, iteration cap for Track B — still open, values in `track_b_lagr.py` are untuned defaults. **Promoted to blocking (F34, refined by F35):** where Track B finds no feasible incumbent, Polyak's rule has no target and the bound stalls below the LP's — which the dual optimum cannot do. The primary lever is the **incumbent**, not the schedule: supplying one from Track C or `A+subset` would likely recover it, but that deepens the warm-start entanglement `track_b_lagr.py` warns about and is 075/089's call |
| O6 | ~~LP rounding policy~~ → **the repair pass**. The LP returns integral routings 96% of the time |
| O7 | Where does the budget bind? **Answered (F33): wherever price per GPU is not constant.** (C3) changes the optimum in 24/25 heterogeneous instances vs 0–4/25 on the two per-GPU-price generators. Anchor amended, see findings F2 |
| O8 | Is Track A worth its complexity? |

**O1 is closed (2 September 2026): no per-invocation term.** The objective is provisioning
cost only, and `ProfileSpec` carries no `varcost` field. Reopening it changes the objective
signature everywhere.

---

## Environment

```text
Python 3.11+
pulp            # MILP modelling
                # CBC ships with PuLP; verify with pulp.listSolvers(onlyAvailable=True)
numpy
pytest
```

Determinism: every track takes `seed`. Randomised orderings must derive from it, so runs
reproduce exactly (principle P10).

---

## Conventions

- Tracks return `AllocationResult` with `feasible=False`; they do not raise on infeasibility
- Infeasibility names the blocking task and the violated constraint (`C1`/`C2`/`C3`)
- Unprofiled entries return `NotProfiled`, never a default value
- No module outside `core/provisioning.py` mutates provisioning state
- Every result passes `invariants.check()` before leaving a track
