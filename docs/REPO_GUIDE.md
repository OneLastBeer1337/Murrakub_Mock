# Repository guide — every file, explained

**What this is.** A file-by-file map of the whole repository. If you have just been handed
this repo and do not know what any of it is, read
[`ORIENTATION.md`](ORIENTATION.md) first for *what the project is*, then use this for *where
things are*.

Every file is listed. Nothing is hidden in an "etc."

---

## The 60-second map

```
EnterpriseOrches/
├── docs/           what we know, decided, measured and are writing   ← start here
├── poc/            the mathematical formulation, solver tracks, and G9 benchmark harness
├── prototype/      the concrete DAG engine and event-driven adaptive closed loop
├── scripts/        one-off audits and table generators, each reproducing a finding
├── data/           input batches for the multi-workflow experiments and LogHub traces
└── *.md            project-level state: plan, handoff, guardrails
```

**Active Design of Record:** [`docs/design/System_Architecture_v5.md`](design/System_Architecture_v5.md).  
**Test Baseline:** 721 passed, 4 skipped across `poc/tests/` and `prototype/tests/`.

---

## Root — project state

These are the files that say *where the project is*, as opposed to how it works.

| File | Lines | What it is |
|---|---|---|
| **`README.md`** | — | Front door. System mission, MCFL formulation, Invariants I1–I5, Novelty Boundary O12/F24, quickstart CLI commands, and repository map |
| **`CLAUDE.md`** | 255 | **The guardrails.** Working summary, the ground-truth fixture, the build order, the invariants, the scope guard ("do not build") and the settled decisions that must not be reintroduced. **Read before changing code** |
| **`PLAN.md`** | 192 | Eight steps from today to the M1 presentation on 30 Sep. No options, no parallel tracks. Also holds the Semester 2 parked list |
| **`HANDOFF.md`** | 206 | State and decisions already taken, the open-question table, and the **do-not-quote** list. What you would read to take over the project |
| **`PROGRESS.md`** | 190 | Milestone tracking and deliverable status. `mickie`-origin, more formal in tone |
| **`BRANCHES.md`** | 136 | **Read before merging anything.** How the two branches diverged and what reconciling them costs |
| `requirements.txt` | 13 | `pulp`, `numpy`, `pytest`. CBC ships with PuLP |
| `pytest.ini` | 5 | Test discovery config |
| `.gitignore` | 20 | Git ignore configuration |

---

## `docs/` — grouped by what you are trying to do

### Top level

| File | Lines | What it is |
|---|---|---|
| **`ORIENTATION.md`** | — | **Start here if you are new.** The whole project in one file — problem, design, formal model, the fixture, findings, evidence discipline, open items. Assumes nothing |
| `README.md` | — | Documentation index. Find your row |
| `REPO_GUIDE.md` | — | This file |

### `docs/design/` — how the system is built

| File | Lines | What it is |
|---|---|---|
| **`System_Architecture_v5.md`** | 794 | **The active design of record (ratified September 2026).** Documents online self-correcting throughput/price profiling (G2) with 4-tier damping, formal closed-loop evaluation harness (G9), concrete DAG topological engine, and grounds the adaptive closed loop novelty (O12 / F24). |
| `System_Architecture_v4.md` | 569 | **Design predecessor (ratified 7 Sep 2026).** Recreated the Murakkab (OSDI '26) capacity model within scope, specified the two-tier execution testbed, and closed initial definitions for G1–G10. |
| `System_Architecture_v2.md` | 908 | **Foundational design predecessor.** The original formulation ratified at T0; establishes the facility location problem class, tracks A/B/C, and 9 empirical amendments. |
| `System_Architecture_v3.md` | 457 | *Superseded / Withdrawn.* Proposed an API-rate-limit pivot that departed from the Murakkab capacity model; retracted following 7 Sep consultation. |
| `component_reference.md` | 351 | What each component *does*, what it must *become*, and whether it earns its place. Written as behaves / does / fits / becomes |
| `pipeline.md` | 289 | ASCII diagrams of the end-to-end PoC pipeline — instance construction, invariant gating, track execution, metric aggregation |
| `component_gaps.md` | — | Architectural gap resolution registry (G1–G10), detailing how every gap was resolved in v4 and v5 with code references and verification suites. |

### `docs/evidence/` — what we actually measured

| File | Lines | What it is |
|---|---|---|
| **`poc_findings_summary.md`** | 230 | **What we believe now, at what confidence** — plus the *"numbers that were corrected"* table. **Check this before quoting any number anywhere** |
| `poc_findings.md` | 2299 | The full chronological log, 35 findings **including superseded ones**. History is kept deliberately: F14 was corrected by F15 then F16, F16's speedup by F29, F34's headline by F35. Do not quote from it without checking the summary first |
| `chapter3_benchmark_results.md` | 143 | Scale benchmark tables and their LaTeX, ready for Chapter 3. Its §1 summary was corrected by F32 |

### `docs/proposal/` — what we are writing

| File | Lines | What it is |
|---|---|---|
| `proposal_narrative.md` | 161 | **The argument chain** that makes the findings one story, and §6's running order for Chapter 3 — *the loop leads, the optimizer serves it* |
| `D11_poc_report.md` | 227 | The PoC report for the advisor: four answers, the differentiator, limitations |
| `PoC_and_Validation_Plan.md` | 374 | September's scope, deliverables D1–D12 with owners and dates (§5.2), ownership (§5.5), risks |
| `M1_Proposal_Presentation_Slides.md` | 217 | Slide-by-slide with speaker scripts. **Check every figure against the corrections table first** |

### `docs/sessions/` — what we run with people

| File | Lines | What it is |
|---|---|---|
| **`T0_briefing.md`** | 156 | **How to run the 8 Sep session.** Confirm-or-object, a default for every item, the sign-off template |
| `T0_Formulation_Ratification_Briefing.md` | 134 | The **formal model** being ratified — the mathematics and the problem classification. Read this for *what*; read the above to *run the meeting* |
| `study_guide.md` | 238 | Preparing to be questioned. Things to **run and predict**, not to read. Step 9 rehearses the hard questions |

### `docs/presentation/`

| File | Lines | What it is |
|---|---|---|
| `T0_full_deck.html` | 1780 | Self-contained 30-slide deck, no dependencies — open in a browser. Covers problem → design → PoC → findings → the T0 decisions. `←`/`→` navigate, `N` speaker notes, `D` dark mode, `Ctrl+P` prints with notes |

### `docs/research_papers/` — literature tracking, feeds Chapter 2

| File | What it is |
|---|---|
| `papers.json` | The reference database. **The source of truth for every citation** |
| `relationship_report.md` | Generated prose report on how the papers relate to each other and to us |
| `relationship_map.mmd` | Mermaid diagram of the same |
| `HOW_TO_ADD_A_PAPER.md` | The process. Read before touching `papers.json` |
| `NEW_PAPER_TEMPLATE.json` | Skeleton entry |
| `build_report.py` | Regenerates `relationship_report.md` from `papers.json` |
| `generate_diagram.py` | Regenerates the Mermaid map |
| `integrity_check.py` | Validates `papers.json` structure |
| `check_no_shrinkage.py` | Guards against a paper silently losing content on edit |
| `growth_log.json` | Append-only record of how the database grew |
| `snapshots/*.json` | 14 before/after snapshots taken around each paper addition (P1, P6–P12). Evidence that no entry was lost or quietly rewritten |

### `docs/v1_superseded/` — the retired v1 design

Not current. Its `README.md` says what replaced what and why. Kept because v1's errors are
instructive — notably the **slot ledger** it modelled, which v2's `ProvisioningState` replaced.

| File | What it is |
|---|---|
| `README.md` | What was superseded, and why |
| `ARCHITECTURE.md` | The v1 design, 532 lines |
| `SCHEDULE.md` | The v1 schedule |
| `offline_baselines/` | v1's standalone MILP baselines — `milp_baseline.py`, `scenario2_order_sensitivity.py`, plus a README |

---

## `poc/` — the mathematical formulation & solvers

`poc/README.md` (51 lines) is the package's own entry note.

### `poc/formulation/` — the problem, as data and as assertions

> *No algorithms live here.*

| File | Lines | What it is |
|---|---|---|
| `types.py` | 142 | **The data model.** `Task`, `ProfileSpec`, `AllocationResult`, `Infeasible`, `AdmitCost`, `Observation`. Also where **O1 is resolved as "no"** — there is no `varcost` field, so the objective is provisioning cost only |
| **`invariants.py`** | 86 | **I1–I5, asserted on every allocation result in every test.** The single highest-value piece of test infrastructure in the repo — all three tracks have relaxation or rounding steps that can silently emit invalid answers |
| `__init__.py` | 5 | Package exports |

### `poc/core/` — what every track shares

| File | Lines | What it is |
|---|---|---|
| **`provisioning.py`** | 141 | **`ProvisioningState` — the centre of the design.** Owns `n[m]`, load per profile, GPUs used. `cost_to_admit()` returns `extra_instances = 0` when headroom already covers the task — **that state-dependence *is* the aggregate-coupling problem.** Get this wrong and every number is wrong |
| `decision_rule.py` | 52 | `select_profile` — the one inner rule all three tracks call (**principle P4**). The `cost_adjust` argument is the only thing that differs between tracks |
| `consolidation.py` | 196 | The multi-move neighbourhood: relocate every task on one profile together. Also holds `consolidate_subsets` (k ≤ 2), which is what recovers the fixture's optimum |
| `relocate.py` | 63 | Single-move relocate — move one task, keep strict improvements. **Provably insufficient on the fixture**, which is why it exists as its own condition |

### `poc/instances/` — the problems we solve

| File | Lines | What it is |
|---|---|---|
| `generator.py` | 174 | The **uniform** generator. `price = gpus × U(80,120)`. Also holds the shared budget anchor `_reference_gpus` and the pool builder |
| `structured_generator.py` | 158 | The **structured** generator — deliberately opposite structure: sublinear throughput, GPU tiers, lognormal loads, clustered floors |
| `heterogeneous_generator.py` | 219 | The **heterogeneous** generator — a local, owned, mixed fleet where price per GPU varies by hardware class. **Built to close F31**, and it reversed T3's answer |
| `fixtures/adversarial_3t2p.py` | 94 | **The ground truth.** 3 tasks, 2 profiles, B = 4, optimum **280**, greedy **300**. Hand-verified by exhaustion. Every track is tested against it |

### `poc/tracks/` — the allocators

The exact solver was built **before any heuristic**, deliberately.

| File | Lines | Condition | What it is |
|---|---|---|---|
| `exact_milp.py` | 184 | `MILP` | Direct MILP encoding in PuLP with CBC. **Ground truth — returns 280 on the fixture.** Also *is* the Murakkab baseline, since §1 is their model |
| `static_baseline.py` | 98 | `STATIC` | The no-optimisation floor. Shows optimisation is worth doing at all |
| `track_a_greedy.py` | 98 | `A` | Plain greedy. **Returns 300 on the fixture — which is the point**, and is an asserted test |
| `track_a_m1.py` | 143 | `A+M1` | Greedy + feasibility lookahead (the M1 analogue) |
| `track_a_relocate.py` | 47 | `A+rel` | Greedy + one relocate pass |
| `track_a_subset.py` | 59 | `A+subset` | Greedy + subset consolidation. **Recovers 280** |
| `track_a_m1_subset.py` | 55 | `A+M1+subset` | Both refinements together |
| `track_b_lagr.py` | 347 | `B` | **Lagrangian relaxation of (C1)** with subgradient updates. The shipped arm — the bound is the whole point |
| `track_b_cold.py` | 35 | `B-cold` | Track B with **no warm start**, so any "B beats A" claim can be read off an independent comparison |
| `track_b_c3.py` | 184 | `B-C3` | Relaxation of the **budget** constraint (C3), via bisection on a scalar μ |
| `track_b_budget.py` | 165 | `B-C3-alt` | An independent implementation of the same arm, kept so the alternative is reproducible rather than asserted |
| `track_b_capacity.py` | 176 | `B-C2` | Relaxation of the **capacity** constraint (C2). T1's third arm — worst of the three everywhere |
| `track_c_lp.py` | 227 | `C` | **LP relaxation + rounding + repair.** The practical workhorse — bounded, predictable runtime (sub-35ms) |
| `track_c_consolidate.py` | 59 | `C+cons` | Track C + the consolidation pass |
| `track_c_multi.py` | 40 | `C2` | Track C given every realisation order |

### `poc/harness/` — measurement & evaluation

| File | Lines | What it is |
|---|---|---|
| **`runner.py`** | 250 | Runs **all 15 conditions under matched inputs** — every condition gets the *identical instance object*, which is what makes comparison legitimate. Holds the condition registry and the `UNAVAILABLE` map. `python -m poc.harness.runner` |
| **`closed_loop_runner.py`** | 918 | **G9 Formal Closed-Loop Benchmark Evaluation Harness.** Simulates multi-epoch execution under dynamic physical runtime drift (thermal throttling, workload surges, network jitter); compares Static Murakkab Baseline vs Event-Driven Adaptive Closed Loop; outputs formatted ASCII comparison tables and RFC 7159 / Draft-07 JSON reports |
| `metrics.py` | 121 | Cost, runtime, bound, gap, feasibility. `gap_to_optimum`, `bound_gap`, `summarise`, `solvability` |

### `poc/tests/` — 15 test modules (part of 721 passing, 4 skipped across repo)

| File | Lines | What it covers |
|---|---|---|
| `test_provisioning.py` | 183 | Admit sequences, headroom arithmetic, budget rejection, snapshot/restore |
| `test_invariants.py` | 105 | `invariants.check()` against hand-built valid *and violating* results |
| `test_adversarial.py` | 126 | The fixture — including that greedy really does return 300, and that all six orderings do |
| `test_closed_loop_harness.py` | 350 | G9 benchmark runner unit tests (multi-epoch drift, configuration, ASCII table, JSON Draft-07 schema compliance) |
| `test_closed_loop_adversarial.py` | 258 | G9 adversarial stress tests (F24 replication, multi-vector drift combinations, sub-2 round MTTR) |
| `test_tracks_small.py` | 239 | Every track against the exact optimum **by exhaustion**, on instances small enough to enumerate |
| `test_track_b.py` | 327 | The bound is the point, so the bound is the test. `bound ≤ optimum` is a disqualifying-if-broken property |
| `test_harness.py` | 225 | Reproduces a known result end to end under matched inputs |
| `test_decision_rule.py` | 87 | Known pools, hand-computed answers, all-infeasible returns `None` |
| `test_consolidation.py` | 111 | The multi-move pass |
| `test_cpu_profiles.py` | 92 | CPU profiles with 0 GPUs and ZeroDivisionError protection |
| `test_generator.py` | 94 | Well-formed instances, every `C(t)` non-empty, reproducible from seed |
| `test_structured_generator.py` | 111 | Same contract, *and* assertions that it is genuinely different |
| `test_heterogeneous_generator.py` | 152 | Same, plus **corr(price, gpus) asserted in both directions** — near zero here, near one there |

---

## `prototype/` — the adaptive closed loop & concrete execution engine

`prototype/` implements the tangible manifestation of the platform's core novelty (O12 / F24). It closes the feedback loop around Murakkab's static formulation, realizing Principle P6 (*"profiles are measured, not declared"*) and executing concrete DAGs.

| File | Lines | Job | What it is |
|---|---|---|---|
| **`engine.py`** | 346 | J5/J6 | **Concrete DAG topological execution engine.** Dispatches real ZooKeeper LogHub records across 4 task types (parsing, classification, enrichment, reporting), validates acyclicity via Kahn's algorithm (G4), and emits load-scaled observations (G3) |
| **`pipeline_mockup.py`** | 249 | J1–J10 | **Full end-to-end pipeline mockup.** Demonstrates the complete lifecycle: batch ingestion -> Track C allocation -> execution -> drift injection -> parameter cliff detection -> automated re-optimization -> restored SLA execution |
| `loop.py` | 184 | — | **The closed loop controller**: J1 → J2 → J3 → J4 → J5 → J6 → J7 → J8 → J9 → J3 … |
| `ingestion.py` | 119 | J1 | Ingests batch manifests, validates DAG acyclicity via Kahn's algorithm (G4), scales demand by input log lines (G1), and freezes batch tasks |
| `registry.py` | 95 | J2 | Executor Registry + Eligibility Resolver — builds candidate pools `C(t)` using optimistic UCB reliability floors (G10) |
| `profiling.py` | 424 | J7/J8 | **Online self-correcting ProfileStore (G2)** with dual-input rate estimation, 4-tier damping architecture, thermodynamic efficiency tracking ($\eta$), and **Two-Tier DriftDetector (G6/G7)** with instant parameter cliff checking |
| `reoptimisation.py` | 129 | J9 | Global and scoped re-optimization subroutines (`reoptimise_global()`) wired to the runtime loop (G8) |
| `simulator.py` | 121 | J5/J6 | Synthetic workflow telemetry simulator (alternative to concrete engine) |

### `prototype/tests/` — 8 test modules (part of 721 passing, 4 skipped across repo)

| File | Lines | What it covers |
|---|---|---|
| `tests/test_engine.py` | 245 | Concrete DAG topological execution engine, Kahn's cycle check (G4), load-scaled observation emission (G3), and LogHub trace processing |
| `tests/test_profiling_v5.py` | 589 | Architecture v5 G2 self-correcting profiling suite (dual-input rates, 4-tier damping, Kalman EMA, thermodynamic efficiency) |
| `tests/test_profiling_stress.py` | 511 | Chaos fuzzing, multithreaded snapshot isolation, rapid oscillation damping, transient GC pause spikes |
| `tests/test_loop.py` | 227 | End-to-end closed loop adaptation, versioning, anti-thrashing |
| `tests/test_profiling.py` | 186 | Core ProfileStore, Beta-Binomial reliability estimation, EMA latency |
| `tests/test_registry.py` | 69 | Registry type filtering and candidate pool resolution C(t) |
| `tests/test_reoptimisation.py` | 167 | Global vs scoped re-optimization scoping tests (O9 / F18) |

---

## `scripts/` — each one reproduces a finding

Every script here exists so a claim can be re-derived from scratch rather than trusted.

| File | Lines | Reproduces |
|---|---|---|
| `audit_budget_binding.py` | 134 | **T3 / F33.** Holds tasks and profiles fixed, varies *only* B, and asks whether the optimum moves. 0–4/25 vs **24/25** |
| `audit_t1_arms.py` | 155 | **T1 / F34–F35.** All three relaxation arms against the LP bound, paired, with bootstrap intervals |
| `audit_f20_subset.py` | 172 | **T2 / F32.** The paired audit that retired the "twenty-fold improvement" claim |
| `generate_chapter3_tables.py` | 157 | The Chapter 3 scale benchmark tables and their LaTeX |
| `prepare_multiworkflow_batch.py` | 134 | Turns real Zookeeper LogHub data into a concrete multi-workflow batch |

---

## `data/`

| File | Lines | What it is |
|---|---|---|
| `eval_batches/eval_batch_3workflows.json` | 3430 | The prepared multi-workflow evaluation batch from ZooKeeper LogHub |
| `linux_sample.log` | — | Raw Linux system log trace sample |
| `spark_sample.log` | — | Raw Apache Spark execution log sample |
| `zookeeper_sample.log` | — | Raw Apache ZooKeeper consensus log sample |

---

## Reading paths

**"I have one hour and know nothing."**  
`docs/ORIENTATION.md` → `docs/evidence/poc_findings_summary.md`. Done.

**"I need to understand the architecture and Design of Record."**  
[`docs/design/System_Architecture_v5.md`](design/System_Architecture_v5.md) → [`README.md`](../README.md).

**"I need to understand the maths."**  
[`docs/design/System_Architecture_v5.md`](design/System_Architecture_v5.md) §2 → `poc/formulation/types.py` → `poc/instances/fixtures/adversarial_3t2p.py`.

**"I need to understand why it is hard."**  
The fixture, then `poc/core/provisioning.py` — specifically `cost_to_admit()`.

**"I am going to change an algorithm."**  
`CLAUDE.md` first (the scope guard and settled decisions), then `docs/design/component_reference.md`, then the track. **Run `python -m pytest poc/tests/ prototype/tests/ -q` before and after** — I1–I5 will catch most mistakes immediately.

**"I need to check whether a number is safe to quote."**  
`docs/evidence/poc_findings_summary.md`, the *"numbers that were corrected"* table. Always.

**"I am presenting."**  
`docs/presentation/T0_full_deck.html` → `docs/sessions/study_guide.md` step 9.

---

## Where to make a change

| If you want to… | Touch | And check |
|---|---|---|
| Change the objective or a constraint | `poc/tracks/exact_milp.py` **and every track** | This is expensive. See O1 in `CLAUDE.md` first |
| Add an allocator | a new `poc/tracks/*.py` + register it in `harness/runner.py` | It must return `AllocationResult` and pass I1–I5 |
| Add an instance family | a new `poc/instances/*_generator.py` | Mirror `test_heterogeneous_generator.py` — assert it is *different*, not just valid |
| Change how capacity is counted | `poc/core/provisioning.py` | Everything. This is the centre |
| Update profile calibration | `prototype/profiling.py` | Check 4-tier damping and run `test_profiling_v5.py` |
| Modify benchmark drift scenarios | `poc/harness/closed_loop_runner.py` | Run `test_closed_loop_harness.py` |
| Add a finding | append to `docs/evidence/poc_findings.md`, then update `poc_findings_summary.md` | The log is chronological — **append, never rewrite history** |
| Fix a retracted number | `poc_findings_summary.md` corrections table, then sweep every document | `PLAN.md` step 3 is exactly this task |

---

## Two conventions that are easy to violate by accident

1. **`docs/evidence/poc_findings.md` is append-only history.** Findings that were later
   corrected stay as they were written; the correction is a *new* finding that supersedes
   them. The summary states the current position. Rewriting the log destroys the audit trail
   that is this project's strongest asset.

2. **Never divide two means.** Report the paired per-instance difference and its interval.
   Four headline numbers were retracted for exactly this. If you are about to write `N×`,
   stop and compute the paired statistic instead.
