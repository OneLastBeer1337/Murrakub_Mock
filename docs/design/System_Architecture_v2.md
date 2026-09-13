# System Architecture and Detailed Design — v2

**Profile-Guided Multi-Workflow Resource Orchestration Platform**

Supersedes `System_Architecture_and_Detailed_Design.md` (v1). Written to be built from.

---

## 0. Status and What Changed From v1

### 0.1 The correction

v1 modelled capacity as **consumed per task assignment** — a ledger of slots decremented each
time a task was assigned. That is wrong. Under Murakkab's model, capacity is consumed by
**provisioned instances**, and instance counts are derived from the aggregate load routed to
them.

This invalidated three sections of v1 and changed all three algorithm tracks. They are
rewritten here.

| v1 section | Status |
|---|---|
| §3.5 Shared Resource Ledger | **Replaced** by Provisioning State (§4.5) |
| §4.1 Data Model | **Replaced** (§5.1) — gains instance variables |
| §4.2.1 Shared Decision Rule | **Replaced** (§5.2.1) — marginal cost, not slot filter |
| §3.1.7 Tracks A/B/C | **Rewritten** (§4.4) for two-level structure |
| Everything else | Carried forward, largely unchanged |

### 0.2 What is new

- **§1 — the formal problem.** v1 specified algorithms against a problem it never stated. That
  gap caused every downstream error, including the HEFT mistake. §1 exists so no future
  algorithm choice can be argued from vibes.
- **§6 — implementation guide.** Repository layout, build order, module contracts, and an
  explicit scope guard, written for direct implementation.

### 0.3 Provenance tags

| Tag | Meaning |
|---|---|
| *(untagged)* | Traces to a source document or cited paper |
| **[PROPOSED]** | Invented here. Not team-agreed, not advisor-confirmed |
| **[OPEN]** | Known unresolved; resolved by a named PoC test |

### 0.4 Superseded decisions

**HEFT is not used.** Neither Murakkab's formulation nor Cheng & Nguyen's contains precedence
constraints or a makespan term. Upward rank orders tasks by a quantity absent from the
objective. Replaced by greedy construction (Track A).

**Capacity is instance-based, not task-based.** See §0.1.

---

## 1. Problem Formulation

### 1.1 Informal statement

Given a batch of workflows whose tasks must each be executed by some model configuration, and
a fixed GPU budget: decide **which configuration serves each task** and **how many instances
of each configuration to provision**, minimising total provisioning cost, such that every
instance has enough throughput for the load routed to it and the GPU budget is not exceeded.

Two decisions, coupled. Routing determines load; load determines instance counts; instance
counts consume the budget; a binding budget constrains routing.

### 1.2 Sets and indices

```text
T           tasks, across all workflows in the batch
M           model profiles — an instantiable (model, hardware tier, config) triple
C(t) ⊆ M    profiles eligible for task t, after floor filtering (§1.6)
```

A **profile** is the unit that gets provisioned. A **candidate** for a task is a profile that
is eligible for it. These are the same objects viewed from different sides.

### 1.3 Parameters

```text
load(t)     throughput demand of task t                  (requests or tokens per unit time)
thr(m)      throughput capacity of one instance of m     (same units as load)
gpu(m)      GPUs consumed by one instance of m
price(m)    cost of one instance of m over the horizon
B           total GPU budget
rel(m)      reliability of profile m                     [0,1]
lat(t,m)    latency of task t on profile m
R_min(t)    reliability floor for task t
L_max(t)    latency ceiling for task t

            R_min(t) is **the reliability the baseline would deliver for t** — not an
            arbitrary input. Advisor guidance, 3 Sep 2026: the goal is not to maximise
            reliability but to keep it as good as not using this system. Set arbitrarily
            low, the optimiser will legally trade reliability for cost: given two profiles
            both passing a 0.90 floor it correctly takes 0.910 over 0.999 and saves 200.
            Anchored to the baseline, the existing program enforces the requirement with no
            change to the objective or to (C1)-(C3). See poc_findings.md F24.
```

### 1.4 Decision variables

```text
x[t][m] ∈ {0,1}     task t routed to profile m ∈ C(t)     — level 1, routing
n[m]    ∈ Z⁺        instances of profile m provisioned    — level 2, provisioning
```

### 1.5 Objective

```text
minimize    Σ_{m ∈ M}  n[m] · price(m)
```

**[PROPOSED]** A variable per-invocation term may be added if executor pricing is
usage-based rather than purely provisioning-based:

```text
          + Σ_t Σ_m  x[t][m] · varcost(t, m)
```

**[CLOSED — 2 September 2026: no.]** The objective is provisioning cost only. This term is
not implemented and `ProfileSpec` carries no `varcost` field. Reopening it changes the
objective signature everywhere; it does not change the problem class.

### 1.6 Constraints

```text
(C1)  Σ_{m ∈ C(t)} x[t][m] = 1                                    ∀ t ∈ T
      every task is assigned exactly one profile

(C2)  Σ_{t : m ∈ C(t)} x[t][m] · load(t)  ≤  n[m] · thr(m)        ∀ m ∈ M
      provisioned throughput covers routed load

(C3)  Σ_{m ∈ M} n[m] · gpu(m)  ≤  B
      total GPUs within budget
```

**Floors are applied by construction, not as constraints:**

```text
C(t) = { m ∈ M : rel(m) ≥ R_min(t)  and  lat(t,m) ≤ L_max(t) }
```

This keeps floors out of the program, preserves the LP relaxation's validity, and matches
principle P3 (feasibility first, cost second).

**No linking constraint is needed.** If `x[t][m] = 1` and `load(t) > 0`, then (C2) forces
`n[m] ≥ 1`. An explicit `x ≤ y` linking constraint would be redundant.

### 1.7 Where the coupling lives

This is the part every algorithm has to deal with, and the reason the problem is not easy.

| Constraint | Couples | Consequence |
|---|---|---|
| **(C1)** | Profiles, through each task | A task's choice is exclusive — taking one profile forecloses others |
| **(C2)** | Tasks to instances, and **tasks to each other** across workflows sharing a profile | This is the multi-workflow interaction. Two tasks in different workflows contend only if they route to the same profile |
| **(C3)** | All profiles, through one budget | Global scarcity |

**The integrality gap lives in (C2).** `n[m]` must cover a ceiling of aggregate load over
throughput. The LP relaxation returns fractional instance counts; rounding up costs real GPUs.
This is why the LP bound is not tight and why an integer-aware method can do better.

**The aggregate-coupling problem lives in (C2) too.** A task's marginal cost depends on whether
its chosen profile already has headroom. Routing task 1 to profile X may cost a whole instance,
or nothing, depending on assignments not yet made. Track A's central difficulty.

### 1.8 Problem class

This is a **modular capacitated facility location problem with a budget constraint**:

| Facility location term | Here |
|---|---|
| Facility site | Model profile `m` |
| Opening multiple modular units at a site | `n[m]` instances |
| Customer | Task `t` |
| Assignment | `x[t][m]` |
| Facility capacity | `n[m] · thr(m)` |
| Global side constraint | GPU budget (C3) |

This identification matters for three reasons:

1. **It justifies Lagrangian relaxation properly.** Lagrangian relaxation of the assignment
   constraints is the classical solution method for capacitated facility location. Track B is
   not an arbitrary pick — it is the textbook method for this problem class.
2. **It predicts the decomposition.** Relaxing (C1) yields one subproblem per profile. This is
   the standard result and it contradicts v1's claim of per-workflow decomposition.
3. **It gives a literature to cite** beyond the two LLM-serving papers, which strengthens Ch.2.

### 1.9 What is deliberately not modelled

Recorded so the divergence from Murakkab is explicit rather than accidental:

- **No time dimension.** Steady-state provisioning over one horizon. No arrival dynamics, no
  queueing, no autoscaling.
- **No precedence.** DAG edges determine data flow at execution time but do not enter the
  optimisation, exactly as in both source papers.
- **No parallelism configuration as a decision.** TP/PP degree is baked into a profile rather
  than chosen. Murakkab and Cheng & Nguyen both decide it; this project does not.
- **No accuracy maximisation objective.** Reliability is a floor only.
- **No multi-tenancy pricing or SLO tiers.**

---

## 2. System Architecture

### 2.1 Overview

```text
System
├── Workflow Ingestion
├── Executor Registry
├── Eligibility Resolver
├── Multi-Workflow Optimizer
│     ├── Track A — Greedy Construction
│     ├── Track B — Lagrangian Relaxation
│     ├── Track C — LP Relaxation + Rounding
│     └── Shared Decision Rule
├── Provisioning State            ← replaces v1's Resource Ledger
├── Assignment Registry
├── Execution Engine
├── Profiling Subsystem
│     ├── Measurement Interceptor
│     ├── Profile Store
│     └── Drift Detector
└── Evaluation Harness
```

### 2.2 Principles

| # | Principle | Consequence |
|---|---|---|
| P1 | Offline batch, not streaming | No admission control, no mid-run rebalancing |
| P2 | Eligibility separate from selection | Resolver returns pools, never winners |
| P3 | Feasibility first, cost second | Floors filter `C(t)`; never weighted against cost |
| P4 | One decision rule, three coordination strategies | All tracks call the same inner rule |
| P5 | Tracks are swappable | One interface; none privileged |
| P6 | Profiles are measured, not declared | No hand-tuned tables |
| P7 | Re-optimisation is event-driven | Drift triggers it; no fixed clock |
| P8 | Structure immutable after ingestion | Drift re-enters the Optimizer only |
| P9 | Complete or nothing | Partial assignments are never valid output |
| P10 | Reproducible given a fixed seed | Randomised restarts are seeded, not banned |

### 2.3 Component register

| Component | Purpose |
|---|---|
| Workflow Ingestion | Parse, validate, freeze the batch |
| Executor Registry | Curated catalogue of profiles and declared task types |
| Eligibility Resolver | Build `C(t)` per task by exact type match plus floor filtering |
| Multi-Workflow Optimizer | Produce `x` and `n` |
| Provisioning State | Track instances, per-profile load, and GPU budget during a run |
| Assignment Registry | Persist versioned assignments |
| Execution Engine | Run a stored assignment |
| Profiling Subsystem | Measure, update profiles, detect drift |
| Evaluation Harness | Run all conditions under matched inputs |

### 2.4 Data flow

| Stage | Input | Output |
|---|---|---|
| 1. Ingest | Batch manifest | Frozen task graphs |
| 2. Resolve | Task types + Registry + Profile snapshot | `C(t)` per task |
| 3. Optimise | `C(t)`, profiles, budget | `x`, `n`, cost, bound |
| 4. Persist | Allocation result | Versioned assignment |
| 5. Execute | Active assignment | Results + telemetry |
| 6. Profile | Telemetry | Updated profile entries |
| 7. Detect | Updated vs stored profile | Drift signal or no-op |

---

## 3. Functional Architecture

### 3.1 Jobs

| ID | Job | Trigger | Completion |
|---|---|---|---|
| J1 | Ingest batch | Run initiated | All workflows parsed, validated, frozen |
| J2 | Resolve eligibility | J1 | Every task has non-empty `C(t)` |
| J3 | Produce allocation | J2, or J9 | `x` and `n` complete and feasible |
| J4 | Persist assignment | J3 | Stored and active |
| J5 | Execute | Requested | All tasks terminated |
| J6 | Record outcomes | Task call completes | Observation emitted |
| J7 | Update profile | J6 | Entry updated |
| J8 | Detect drift | J7 | Score computed and compared |
| J9 | Trigger re-optimisation | J8 signals | J3 re-invoked |
| J10 | Run evaluation | Experiment initiated | All conditions recorded |

### 3.2 Job dependencies

```text
J1 ──► J2 ──► J3 ──► J4
             ▲        │
             │        ▼
            J9      J5
             ▲        │
             │        ▼
            J8 ◄─ J7 ◄─ J6

J10 ──► drives J3 under fixed conditions
```

### 3.3 J3 decomposition (the one that changed)

1. Take an immutable profile snapshot
2. Initialise Provisioning State: zero instances, zero load, full budget
3. Select strategy (A, B, or C)
4. Execute the track (§5.2)
5. Verify: every task assigned; (C2) holds for every profile; (C3) holds
6. Emit `AllocationResult` containing both `x` and `n`

**[RESOLVED — O9, see `poc_findings.md` F18.]** J9 previously read "for affected workflows
only", with a note doubting whether that is well-defined under (C2). It is well-defined, and
it is **vacuous**: drift is detected on a *profile*, so the affected workflows are those
routed to it — and a shared profile is used by 84–100% of workflows even at twelve. Scoping
correctly does the same work as a global run; scoping narrower costs a mean 22% and up to 51%.

**J9 re-invokes J3 over the whole batch.** No scoping.

---

## 4. Component Architecture

### 4.1 Multi-Workflow Optimizer

**Purpose.** Produce `x` and `n` minimising Σ n[m]·price(m) subject to (C1)–(C3).

**Interface.**

```text
AllocationStrategy.allocate(
    tasks:    Task[],
    pools:    Map<TaskId, ProfileId[]>,     # C(t)
    profiles: Map<ProfileId, ProfileSpec>,
    budget:   int,
    seed:     int
) -> AllocationResult | Infeasible
```

All three tracks implement this identically (P5).

**Constraints.** Must terminate; must not mutate the profile snapshot; deterministic given
inputs and seed; complete-or-nothing output.

**Error handling.**

| Condition | Response |
|---|---|
| Empty `C(t)` for some task | Abort naming the task — registry or floors too strict |
| No feasible assignment within budget | `Infeasible` naming the binding constraint |
| Track B hits iteration cap | Return best feasible found, flagged unconverged, with bound |
| Track C repair fails | `Infeasible` — never a violating assignment |
| Verification fails in step 5 | Internal error; fail loudly — indicates a bug |

### 4.2 Eligibility Resolver

Builds `C(t)` by exact task-type match against the Registry, then filters by floors. Exact
match only — no fuzzy or semantic matching, so registry gaps surface as failures rather than
silent quality loss. Empty `C(t)` aborts the run.

### 4.3 Executor Registry

Curated catalogue of profiles: declared task type, throughput, GPU count, price, reliability,
latency. Read-only at runtime. Manually maintained per domain.

### 4.4 Provisioning State *(replaces v1's Shared Resource Ledger)*

**Purpose.** Track, during one allocation run: instances provisioned per profile, load routed
per profile, and GPUs consumed.

**This component is the correction at the heart of v2.** v1 modelled a slot pool decremented
per task. Under (C2)–(C3), a task consumes no resource directly — it adds *load*, which may or
may not force a new instance.

**Interface.**

```text
ProvisioningState:
    instances(m)        -> int              # n[m]
    load(m)             -> float            # routed load on m
    gpusUsed()          -> int              # Σ n[m]·gpu(m)
    headroom(m)         -> float            # n[m]·thr(m) − load(m)

    costToAdmit(t, m)   -> AdmitCost | Infeasible
    admit(t, m)         -> void
    release(t, m)       -> void
    snapshot()          -> StateSnapshot
    restore(snapshot)   -> void
```

```text
AdmitCost {
    extraInstances: int      # ceil shortfall / thr(m), zero if headroom suffices
    extraGpus:      int      # extraInstances · gpu(m)
    extraCost:      float    # extraInstances · price(m)
}
```

**`costToAdmit` is the most important operation in the system.** It answers "what does routing
this task here cost *right now*" — and its answer changes as other tasks are admitted. That
state-dependence is the aggregate-coupling problem, made explicit rather than hidden.

`costToAdmit` returns `Infeasible` when `extraGpus` would exceed remaining budget.

`snapshot`/`restore` exist for Track A's multi-start and Track C's rounding repair.

### 4.5 Profiling Subsystem

**Measurement Interceptor** — transport-layer interception; attributes each call to
`(workflowInstance, taskId, profileId)`; records latency, success, cost. Unattributable calls
are logged and discarded rather than mis-attributed.

**Profile Store** — sole writer of profile state. Serves immutable snapshots; an allocation
run reads exactly one snapshot so Track B's bound is meaningful. Unprofiled pairs return
`NotProfiled`, never a default.

*Update rule, amended after measurement — see `poc_findings.md` F19.* This section
previously said "EMA update per observation" for all fields. That is correct for **latency**,
a continuous quantity an EMA tracks well. It is **wrong for reliability**, which is estimated
from a binary success/failure signal: at α = 0.3 a profile at 0.99 that observes 99 successes
and then one failure reports **0.70**. Since `rel(m)` is the filter that builds `C(t)`, a
single failed call would make a profile ineligible for every task with a floor above 0.7,
collapse the pools and re-allocate the batch on the evidence of one observation.

```text
latency      EMA, as originally specified
reliability  decayed counting estimator with a weak prior:
                 rel = (decayed successes + p) / (decayed trials + 2p)
```

Recency still dominates, so genuine degradation is still detected. Note that the decay sets
the effective sample size at `1/(1 − decay)` and therefore imposes a **ceiling** on achievable
reliability of `(N + p)/(N + 2p)` — pick it so the ceiling clears the highest `R_min(t)` the
registry must serve, or those tasks become permanently unservable with no error raised.

**Drift Detector** — recomputes the would-be decision under the updated profile, computes the
compatibility score, compares to threshold, signals. Signals only; does not re-optimise.
Suppresses when observation counts are too thin to be meaningful.

### 4.6 Execution Engine

Loads the active assignment, topologically orders tasks, dispatches to assigned profiles,
routes data between tasks. Executes the stored plan as given; never re-decides at runtime.

**Known gap.** Task failure is recorded and propagated. No fallback profile is attempted. The
project brief names improving reliability as a pillar; reliability is currently a filter at
allocation time, not a mechanism at execution time. **[OPEN — Semester 2.]**

### 4.7 Evaluation Harness

Fixes batch, profile snapshot, budget, and seed identically across conditions; runs Tracks A,
B, C, static baseline, and exact MILP; records cost, runtime, bound, feasibility, and
**delivered reliability against the baseline**.

That last metric is not optional. On cost alone a static allocator wins any drift scenario —
it keeps the cheap plan and reports an unchanged bill while silently violating its floors.
Measured over 16 rounds with a mid-run degradation, a static allocator delivered 0.542
against a 0.95 floor, at cost 400, and reported nothing wrong; the adaptive loop delivered
0.938 at cost 1013 (F24). Reporting cost without delivered reliability would have scored the
failing system as the better one. Any condition
this project introduces that Murakkab's evaluation did not use requires the MILP baseline to be
re-run under it before an improvement is claimed.

---

## 5. Detailed Design

### 5.1 Data model

```text
TaskId {
    workflowId: str
    taskName:   str
}

Task {
    id:        TaskId
    taskType:  str
    load:      float
    relFloor:  float
    latCeil:   float
    successors: TaskId[]        # execution ordering only; not in the optimisation
}

ProfileSpec {
    id:          str
    declaredType: str
    throughput:  float          # thr(m)
    gpus:        int            # gpu(m)
    price:       float          # price(m)
    reliability: float          # rel(m)
    latency:     float          # lat(m) — task-independent in the current model
    observations: int           # backing the EMA; 0 means unprofiled
}

Instance {
    profileId: str
    count:     int              # n[m]
}

AllocationResult {
    routing:      Map<TaskId, ProfileId>      # x
    provisioning: Map<ProfileId, int>         # n
    totalCost:    float
    gpusUsed:     int
    lowerBound:   float | None                # Tracks B, C
    strategy:     "A" | "B" | "C" | "MILP" | "STATIC"
    iterations:   int | None                  # Track B
    restarts:     int | None                  # Track A
    converged:    bool | None                 # Track B
    computeTime:  float
    feasible:     bool
}

Infeasible {
    reason:       str
    blockingTask: TaskId | None
    constraint:   "C1" | "C2" | "C3"
}

Observation {
    taskId:     TaskId
    profileId:  str
    latency:    float
    success:    bool
    cost:       float
    timestamp:  datetime
}
```

**Invariants asserted on every allocation result:**

```text
I1  every task appears exactly once in routing                        (C1)
I2  for every m: Σ load of tasks routed to m ≤ n[m]·thr(m)            (C2)
I3  Σ n[m]·gpu(m) ≤ B                                                 (C3)
I4  every routed profile is in C(t) for its task                      (floors)
I5  n[m] ≥ 1 for every profile appearing in routing
```

I1–I5 are the property test. Every track must satisfy them; a violation is a bug regardless of
which track produced it.

### 5.2 Algorithms

#### 5.2.1 Shared decision rule

```text
function selectProfile(task, pool, state, costAdjust) -> ProfileId | Infeasible:
    best      = None
    bestValue = +inf

    for m in pool:                          # pool is C(t), already floor-filtered
        admit = state.costToAdmit(task, m)
        if admit is Infeasible:             # would exceed GPU budget
            continue

        value = costAdjust(m, admit)
        if value < bestValue:
            best      = m
            bestValue = value

    if best is None:
        return Infeasible(reason="no profile admissible within budget",
                          blockingTask=task.id, constraint="C3")
    return best
```

`costAdjust` is the seam that lets all tracks share this rule:

| Track | `costAdjust(m, admit)` |
|---|---|
| A | `admit.extraCost` — marginal provisioning cost only |
| B | `admit.extraCost + λ[task] ` — plus the relaxed assignment multiplier |
| C (repair) | `admit.extraCost` |

Complexity: `O(|C(t)|)` per task.

#### 5.2.2 Track A — Greedy construction

```text
function trackA(tasks, pools, profiles, budget, seed) -> AllocationResult | Infeasible:
    best = None

    for order in orderings(tasks, seed):        # deterministic set + seeded random
        state  = ProvisioningState(profiles, budget)
        routing = {}
        failed  = False

        for t in order:
            m = selectProfile(t, pools[t], state,
                              costAdjust = (m, a) -> a.extraCost)
            if m is Infeasible:
                failed = True; break
            state.admit(t, m)
            routing[t] = m

        if failed: continue

        result = buildResult(routing, state, strategy="A")
        if best is None or result.totalCost < best.totalCost:
            best = result

    if best is None: return Infeasible(...)
    return best
```

**Known weakness, by construction.** `costToAdmit` is myopic: it prices a task against the
*current* provisioning state, so early tasks may open instances that later tasks would have
made unnecessary, or vice versa. Multi-start partially compensates by trying different orders.
Whether relocate/consolidate are needed on top is **[OPEN — PoC test T2/T4]**.

Complexity: `O(|orderings| · |T| · max|C(t)|)`.

#### 5.2.3 Track B — Lagrangian relaxation

**Which constraint to relax is [OPEN — PoC test T1].** Two candidates:

| Relax | Remaining coupling | Decomposes by |
|---|---|---|
| **(C1)** assignment | (C2) per profile, (C3) global | **Per profile** — classical for facility location |
| (C3) budget | (C1) still couples profiles through tasks | Does not cleanly decompose |

The formulation in §1.8 predicts **relax (C1)**. The pseudocode below assumes it; T1 confirms
or corrects.

```text
function trackB(tasks, pools, profiles, budget) -> AllocationResult | Infeasible:
    lambda = { t: 0.0 for t in tasks }        # one multiplier per assignment constraint
    best   = None
    iter   = 0

    while iter < ITERATION_CAP:
        # --- subproblems, one per profile ---
        selected = {}                          # m -> set of tasks m would take
        subValue = 0.0
        for m in profiles:
            eligible = [t for t in tasks if m in pools[t]]
            take, cost = solveProfileSubproblem(m, eligible, lambda, budget)
            selected[m] = take
            subValue   += cost

        bound = subValue - sum(lambda.values())

        # --- recover a feasible primal solution ---
        candidate = repairToFeasible(selected, tasks, pools, profiles, budget)
        if candidate is not Infeasible:
            if best is None or candidate.totalCost < best.totalCost:
                best = candidate

        # --- subgradient update ---
        # g[t] = 1 - (number of profiles that selected t)
        for t in tasks:
            g = 1 - count(m for m in profiles if t in selected[m])
            lambda[t] = lambda[t] + stepSize(iter) * g

        if converged(lambda): break
        iter += 1

    if best is None: return Infeasible(...)
    best.lowerBound = bound
    best.converged  = (iter < ITERATION_CAP)
    return best
```

`solveProfileSubproblem` decides `n[m]` and which eligible tasks to take, given multipliers.
Because `n[m]` is a ceiling of load over throughput, the subproblem is itself a small
integer problem — this is where the bound can beat the LP.

**[OPEN — T1/O5]:** step-size schedule, convergence tolerance, iteration cap, and the primal
repair heuristic.

#### 5.2.4 Track C — LP relaxation + rounding

```text
function trackC(tasks, pools, profiles, budget) -> AllocationResult | Infeasible:
    lp = buildLP(tasks, pools, profiles, budget)
        # x[t][m] ∈ [0,1], n[m] ≥ 0 continuous
        # (C1), (C2), (C3) as written
    frac, bound = solveLP(lp)

    routing = roundRouting(frac)               # policy — [OPEN, O6]
    state   = ProvisioningState(profiles, budget)
    for t, m in routing:
        if state.costToAdmit(t, m) is Infeasible:
            routing = repair(t, routing, state, pools)
            if routing is None:
                return Infeasible(...)
        state.admit(t, m)

    result = buildResult(routing, state, strategy="C")
    result.lowerBound = bound
    return result
```

**Rounding is not incidental here.** The LP returns fractional `n[m]`. Rounding down breaks
(C2); rounding up may break (C3); and rounding one profile up changes headroom that affects
whether another profile's rounding is feasible. Treat it as an algorithm, not a policy switch.

#### 5.2.5 Exact reference (MILP)

Direct encoding of §1.4–1.6 in PuLP with CBC. Used only as a baseline and as ground truth for
small-instance testing. Not a track.

---

## 6. Implementation Guide

Written for direct implementation. Follow the build order; the scope guard is binding.

### 6.1 Repository layout

```text
poc/
├── formulation/
│   ├── types.py            # Task, ProfileSpec, AllocationResult, Infeasible (§5.1)
│   └── invariants.py       # I1–I5 checks (§5.1) — used by every test
├── instances/
│   ├── generator.py        # synthetic instance generator (§6.4)
│   └── fixtures/           # hand-built adversarial cases for T2
├── core/
│   ├── provisioning.py     # ProvisioningState (§4.4)
│   └── decision_rule.py    # selectProfile (§5.2.1)
├── tracks/
│   ├── exact_milp.py       # §5.2.5
│   ├── track_c_lp.py       # §5.2.4
│   ├── track_b_lagr.py     # §5.2.3
│   └── track_a_greedy.py   # §5.2.2
├── harness/
│   ├── runner.py           # runs conditions under matched inputs
│   └── metrics.py          # cost, runtime, bound, gap, feasibility
└── tests/
    ├── test_invariants.py
    ├── test_provisioning.py
    ├── test_decision_rule.py
    ├── test_tracks_small.py    # vs exact optimum by exhaustion
    └── test_adversarial.py     # T2 fixtures
```

### 6.2 Build order

Each step is testable before the next begins. Do not reorder — later steps depend on earlier
ones being verified.

| # | Build | Verified by |
|---|---|---|
| 1 | `formulation/types.py` | Types instantiate; no logic to test |
| 2 | `formulation/invariants.py` | Hand-built valid and violating results |
| 3 | `instances/generator.py` | Generated instances are well-formed; `C(t)` non-empty |
| 4 | `tracks/exact_milp.py` | Small instances vs hand-computed optima |
| 5 | `core/provisioning.py` | admit/release/snapshot/restore sequences; budget rejection |
| 6 | `core/decision_rule.py` | Known pools with known correct picks; all-infeasible case |
| 7 | `tracks/track_c_lp.py` | Bound ≤ MILP optimum; result satisfies I1–I5 |
| 8 | `tracks/track_b_lagr.py` | Bound ≤ MILP optimum; bound ≥ LP bound (the T1 question) |
| 9 | `tracks/track_a_greedy.py` | Satisfies I1–I5; compared against MILP on small instances |
| 10 | `harness/` | Reproduces a known result end-to-end |

**Build the exact solver at step 4, before any heuristic.** Nothing else can be checked for
correctness without ground truth.

### 6.3 Module contracts

```text
# formulation/invariants.py
def check(result: AllocationResult,
          tasks: list[Task],
          pools: dict[TaskId, list[str]],
          profiles: dict[str, ProfileSpec],
          budget: int) -> list[str]
    """Return a list of violated invariant IDs. Empty list means valid.
       Called by every test and by the harness on every produced result."""

# core/provisioning.py
class ProvisioningState:
    def __init__(self, profiles, budget)
    def cost_to_admit(self, task, profile_id) -> AdmitCost | None   # None = infeasible
    def admit(self, task, profile_id) -> None
    def release(self, task, profile_id) -> None
    def snapshot(self) -> dict
    def restore(self, snap: dict) -> None
    def build_provisioning(self) -> dict[str, int]                  # n[m]
    def total_cost(self) -> float
    def gpus_used(self) -> int

# core/decision_rule.py
def select_profile(task, pool, state, cost_adjust) -> str | None    # None = infeasible

# tracks/*.py  — every track exposes:
def allocate(tasks, pools, profiles, budget, seed=0) -> AllocationResult   # feasible=False on failure
```

Every track returns an `AllocationResult` with `feasible=False` rather than raising, so the
harness can record failures as data instead of crashing.

### 6.4 Instance generator

```text
generate(n_tasks, n_profiles, budget_tightness, seed) -> Instance
```

`budget_tightness ∈ (0, 1]` — the budget as a fraction of the GPUs used by a **reference
allocation**: every task routed to its most GPU-efficient eligible profile (lowest
`gpu(m)/thr(m)`), with instance counts derived from the routed load. This is the **primary
experimental axis** (PoC test T3); the comparison has no signal where the budget is loose.

Because the reference is a real achievable allocation rather than a bound, `tightness = 1.0`
is feasible by construction, and decreasing tightness binds monotonically into infeasibility.
That is the property the sweep needs.

*Amended after PoC measurement — see `poc_findings.md` F2.* This section previously anchored
the budget to "a naive one-instance-per-profile solution", `Σ_m gpu(m)`. That anchor does not
depend on the tasks, so a batch of 8 tasks routinely needs more instances than one-per-profile
and the budget landed below feasibility almost everywhere: 0 of 25 instances were solvable at
tightness 0.3–0.4 and only 16 of 25 at 1.0. T3 had no room to sweep. The reference-allocation
anchor gives 25 of 25 solvable at 1.0.

Note the parameter name runs backwards against its value: 1.0 is the *loosest* budget. Kept
for continuity with the original text.

The generator must guarantee `C(t)` is non-empty for every task, or the instance is discarded
and regenerated.

### 6.5 Scope guard

**Do not build in the PoC:**

- Executor Registry — the generator supplies profiles directly
- Profiling Subsystem — profiles are static inputs
- Execution Engine — nothing is executed
- Drift detection, re-optimisation, J9
- Zookeeper / LogHub domain data — synthetic only
- Track A's relocate, multi-start beyond simple orderings, consolidate — T4 decides if these
  are worth building
- Monitoring, fallback, framework integration

> If a module does not help answer T1, T2, T3, or T4, it does not belong in the PoC.

### 6.6 Test strategy

| Level | Target | Method |
|---|---|---|
| Property | Every track output | I1–I5 asserted on **every** result, in every test |
| Unit | `ProvisioningState` | Admit sequences; headroom arithmetic; budget rejection; snapshot/restore round-trip |
| Unit | `select_profile` | Known pools with hand-computed answers; all-infeasible returns None |
| Component | Each track | Instances ≤ 8 tasks, ≤ 4 profiles — optimum by exhaustion |
| Bound | Tracks B and C | `bound ≤ true optimum` always; record whether `B_bound ≥ C_bound` (T1) |
| Sweep | All | Budget tightness swept; record where solutions diverge (T3) |
| Adversarial | Track A | Hand-built cases where greedy ordering misleads (T2) |

**The property test is the highest-value test here.** All three tracks have relaxation or
rounding steps that can silently produce violating results. Asserting I1–I5 on every output
catches that class of bug regardless of source.

---

## 7. Open Items

| ID | Item | Resolved by | Severity |
|---|---|---|---|
| O1 | Does the objective include a per-invocation term? **Closed: no** — provisioning cost only. Confirmed 2 Sep 2026 | Team decision | Closed |
| ~~O2~~ | **CLOSED.** Track B relaxes **(C1)**, built on §1.8's prediction. The (C3) arm is **no longer unmeasured** — `B-C3` shipped in the step-1 merge and `B-C3-alt` keeps the independent implementation. Result: relaxing (C3) *and* the integrality of `n[m]` is what buys per-task decomposition, and is also exactly why its bound only **matches** the LP rather than beating it (agreement to 2e-5 on 49 paired instances). Relaxing (C1) keeps the discrete step function and is the arm that earns its place | **PoC T1** | Closed |
| O3 | Is Track B's bound strictly better than Track C's? **Preliminary: yes**, strictly tighter on 30 of 30 instances, and tight on the fixture (findings F7) | **PoC T1** | High |
| O4 | Can greedy be fooled by aggregate coupling? | **PoC T2** | High |
| O5 | Step-size schedule, tolerance, iteration cap. **PROMOTED to High by F34 — it is now load-bearing for T1.** Track B reports `converged=False` on 12 of 12 heterogeneous instances and its bound falls *below* the LP's, which theory forbids at the dual optimum. Raising the cap 16x does not help (12.02% -> 11.63%, then flat), so the step size is collapsing rather than the budget running out | **PoC T1** | **High** |
| O6 | ~~LP rounding policy~~ → **Track C's repair pass**. Answered in part: the LP returns an integral routing 96% of the time, so rounding the routing is nearly free; the cost is decided by the repair that runs once `n[m]` must be integral (findings F6) | **PoC T3/T4** | Medium |
| ~~O7~~ | **ANSWERED 4 Sep (F33).** The budget binds **wherever price per GPU is not constant** — which, on this project's own premise of routing across heterogeneous profiles, is the normal case. Measured by holding tasks and profiles fixed and varying only B: (C3) changes the optimal cost in **24 of 25** instances on `heterogeneous_generator.py` (median cost penalty 15.4%), against **4 of 25** uniform and **0 of 25** structured. F26's "nearly inert" describes the old instances, not the problem | **PoC T3** | Closed |
| O8 | Is Track A worth its complexity? | **PoC T4** | High |
| O9 | Is scoped re-optimisation well-defined under (C2)? **Closed: yes, but vacuous** — the affected set is 84–100% of workflows, so J9 re-optimises globally (F18) | Closed | — |
| ~~O10~~ | **ANSWERED 3 Sep (advisor).** Reliability is a **floor**, anchored to baseline-delivered reliability — **not** an objective. So §1.9 stands and the objective stays single-term: provisioning cost. This is the assumption T0's Part 1 ratifies, and it was the one answer that could have invalidated the formulation | Closed | — |
| O11 | Framework integration or standalone | Advisor | High |
| ~~O12~~ | **ANSWERED 3 Sep (advisor, relayed by the team).** The **closed loop is a sufficient novelty claim** for M1 - measured profiles, drift detection, re-optimisation, which neither Murakkab nor Cheng & Nguyen does. This does **not** license claiming novelty in the optimisation: §1.8's concession stands, the allocation problem is textbook modular capacitated facility location and is to be presented as such. Chapter 2 leads with the loop and positions the formulation as adopted, not invented | Closed | - |
| ~~O13~~ | **ANSWERED 3 Sep (F31).** `price(m)` is **not** a multiple of `gpu(m)`. Murakkab's own results move GPU count 2.82x, energy 3.72x and cost 4.33x on one matched workload, and their gains come from trading A100s for H100s - price and energy per GPU differ by hardware type. Our generators assume the opposite (corr(price, gpus) ~ 0.95-1.0), so (C3) is nearly inert **in our instances only**. T3's binding region and T1's arm comparison remain provisional, not because O13 is open but because no generator reflects its answer yet. Deployment target **decided 4 Sep: local first**, so `price(m)` is amortised hardware plus energy across a heterogeneous owned fleet - precisely the regime where price per GPU varies by hardware class and (C3) is *not* redundant with the objective. A third generator reflecting this is being built rather than parked | Closed | - |

---

## 8. Traceability

| Req | Source | Job | Component | Algorithm | Test |
|---|---|---|---|---|---|
| R1 Per-task allocation | Brief; Obj 1.2.1 | J3 | Optimizer | §5.2.1–5.2.4 | Component, property |
| R2 Multiple concurrent workflows | Advisor 31 Aug | J1, J3 | Ingestion, Optimizer | (C2) coupling | Integration |
| R3 Non-exact alternatives to MILP | Obj 1.2.2 | J3 | Tracks A/B/C | §5.2.2–5.2.4 | Sweep |
| R4 Profile-guided, self-updating | Brief; Obj 1.2.3 | J6, J7 | Profiling | EMA | Component |
| R5 Re-optimise on drift | v1 §4 | J8, J9 | Drift Detector | Compatibility score | Component |
| R6 Evaluate vs exact baseline | Obj 1.2.4 | J10 | Harness | Matched-condition | Sweep, statistical |
| R7 Execution monitoring | Brief | — | **Absent** | — | — |
| R8 Improve reliability | Brief | — | **Absent (O10)** | — | — |
| R9 Multi-agent framework | Brief | — | **Absent (O11)** | — | — |

R7–R9 come from the advisor's original project brief and have no implementation. They are
listed rather than omitted.

---

## 9. Reference Map

| Source | Taken | Used in |
|---|---|---|
| Chaudhry et al. (2026), Murakkab | Capacity model: instances provisioned against routed load, under a GPU budget; DAG workflow representation; MILP baseline | §1, §4.7 |
| Cheng & Nguyen (2026) | Feasibility-first-then-minimise-cost rule; marginal activation-cost ranking; multi-start construction | §5.2.1, §5.2.2 |
| de la Torre & Halappanavar (2023) | Lagrangian relaxation with subgradient updates | §5.2.3 |
| Capacitated facility location literature | Problem class identification; relaxation of assignment constraints as the classical decomposition | §1.8, §5.2.3 |
| Hua et al. (2026), AgentOpt | Transport-layer interception, call-context attribution | §4.5 |
| Hatherley (2025) | Compatibility score | §4.5 |
| Topcuoglu et al. (2002); Zhao & Sakellariou (2006) | **No longer used** — §0.4 | — |

---

*End of document.*
