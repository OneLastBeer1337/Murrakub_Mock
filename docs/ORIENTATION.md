# Orientation — the whole project, from zero

**If you know nothing about this repo, read this file and nothing else.** It explains what the
project is, how the system is designed, what has actually been built and measured, and where
to look when you want more depth. Every claim here links to the document or file that backs
it.

**Active Design of Record:** [`docs/design/System_Architecture_v5.md`](design/System_Architecture_v5.md).  
**Test Baseline:** 721 passed, 4 skipped across `poc/tests/` and `prototype/tests/`.

> ### How much of this ages, and how fast
>
> A file that says "read this and nothing else" is in tension with a project whose answers are
> still moving. So be explicit about which is which.
>
> | | ages? | |
> |---|---|---|
> | §2 the problem, §5 the formal model, §6 the fixture, §4 the design | **No** | Settled. If these change, the project has changed |
> | §3 positioning, §4.3 requirements, §10 the team, §12 Semester 2 | **Slowly** | Changes when a decision is taken, and decisions are dated where they appear |
> | **§8 the four answers, §11 what exists** | **Yes, fast** | These are live measurements. Each carries the finding and date it was last verified |
>
> **T1's answer changed twice on 4 September alone.** That is normal here and not a sign
> anything is wrong — it is what an active audit looks like. But it means §8 is a snapshot.
>
> **Before quoting any number from this file**, check the *"numbers that were corrected"*
> table in [`poc_findings_summary.md`](evidence/poc_findings_summary.md). That table is maintained; this
> file is a summary of it. Where they disagree, **the summary wins** — and please fix this file.

---

## 1. In five sentences

We are building a system that decides, for a batch of AI workflows, **which model serves each
task** and **how many copies of each model to pay for**, minimising cost under a fixed GPU
budget. Those decisions depend on *profiles* — how fast, how reliable, how expensive each
model is — and the usual approach treats profiles as fixed numbers typed in by a human. Ours
**measures profiles from real execution, notices when they drift, and re-allocates.** The
allocation maths itself is textbook and we say so; the loop around it is the contribution.
This repo currently establishes **Architecture v5**, featuring concrete DAG topological
execution, online self-correcting profiles with 4-tier damping, and a formal closed-loop
evaluation harness.

---

## 2. The problem, in plain language

You have a batch of workflows. Each workflow is a DAG of tasks — "summarise this", "extract
entities", "generate code". Each task could be served by several different **model profiles**:
a profile is a concrete deployable thing, roughly `(model, hardware tier, batch config)`, and
different profiles differ in throughput, price, reliability and latency.

Two decisions have to be made together, for the whole batch, before anything runs:

| decision | symbol | meaning |
|---|---|---|
| **Routing** | `x[t][m]` | which profile `m` serves task `t` — exactly one each |
| **Provisioning** | `n[m]` | how many instances of profile `m` we pay for |

You want the cheapest total bill, and you cannot exceed a GPU budget.

**Why this is not trivial.** The two decisions are coupled in a circle. Routing determines how
much load lands on each profile. Load determines how many instances you must buy. Instances
consume GPUs. A tight GPU budget constrains what routing you were allowed to choose in the
first place.

**Where the real difficulty lives** is subtler and it has a name in this project: *aggregate
coupling*. Capacity is bought in **whole instances**, not per task. So the cost of putting a
task somewhere depends on whether that profile already has spare room — which depends on
decisions you have not made yet. Two tasks that are each individually expensive to move can be
cheap to move *together*. **Section 6** works through the smallest example we have, by hand.

---

## 3. What is ours, and what is borrowed

This is the honest positioning, and it is settled team policy — do not quietly upgrade it.

**Borrowed.** The allocation problem is a known one: **modular capacitated facility location
with a budget constraint.** Profiles are facilities, `n[m]` is units opened at a facility,
tasks are customers, the capacity constraint is facility capacity. We do not claim novelty
here and we present it as adopted. See [`System_Architecture_v5.md`](design/System_Architecture_v5.md) §2.6.

**Ours.** The **closed loop**: measure profiles from execution, detect drift, re-optimise.
Neither of the two closest papers does this — both take profiles as static inputs. The advisor
confirmed on 3 September that this is a sufficient novelty claim for M1 (open question O12).

**The evidence for it**, and the single most important number in the project: under drift, a
static allocator delivers **0.542 reliability against a 0.95 floor while reporting no change**,
where the adaptive loop holds **0.938**. Paired difference **+0.424 [0.405, 0.442]** over 20
seeds. That is finding F24.

The optimiser exists *because the loop needs one that is fast enough to re-run*. It is the
engine, not the contribution. `proposal_narrative.md` is the argument chain in full.

### 3.1 What came from where

Chapter 2 is the weakest part of the written proposal, so knowing the provenance of each idea
matters. Full version in [`System_Architecture_v5.md`](design/System_Architecture_v5.md) §0, §1.1.

| source | what we took |
|---|---|
| **Chaudhry et al. (2026), Murakkab** | The capacity model — instances provisioned against routed load under a GPU budget — the DAG workflow representation, and the MILP baseline. Our formulation **is** their model, which is why the MILP condition *is* the Murakkab comparison |
| **Cheng & Nguyen (2026)** | Feasibility-first-then-minimise-cost, marginal activation-cost ranking, multi-start construction. Track A's ancestry |
| **de la Torre & Halappanavar (2023)** | Lagrangian relaxation with subgradient updates. Track B's method |
| **Capacitated facility location literature** | The problem class itself, and relaxing the assignment constraints as the classical decomposition |
| **Hua et al. (2026), AgentOpt** | Transport-layer interception and call-context attribution — how profiling attaches to real execution |
| **Hatherley (2025)** | The decision compatibility score (formalized in v5 §8.2) |
| ~~Topcuoglu et al. (2002); Zhao & Sakellariou~~ | **No longer used.** HEFT and upward-rank were an early error: they order tasks by a quantity absent from our objective, since we have no makespan term |

---

## 4. How the system is designed

### 4.1 The loop

The system is a cycle of jobs, J1 through J9. The implementation in `prototype/` implements it
end to end with concrete DAG execution and online self-correcting profiling.

```
   J1 ingest a batch of workflow DAGs          prototype/ingestion.py
        |
   J2 resolve eligibility  C(t)                prototype/registry.py
        |
   J3 ALLOCATE  (routing x, provisioning n)    poc/tracks/*.py
        |
   J4 provision instances                      poc/core/provisioning.py
        |
   J5/J6 execute, emit observations            prototype/engine.py
        |
   J7 update profiles from what happened       prototype/profiling.py
        |
   J8 detect drift
        |
   J9 re-optimise  ------> back to J3          prototype/reoptimisation.py
```

**J3 is the part this repo has studied hardest**, because it is the part that has to be cheap
enough to run every time J9 fires.

### 4.2 Components

| component | what it does | state |
|---|---|---|
| **Multi-Workflow Optimizer** | J3 — solves the allocation | **built**, five families of algorithm (Track C: sub-35ms) |
| **Provisioning State** | owns `n[m]`, the budget, admit/release | **built**, `poc/core/provisioning.py` |
| **Eligibility Resolver** | builds `C(t)` from floors + UCB | **built**, `prototype/registry.py` (G10) |
| **Profiling Subsystem** | updates profiles, detects drift | **built**, `prototype/profiling.py` (G2 4-tier damping, G6/G7) |
| **Executor Registry** | catalogue of profiles | **built**, `prototype/registry.py` |
| **Execution Engine** | topological DAG execution on real logs | **built**, `prototype/engine.py` (ZooKeeper LogHub, G3/G4) |
| **Evaluation Harness** | static sweep & closed-loop benchmark | **built**, `poc/harness/closed_loop_runner.py` (G9) |

**`ProvisioningState` is the centre of the design.** Every track goes through it, and it is
where aggregate coupling is made concrete: `cost_to_admit()` returns `extra_instances = 0`
when existing headroom already covers a task. Get that wrong and every result is wrong.

### 4.3 Requirements Traceability Matrix

In Architecture v5 (Design of Record: [`System_Architecture_v5.md`](design/System_Architecture_v5.md) §9.1), all core requirements R1–R10 are addressed and verified across the platform:

| # | Requirement | Implementation Component | Verification Status |
|---|---|---|---|
| **R1** | Per-task allocation | J3, the Multi-Workflow Optimizer (`poc/tracks/`) | Verified (Exact MILP, Track C) |
| **R2** | Multiple concurrent workflows | Coupled via Constraint C2 in `poc/core/provisioning.py` | Verified (Multi-workflow batches) |
| **R3** | Non-exact alternatives to MILP | Fast solvers: Tracks A, B, C | Verified (Track C sub-35ms) |
| **R4** | Profile-guided, self-updating profiles | J6/J7, `prototype/profiling.py` (G2 4-tier damping) | Verified (`test_profiling_v5.py`) |
| **R5** | Re-optimise on drift | J8/J9, `prototype/loop.py` & `prototype/reoptimisation.py` | Verified (`pipeline_mockup.py`) |
| **R6** | Evaluate against exact baseline | `poc/harness/runner.py` & `closed_loop_runner.py` (G9) | Verified (150 instances, multi-epoch) |
| **R7** | Execution telemetry monitoring | `prototype/engine.py` load-scaled interceptor (G3) | Verified (`test_engine.py`) |
| **R8** | SLA floor reliability defense | Adaptive closed loop restoring reliability (0.542 -> 0.938) | Verified (Finding F24) |
| **R9** | Multi-workflow DAG execution | Concrete topological dispatcher (`prototype/engine.py`) | Verified (Real ZooKeeper traces) |
| **R10**| Formal invariant verification | Mandatory Invariant Suite I1–I5 (`poc/formulation/invariants.py`) | Verified on 100% of allocation results |

### 4.4 Ten principles the design holds to

Abbreviated from [`System_Architecture_v5.md`](design/System_Architecture_v5.md) §2.2. Several explain *why* the code looks
the way it does:

| | |
|---|---|
| P1 | Offline batch, not streaming — no admission control, no mid-run rebalancing |
| P2 | Eligibility is separate from selection — the resolver returns pools, never winners |
| **P3** | **Feasibility first, cost second** — floors filter `C(t)` and are never weighted against cost |
| P4 | One decision rule, three coordination strategies — every track calls the same inner rule |
| P5 | Tracks are swappable; none is privileged |
| P6 | Profiles are measured, not declared — online self-correction (G2) with 4-tier damping |
| P7 | Re-optimisation is event-driven — drift triggers it, not a clock |
| P8 | Structure is immutable after ingestion — drift re-enters the Optimizer only |
| **P9** | **Complete or nothing** — a partial assignment is never valid output |
| **P10** | **Reproducible given a fixed seed** — randomised restarts are seeded, matched conditions across trials |

### 4.5 One design correction worth knowing

An earlier version of the design had a "slot ledger" decremented per task assignment. **That
was wrong and is settled.** Capacity is consumed by *instances*, not by assignments — tasks
add *load*, and load may or may not force a new instance. Two other settled points: HEFT and
upward-rank scheduling are **not** used (there is no makespan term in the objective), and task
precedence affects execution order only, never the optimisation. See `CLAUDE.md`, "Things that
are settled".

---

## 5. The formal model

```
Variables
  x[t][m] ∈ {0,1}    task t routed to profile m ∈ C(t)
  n[m]    ∈ Z⁺       instances of profile m provisioned

Objective
  minimize  Σ_m n[m] · price(m)              ← provisioning cost only

Constraints
  (C1)  Σ_{m ∈ C(t)} x[t][m] = 1             ∀t   every task goes exactly one place
  (C2)  Σ_t x[t][m]·load(t) ≤ n[m]·thr(m)    ∀m   you must buy the capacity you use
  (C3)  Σ_m n[m]·gpu(m) ≤ B                        the GPU budget

Eligibility — applied when BUILDING C(t), not as a constraint
  C(t) = { m : rel(m) ≥ R_min(t)  and  lat(t,m) ≤ L_max(t) }
```

Three things people get wrong when they first read this:

1. **Reliability and latency are not constraints.** They are filters applied earlier, when the
   candidate list `C(t)` is built. A profile that fails a task's floor is never considered.
   Feasibility first, cost second. The advisor confirmed reliability is a **floor, not an
   objective** (O10, 3 September).
2. **There is no per-call cost.** The objective is provisioning cost only. This was open
   question O1 and it is closed — reopening it changes the objective everywhere.
3. **(C2) is the constraint that couples tasks to each other.** (C1) is per-task and (C3) is a
   single global line. (C2) is why this problem is hard, and it is the answer to "which
   constraint couples workflows?" — a question every team member is expected to answer
   unprompted.

---

## 6. Why it is hard — the example that teaches it

This fixture is three tasks and two profiles, small enough to solve by hand, and it is checked
by tests. `poc/instances/fixtures/adversarial_3t2p.py`.

```
Profiles                                   Tasks
  m1: thr=10 gpu=1 price=100 rel=0.99        t1: load=8  needs rel≥0.90  → {m1, m2}
  m2: thr=25 gpu=2 price=180 rel=0.95        t2: load=6  needs rel≥0.90  → {m1, m2}
                                             t3: load=9  needs rel≥0.98  → {m1} only
Budget B = 4
```

By exhaustion, the optimum is **280**: send `t1` and `t2` to `m2`, `t3` to `m1`.

Greedy construction gets **300**:

```
t1: m1 costs 100 (open one), m2 costs 180  → picks m1
t2: m1 has headroom 2 < 6, so +1 instance = 100; m2 = 180  → picks m1
t3: m1 has headroom 6 < 9, so +1 instance = 100; m2 ineligible  → m1
```

Each individual choice is correct and the total is wrong. `t1` and `t2` are each cheaper alone
on `m1`, but **together** they fit in one `m2` instance with room to spare.

And it is robust — verified exhaustively:

- **All six orderings** of the tasks give 300. Multi-start does not help.
- **Moving one task at a time** never helps: relocating `t1` alone costs +180 to save 100.
  Same for `t2`. The improving move is *both together*.

That is why the fix had to be a **subset move** (`A+subset`), which finds `{t1,t2} → m2` and
recovers 280. This one fixture drove a real algorithmic decision, which is what fixtures are
for.

---

## 7. The algorithms

Five families, plus baselines. All are registered as **15 runnable conditions** in
`poc/harness/runner.py` and every result is checked against invariants I1–I5 before it leaves
a track.

| | idea | what it is for |
|---|---|---|
| **MILP** | exact solve via CBC | ground truth. Also *is* the Murakkab baseline — the formulation is their model |
| **STATIC** | no optimisation | the floor. Shows optimisation is worth doing at all |
| **Track A** | greedy construction | fast, myopic. `A+subset` adds the subset move; `A+M1` adds a feasibility lookahead |
| **Track B** | Lagrangian relaxation | produces a **lower bound**, not really an allocator. Three arms relax (C1), (C2), (C3) |
| **Track C** | LP relaxation + repair | the practical workhorse — bounded, predictable runtime (sub-35ms) |

**Invariants, asserted on every result everywhere.** These are the single highest-value piece
of test infrastructure in the repo, because all three tracks have relaxation or rounding steps
that can silently emit invalid answers:

```
I1  every task appears exactly once            I4  every routed profile is in C(t)
I2  load routed to m ≤ n[m]·thr(m) + 1e-9      I5  n[m] ≥ 1 for every profile used
I3  Σ n[m]·gpu(m) ≤ B
```

---

## 8. The four questions, and where they stand

The PoC answered these. **A negative answer is a success** — "Track B gives no
advantage" saved a semester.

| | question | current answer | last verified |
|---|---|---|---|
| **T1** | Which constraint should Track B relax, does its bound beat the LP? | **(C1).** Tighter than the LP on **53/53** instances across all three generators *wherever Track B has a feasible incumbent*. The (C2) arm is worst everywhere. (C3) collapses to the LP bound by theory | **F35, 4 Sep** — `scripts/audit_t1_arms.py`. |
| **T2** | Can greedy be defeated by aggregate coupling? | **Yes** — proven on the fixture and confirmed at scale. `A+subset` fixes it: **never worse** than plain greedy on 72 paired instances | **F32, 4 Sep** — `scripts/audit_f20_subset.py`. The fixture half is permanent; it is checked by tests |
| **T3** | Over what budget range is there interesting structure? | **Wherever price per GPU is not constant.** The budget changes the optimal cost in **24/25** heterogeneous instances against **0–4/25** where price tracks GPU count | **F33, 4 Sep** — `scripts/audit_budget_binding.py` |
| **T4** | Is Track A worth its complexity vs Track C? | **Plain greedy, no. `A+subset`, yes** — it is competitive. Track C's real virtue is *bounded* runtime, not average speed | **F29/F30/F32.** |

---

## 9. How this project treats evidence

This matters more than any single result, and it is the thing to imitate if you join.

**Three headline numbers were retracted by our own audit**, and a fourth was found later. All
failed the same way: **a ratio of two means**, which is not a typical ratio when either
distribution has a tail. "Track C is ~110× faster" was `12.283 / 0.106`; the *median* speedup
is 5×.

The rules that came out of it:

1. **Never divide two means.** Report the paired per-instance difference and its interval.
2. **A paired interval that crosses zero means the effect is not established.**
3. **Check `poc_findings_summary.md`'s "numbers that were corrected" table before quoting any
   number.** Treat a bare `N×` claim with no interval as unverified.
4. **The audit is not a one-time pass.** Anything merged from a branch is unaudited whatever
   its finding number.
5. **Before reporting a pooled difference, ask what would make an instance behave differently,
   and split on it.** This caught two errors, one inherited and one our own.

---

## 10. Who does what

**Team members are referred to by number throughout this repo** — `035`, `075`, `077`, `083`,
`089` — the five capstone engineers. The advisor is Prof. Tossaphol.

| | Responsibility | Owns |
|---|---|---|
| **035** | Greedy construction, T2, T4, Kahn's algorithm DAG cycle check (G4) | Track A, Ingestion |
| **075** | Formulation, Lagrangian relaxation, Track C LP relaxation + repair, T1 | Track B, Track C |
| **077** | Online self-correcting ProfileStore (G2), drift detection (G6/G7), closed loop | Prototype, Profiling |
| **083** | Heterogeneous fleet generator (F31/F33), repository architecture, LogHub trace preparation | Infrastructure |
| **089** | Exact MILP baseline, static harness, G9 closed-loop benchmark evaluation harness | Evaluation, Harness |

---

## 11. What actually exists right now

**As of Architecture v5** — and every one of these is a command, not a claim:

| | | check it |
|---|---|---|
| **721** tests pass, 4 skip | across `poc/tests/` and `prototype/tests/` | `python -m pytest poc/tests/ prototype/tests/ -q` |
| **35** findings recorded | including superseded ones | `grep -c "^## F" docs/evidence/poc_findings.md` |
| **15** runnable conditions | static harness | `python -c "from poc.harness.runner import STRATEGIES; print(len(STRATEGIES))"` |
| **3** instance generators | uniform, structured, heterogeneous | `ls poc/instances/*generator*.py` |
| **1** closed-loop benchmark runner | multi-epoch drift simulation (G9) | `python -m poc.harness.closed_loop_runner` |
| **1** concrete DAG execution engine | real ZooKeeper incident parsing (G3/G4) | `python -m prototype.pipeline_mockup` |

**Built and measured:** the MCFL formulation, exact MILP validated against ground truth,
three families of fast heuristic with valid bounds, the provisioning state, the invariant
checker, three generators, the static evaluation harness, the G9 multi-epoch closed-loop
benchmark harness, the concrete DAG topological engine, online self-correcting profiles with
4-tier damping, and the full J1–J10 mockup pipeline.

---

## 12. Future Work & Roadmap

With concrete execution (`prototype/engine.py`), online profiling (`prototype/profiling.py` G2),
and the formal closed-loop evaluation harness (`poc/harness/closed_loop_runner.py` G9) completed
and verified in Architecture v5, remaining future work focuses on:

1. **Distributed Multi-Agent Cluster Scaling:** Deploying across physical multi-node server clusters with real-time network latency variations.
2. **Hardware Orchestration Daemon:** Operating system daemon managing automated GPU device isolation, dynamic power caps, and live thermal telemetry.
3. **Continuous Bayesian Hyperparameter Tuning:** Automated tuning of EMA decay rates and confidence-bound parameters under arbitrary workload distributions.

---

## 13. Where to look next

**Read in this order if you want the full picture:**

| # | document | what you get |
|---|---|---|
| 1 | this file | the whole thing at low resolution |
| 1b | [`REPO_GUIDE.md`](REPO_GUIDE.md) | **every file in the repository**, explained one by one, with reading paths |
| 2 | [`poc_findings_summary.md`](evidence/poc_findings_summary.md) | what we believe now, at what confidence, plus the corrections table |
| 3 | [`proposal_narrative.md`](proposal/proposal_narrative.md) | why the findings form one argument |
| 4 | [`design/System_Architecture_v5.md`](design/System_Architecture_v5.md) | the active design of record |
| 5 | [`evidence/poc_findings.md`](evidence/poc_findings.md) | all 35 findings in order, including retracted ones |

**The code, in the order it was built:**

```
poc/formulation/types.py        the data model
poc/formulation/invariants.py   I1-I5, called everywhere
poc/instances/                  generators + the hand-verified fixture
poc/tracks/exact_milp.py        ground truth — returns 280 on the fixture
poc/core/provisioning.py        THE central component
poc/core/decision_rule.py       shared routing rule
poc/tracks/track_c_lp.py        LP relaxation + repair (sub-35ms)
poc/tracks/track_b_lagr.py      Lagrangian bound
poc/tracks/track_a_greedy.py    greedy — returns 300 on the fixture
poc/harness/runner.py           matched-condition runner + metrics
poc/harness/closed_loop_runner.py  G9 formal closed-loop evaluation harness
prototype/engine.py             concrete DAG topological engine (LogHub)
prototype/profiling.py          online self-correcting ProfileStore (G2)
prototype/pipeline_mockup.py    full J1–J10 pipeline mockup
```

**Run it:**

```bash
python -m prototype.pipeline_mockup     # full J1-J10 mockup pipeline
python -m poc.harness.runner            # all 15 conditions static sweep
python -m pytest poc/tests/ prototype/tests/ -q  # 721 pass, 4 skip
```

---

## 14. Glossary

| term | meaning |
|---|---|
| **profile** | a deployable `(model, hardware, batch config)` with measured throughput, price, reliability, latency |
| **routing** / `x` | which profile serves each task |
| **provisioning** / `n` | how many instances of each profile are paid for |
| **`C(t)`** | a task's candidate list — profiles passing its reliability and latency floors |
| **aggregate coupling** | capacity is bought in whole instances, so a task's marginal cost depends on decisions not yet made. The core difficulty |
| **bound / bound gap** | a lower bound on the true optimum, and how far below it sits. Tracks B and C produce them |
| **condition** | one runnable allocator configuration in the harness. There are 15 |
| **paired difference** | same instance, two methods, difference per instance. The correct statistic here |
| **T0 / D1** | the 8 September session where the team ratified the formulation |
| **M1** | the 30 September milestone — proposal and presentation |
