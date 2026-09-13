> **SUPERSEDED — v1.** Not current. See `docs/v1_superseded/README.md` for what
> replaced this and why. Do not build from it.

---

# Project Schedule — Execution Plan

Companion to `Architecture_Design.md` (the *what and why*) — this document is the *when and
in what order*. Week numbers are relative (Week 1 = whenever the team actually starts);
anchor to real calendar dates once a start date is fixed.

> **Per the most recent advisor consultation, this schedule reflects a real pivot:**
> multi-workflow optimization (HEFT + Lagrangian relaxation, offline scope) is now the
> primary focus, replacing the earlier single-workflow allocator design. Structural
> DAG-shape optimization (Palimpzest-derived) is removed from this schedule entirely, not
> paused — see `Architecture_Design.md`'s Development Priority section for the full
> reasoning. Task_Management.xlsx is the up-to-date, task-level source; this document gives
> the stage-level narrative.

Each stage lists **what we have to get** — the concrete deliverable that proves the stage is
actually done, not just "worked on."

![Schedule overview](images/schedule_gantt.png)

*(Note: the Gantt image above predates this update and still shows the earlier
single-workflow staging — regenerate before relying on it visually. The stage descriptions
below are current.)*

---

## Stage 1 — Development: Foundations (Weeks 1–3)

Shared infrastructure every later stage depends on.

| Week | Task | What we have to get |
|---|---|---|
| 1 | Environment setup: local dev environment, Slurm cluster access confirmed | A working dev environment every team member can run |
| 1–2 | Profiled-data schema: cost/latency/reliability/GPU slots, per (task_type, candidate) | A written schema referenced by everything built afterward |
| 2 | Executor registry — data model + manual registration workflow, Murakkab's 3-field schema | A registry that can store multiple candidates per task-type, populated by hand |
| 2–3 | **Shared resource ledger** — one ledger across ALL workflows, not per-instance | Ledger data structure supports the multi-workflow scope from the start |
| 2–3 | Fault-injection harness skeleton (OS-log domain) | Scripts that inject a fault and produce a log stream with a known correct outcome |

**Stage 1 exit criterion:** the shared ledger, registry, and fault-injection harness all
exist and can be exercised manually, before any optimizer logic is built on top of them.

---

## Stage 2 — Development: Phase A — Layer 1 Eligibility Lookup (Weeks 3–5)

Structural DAG-shape optimization has been **removed from scope entirely** (not paused) —
see `Architecture_Design.md` Development Priority. This stage is correspondingly lighter
than earlier versions of this schedule, and the freed capacity is redirected to Stage 3.

| Week | Task | What we have to get |
|---|---|---|
| 3–4 | DAG ingestion: parse a **batch** of incoming JSON DAGs (offline — fixed before optimization starts) | Can load multiple worked-example DAGs from a batch file |
| 4–5 | **Layer 1: eligibility lookup** — `task_type -> candidate pool`, exact match | Given a task, returns exactly its registered eligible candidates — now an explicit, named step per advisor feedback |

**Stage 2 exit criterion:** Layer 1 correctly returns the eligible pool for every task in a
multi-workflow batch, and hands that pool — not a pre-selected winner — to Phase B.

---

## Stage 3 — Development: Phase B — Multi-Workflow Optimizer (Weeks 4–9, overlaps Stage 2)

> **Primary active focus.** This is the core rebuild. Treat the week ranges below as a
> floor, not a ceiling — this stage absorbs the capacity freed by Stage 2's reduction.

| Week | Task | What we have to get |
|---|---|---|
| 4–5 | Feasibility filter (reliability + latency floors) against the **shared** ledger | Filter correctly checks shared, not per-instance, capacity |
| 5 | Inner decision rule (argmin-cost among survivors), packaged as a **reusable** per-workflow/per-task solver | Callable independently — this becomes the shared building block both tracks below call into |
| 5–6 | **Track A — HEFT (multi-workflow):** rank computation per task, per workflow, from real profiled cost | `rank(t)` matches the recursive critical-path formula |
| 6–7 | **Track A — HEFT:** cross-workflow interleaving policy (fairness-aware, per Zhao & Sakellariou's multi-DAG extension) | Multiple workflows' ranked lists combine into one global priority order |
| 7 | **Track A — HEFT:** assignment walk against the shared pool, reusing the inner decision rule | Walks the combined list once, assigns using the shared solver |
| 7–8 | **Track B — Lagrangian relaxation:** formulate the shared-capacity constraint as a penalty (lambda) | Objective correctly includes the lambda-weighted penalty term |
| 8 | **Track B:** decompose into N per-workflow subproblems, reusing the same inner solver | Each workflow's subproblem solved independently |
| 8–9 | **Track B:** multiplier update loop (subgradient step, convergence check) | Lambda updates correctly; loop terminates; **proven lower bound reported alongside the result** |

**Stage 3 exit criterion:** both tracks run end-to-end on the same multi-workflow batch and
produce valid assignments; Lagrangian relaxation additionally reports a real optimality-gap
bound.

---

## Stage 4 — Development: Phase C (Weeks 8–11, overlaps Stage 3's tail)

| Week | Task | What we have to get |
|---|---|---|
| 8–9 | Measurement: transport-layer interception, call-context attribution | Every call captured with (task, candidate, latency, cost, success) |
| 9 | EMA profile update (Task-Candidate Profile — the first of three profiled things) | Repeated runs visibly move the profiled estimate |
| 9–10 | Compatibility score + drift trigger, wired to **Phase B re-run only** (no structure left to reconsider) | Feeding in the 50-run reliability-drop scenario fires a real Phase B re-run |
| 10 | Structured logging (drift-event log schema) | A drift event produces a log entry matching the documented field structure |
| 10–11 | Staged re-check cadence (governs how often Phase B re-runs) | Interval widens on clean checks, resets on any threshold crossing |
| 11 | **New:** Workflow Arrival/Demand profiling — data model + trend projection (Conditional) | New tracking structure exists; only pursued if capacity allows — see note below |

**Note on the new profiling item:** this is genuinely new infrastructure, not a rename of
something already built — see `Architecture_Design.md` §4.4. It is not required for either
optimizer track to function; it only becomes relevant if a future capacity-split policy needs
to weight workflows by demand. Marked Conditional in `Task_Management.xlsx`.

**Stage 4 exit criterion:** the full drift-detection loop reproduces the documented worked
example, correctly re-invoking Phase B and only Phase B.

---

## Stage 5 — Prototype: Integration (Weeks 11–13)

| Week | Task | What we have to get |
|---|---|---|
| 11–12 | Wire Layer 1 + Phase B (both tracks) + Phase C + Registry into one pipeline | A batch of workflows -> Layer 1 -> allocate (either track) -> execute -> profile update, no manual steps |
| 12 | Wire Phase C's drift trigger back to a real Phase B re-run | A drift event automatically triggers a real re-allocation, not just a logged intention |
| 12–13 | End-to-end demo — OS-log domain, **multiple concurrent workflow instances** | A live, observable run showing genuine shared-pool contention across workflows, not just one instance in isolation |

**Stage 5 exit criterion:** a live demo with at least two concurrent workflow instances,
both drawing from the same shared ledger, both correctly allocated without double-booking
capacity.

---

## Stage 6 — Testing: Local (Weeks 13–17)

| Week | Task | What we have to get |
|---|---|---|
| 13–14 | Unit tests — registry, Layer 1, shared ledger, both optimizer tracks, profile store | Component-level coverage in place |
| 14–15 | Regression tests — all worked examples from `Architecture_Design.md` | CI fails loudly if any algorithm drifts from documented examples |
| 15–17 | Local/Slurm scale-up testing — **multiple concurrent workflows, genuine shared-pool contention** | System stable under real multi-workflow load, not just single-instance load |

**Stage 6 exit criterion:** full test suite green, system demonstrably stable when several
workflows genuinely compete for the same limited capacity.

---

## Stage 7 — Testing: Cloud (Weeks 17–20)

> **Conditional — opportunistic, not required.** Unchanged from the prior version of this
> schedule — pursue only if time/capacity allow after Stage 6 succeeds.

| Week | Task | What we have to get |
|---|---|---|
| 17–18 | GCP environment setup, deploy Registry + Profile Store | System deployable to GCP, not just local/Slurm |
| 18–19 | Re-run the full Stage 6 test suite against the cloud deployment | Parity confirmed |
| 19–20 | Cloud-specific shakeout | Any divergence explained, not just noticed |

**Stage 7 exit criterion:** same as before — if this stage doesn't happen, Stage 8 proceeds
on the local system alone.

---

## Stage 8 — Evaluation (Weeks 20–27)

This is where the project's actual empirical claim gets tested — expanded from the earlier
version of this stage to reflect the new central question: **how close do the two fast
multi-workflow methods get to true optimal, and how do they compare to Murakkab's own
exact-solve approach under matched conditions.**

| Week | Task | What we have to get |
|---|---|---|
| 20 | **Domain confirmation checkpoint** — confirm OS-log domain with Ano, or pivot | Domain status resolved before full evaluation proceeds — see `Architecture_Design.md` §5 |
| 20–21 | Baseline: static/fixed allocation | Static baseline runnable on the same multi-workflow batches |
| 21–22 | Baseline: offline MILP, **multi-workflow scope** (free solver — see `Offline MILP Baseline/`) | MILP baseline runnable on the SAME batch as HEFT/Lagrangian |
| 22 | **Fair-comparison check** — confirm any changed metric/condition is also applied to the Murakkab-equivalent baseline | Written confirmation, per the advisor's fair-comparison principle (`Architecture_Design.md` §3.5) |
| 22–23 | Evaluation methodology + statistics plan (HEFT vs. Lagrangian vs. static vs. MILP) | Written plan: baselines, metrics, statistical tests |
| 23–25 | Full evaluation matrix — repeated runs, varying multi-workflow batch composition and fault-injection scenarios | Enough repeated-run data per baseline for statistical comparison |
| 25–26 | Statistical analysis — Kruskal-Wallis, pairwise Mann-Whitney U + Cliff's delta | Significance results and effect sizes across all four methods |
| 26–27 | **Optimality-gap analysis** — HEFT's result vs. Lagrangian's proven lower bound vs. true MILP optimum | A direct, quantified answer to "how close to optimal is each fast method" — the project's central empirical question |

**Stage 8 exit criterion:** every measurement dimension has a real number behind it,
including the optimality-gap analysis that didn't exist as a concept in the earlier
single-workflow version of this plan.

---

## Stage 9 — Results & Write-up (Weeks 27–30)

*(The earlier "Second Domain: Document Processing" stage has been removed — document
processing is not active scope per the current architecture; see `Architecture_Design.md`
§5.2. If domain status changes after the Stage 8 checkpoint, this schedule would need
revisiting, not silently absorbed here.)*

| Week | Task | What we have to get |
|---|---|---|
| 27 | Compile results into report structure | Results section, every number traceable to a specific run |
| 27–28 | Write architecture/design chapter (from `Architecture_Design.md`) | Design chapter drafted, largely transcribed from the existing document |
| 28–30 | Final review + defense prep | Complete, defensible final submission |
| 30 | **FINAL PRESENTATION / PROJECT COMPLETION** | Presented — Milestone 3 complete |

---

## Schedule at a glance

| Stage | Weeks | Focus | Priority |
|---|---|---|---|
| 1. Foundations | 1–3 | Shared ledger, registry, fault-injection harness | Fixed |
| 2. Phase A — Layer 1 | 3–5 | Eligibility lookup only (structural search removed) | Fixed |
| 3. Phase B — Multi-Workflow Optimizer | 4–9 | HEFT + Lagrangian relaxation, both tracks | Primary Focus |
| 4. Phase C | 8–11 | Execution, profiling (3 kinds), drift detection | Fixed |
| 5. Integration | 11–13 | First real multi-workflow prototype | Fixed |
| 6. Local testing | 13–17 | Stability under genuine shared-pool contention | Fixed |
| 7. Cloud testing | 17–20 | GCP deployment, parity | Conditional |
| 8. Evaluation | 20–27 | Optimality-gap analysis vs. MILP, fair Murakkab comparison | Fixed |
| 9. Results & write-up | 27–30 | Final report, defense prep | Fixed |

**What changed structurally from the earlier 10-stage plan:** the old Stage 2 (Palimpzest
development) is gone; the old Stage 9 (second domain) is gone; Stage 3 (Phase B) is
substantially heavier, now the named primary focus; Stage 8 (Evaluation) gained the
optimality-gap analysis and the fair-comparison check as new, required work. Total stage
count dropped from 10 to 9, and the schedule is correspondingly shorter (~30 weeks vs. ~34),
though this has not yet been re-anchored to real calendar dates against the fixed
checkpoints (M1/M2/M3) — see the note below.

---

## What's still not filled in

- **Domain is not fully settled** — OS-log incident detection is the working candidate;
  Stage 8's Week 20 checkpoint exists specifically to resolve this with Ano before full
  evaluation proceeds.
- **HEFT's fairness-interleaving policy** — which of Zhao & Sakellariou's six candidate
  policies (or what adaptation) this project actually uses is not yet chosen.
- **Lagrangian relaxation's multiplier-update procedure** — subgradient step size and
  convergence criteria need real tuning once profiling data exists.
- **Workflow arrival/demand profiling** — not yet designed in detail; identified as
  Conditional, only necessary if a future capacity-split policy needs it.
- **This schedule's week numbers have not been re-anchored to the fixed calendar
  checkpoints** (M1 = 30 Sep 2026, M2 = 18 Dec 2026, M3 = 12 Mar 2027) since the stage count
  changed from 10 to 9. `Task_Management.xlsx` carries the actual up-to-date calendar dates
  per task; treat this document's week numbers as relative/illustrative until reconciled.
- **Drift threshold `tau` and EMA rate `alpha`** — placeholders, need real values once
  initial profiling data exists.
