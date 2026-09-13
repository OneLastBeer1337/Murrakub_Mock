> **SUPERSEDED — v1.** Not current. See `docs/v1_superseded/README.md` for what
> replaced this and why. Do not build from it.

---

# Architecture Design — Profile-Guided Resource Orchestration Platform

**This is the main architecture reference for the whole project.** It is written to be
self-contained: a reader with no access to prior conversation history should be able to
understand the full design, why every major decision was made, what precedent supports it,
and what remains open — from this document alone.

---

## Development Priority (Advisor Consultation — Updated)

This section reflects the most recent advisor consultation and **supersedes** the priority
framing in earlier versions of this document. Four changes, in order of impact:

1. **Multi-workflow optimization is now the primary goal, not a future phase.** The advisor's
   view: single-workflow optimization alone is somewhat redundant and doesn't demonstrate
   much — the real problem worth solving is multiple workflows genuinely competing for
   shared resources. Phase B is being rebuilt around this directly, not extended toward it
   later.
2. **Structural DAG-shape optimization (the Palimpzest-derived feature) is REMOVED, not
   paused.** Earlier versions of this document treated it as paused pending a future
   decision. The advisor's reasoning is more specific than "not now": even where reordering
   a workflow's shape helps *on its own*, it doesn't meaningfully compound with resource
   optimization when the two are used *together* — the combined result isn't better than
   using resource optimization alone. On that basis, this feature is cut from scope
   entirely. Section 2 no longer contains it; see Section 8 for the full reasoning as
   recorded.
3. **The problem is explicitly scoped as offline.** "Online" (workflows or executors can
   change while the optimizer is running) is rejected in favor of "offline" (the full set of
   workflows and the executor registry are fixed before any optimization run starts;
   additions only happen *between* runs, never mid-run). This significantly simplifies what
   the multi-workflow algorithms need to handle — no need to react to a workflow appearing
   mid-solve.
4. **Any comparison to Murakkab must be run under matched conditions.** If a metric or
   condition changes from what Murakkab itself was designed around, a fair comparison
   requires re-running Murakkab (or an equivalent) under that same changed condition —
   otherwise a claimed improvement isn't a real comparison, just a test picked to favor this
   project's own system.

---

## 0. Project Context

**Project:** Profile-Guided Resource Orchestration Platform for Multi-Step Agentic Workflows
**Team:** 5 members (66070501035, 075, 077, 083, 089) | **Advisor:** Prof. Tossaphol

**One-line summary:** A system that receives multiple workflows, each already expressed as
a DAG, and — for the whole batch at once, offline — decides which model/hardware/config
each task should use, using real measured performance data, while explicitly accounting for
the fact that every workflow shares one real, limited resource pool. Domain: OS-level
incident detection (log analysis) — see Section 5 for status.

**Technical base:** Murakkab (Chaudhry et al., 2026, OSDI '26, arXiv:2508.18298) — a
resource-efficient serving system for multi-tenant agentic workflows. This project adopts
Murakkab's declarative, profile-guided principle and its recognition that resource
allocation across *multiple concurrent workflows* is the real problem worth solving — and
departs from it in the following confirmed ways:

1. **No exact solver as the core mechanism.** Murakkab's multi-workflow optimizer is a MILP
   (solved via Gurobi) — the same joint solve handles both per-task allocation and
   cross-workflow instance sharing at once. This project replaces that exact solve with two
   non-exact, faster algorithms — see Section 3 — while keeping the same *scope* (multiple
   workflows, shared resources) Murakkab targets. MILP is retained only as an optional
   offline baseline to measure the real optimality gap.
2. **No natural language anywhere.** Murakkab has two NLP-dependent touchpoints — an
   LLM-based orchestrator that builds each workflow's DAG from natural-language sub-task
   descriptions at design time, and an optional runtime path that composes a workflow from a
   raw natural-language end-user query. Both are cut entirely. Every workflow this project
   handles arrives as an already-structured DAG.
3. **Continuous, per-execution profile updating.** Murakkab profiles once (offline, before
   serving begins) and only vaguely mentions periodic refresh. This project's profile
   updates after every real execution (via an exponential moving average). Because
   structural re-optimization is no longer in scope (see Development Priority, above), this
   continuous updating now feeds only into Phase B's re-optimization — not a structural
   decision — but it remains the project's central point of departure from how Murakkab
   itself builds and maintains its profiles.

**Domain status:** OS-level incident detection (syslog, kernel log, systemd journal) is the
current candidate domain, chosen because synthetic fault injection can generate a test set
with known ground truth entirely in-house. **This is not yet fully settled** — confirm with
Ano before treating it as locked. A second domain (document processing) has been discussed
but is not active scope.

---

## 1. System Overview

```
  Multiple incoming DAGs (offline — fixed before this run starts)
              |
              v
  +-----------------------------+
  | PHASE A: Ingestion +        |
  | Layer 1 Eligibility Lookup  |    <- Executor Registry (manual, per domain)
  +-----------------------------+
              |
              v
  +---------------------------------------------------+
  | PHASE B: Multi-Workflow Optimizer                  |
  |   Track A: HEFT (multi-workflow)      <- Profile   |
  |   Track B: Lagrangian Relaxation      <- Store     |
  +---------------------------------------------------+
              |
              v
  Executable assignment (every task, every workflow) -> stored in Registry
              |
              v
  +-----------------------------+
  | PHASE C: Execute + Profile  |
  |   1. Task-Candidate Profile |  (built)
  |   2. Workflow Arrival/Demand|  (NOT yet built)
  |   3. Compatibility/Drift    |  (built, derived from #1)
  +-----------------------------+
              |
              v (drift trigger)
      re-runs PHASE B only -- Phase A has no structure left to reconsider
```

Two structural changes from earlier versions of this diagram, both already reflected above:
**Phase A no longer has a loop-back path** (the drift trigger used to potentially re-invoke
structural search; with that feature removed, drift only ever triggers Phase B). **Phase B
is no longer a single mechanism** — it now runs two genuinely different multi-workflow
algorithms side by side, both reading the same profiled data, for direct comparison.

---

## 2. Phase A — Workflow Ingestion & Layer 1 Eligibility Lookup

**Job:** take multiple incoming DAGs (offline — the full batch is fixed before Phase B ever
runs) and, for every task in every workflow, determine which registered executors are
eligible to perform it. Phase A does **not** decide which executor wins — that's Phase B's
job entirely (see Section 3).

### 2.1 Developer-facing interface

A developer supplies a **standard DAG** (JSON: nodes = tasks, edges = dependencies) — no
special API, no terse chained-call syntax, no natural language. The brevity of what a
developer writes comes from not having to specify model/resource choices (that's Phase B's
job), not from any unusual input format. Task nodes reference `task_type` — a structured
label (e.g. `classify_severity`), not free text.

### 2.2 What Murakkab does here, and what's cut

Murakkab's Development phase has developers write workflows as high-level sub-tasks in
natural language, with no configuration details. A Workflow Orchestrator — itself an LLM
with tool-calling ability — interprets this, parses it into sub-tasks, and maps each to an
Executor, producing a request-agnostic Logical Workflow DAG. Separately, at runtime,
Murakkab also supports "Dynamic Workflow Requests" — a raw natural-language end-user query,
composed into a workflow on the fly.

- **Design-time NL sub-task interpretation (Murakkab):** an LLM reads natural-language task
  descriptions and generates the DAG itself -> **This project: CUT.** DAG structure and task
  identities always arrive already decided.
- **Runtime "Dynamic Workflow Requests" (Murakkab):** an LLM composes a workflow on the fly
  from a raw end-user query -> **This project: CUT.** Every request references an
  already-structured, registered workflow.

### 2.3 Layer 1: Eligibility Lookup

This is the mechanism previously left implicit; it is now named as its own explicit step,
per advisor feedback that the task-to-executor matching step should be visible in the
architecture, not folded silently into "the optimizer."

**What it does:** for every task, look up `task_type -> candidate pool` — an **exact match**
against the executor registry. If `classify_severity` has two registered executors
(`small-model`, `large-model`), the lookup returns both, with no judgment about which is
better. That judgment happens later, in Phase B.

**How an executor gets into the registry in the first place — confirmed against how
Murakkab itself actually works (not auto-discovery):** every executor exists because a
developer manually registered it — the same way Murakkab's own onboarding works (if no
suitable executor is found for a task, Murakkab prompts the developer to add one). Each
registered executor carries Murakkab's own three-field schema:

1. **A textual description** — what the executor does, in words
2. **An interface spec** — input/output types
3. **A key-value list of configurable knobs** — adjustable settings

Murakkab groups every executor into one of three kinds — **LLM** (a specific model
configuration), **Structured composition** (multiple models working together), or **Tool**
(a plain utility, including "any MCP-compliant third-party tool" — Murakkab's own named
example). All three kinds are described the same three-field way, so the registry and
lookup logic treat them uniformly.

**What Layer 1 deliberately does NOT do:** it never ranks, filters by cost, or picks a
winner. It also never performs semantic matching — an executor registered for a *similar but
not identical* task type is not automatically considered eligible. This is a genuine,
acknowledged limit — see Section 9.

### 2.4 The offline constraint, precisely

Per the Development Priority section above: the full set of workflows *and* the full
executor registry are fixed before Phase B ever starts a run. Concretely, this means:

- No workflow can be added mid-optimization; a new workflow waits for the next run.
- No executor can be newly registered mid-optimization either — a new executor becomes
  eligible starting with the *next* run, not the current one.
- Between runs, nothing about Phase A or Layer 1's mechanism changes — the constraint is
  purely about *when* additions are allowed to take effect, not a new mechanism to build.

---

## 3. Phase B — Multi-Workflow Optimizer

> **PRIMARY ACTIVE FOCUS.** This is the core rebuild driven by the most recent advisor
> consultation — replacing the single-workflow allocator with a genuinely multi-workflow
> mechanism.

**Job:** given multiple workflows and their Layer-1-eligible candidate pools, decide a
model/hardware/config assignment for every task, in every workflow, **jointly** — accounting
for the fact that they all draw from one real, shared resource pool.

### 3.1 Why multi-workflow, not single-workflow

The prior design allocated one workflow instance at a time, each assuming it had the full
resource pool to itself — an assumption that breaks the moment two instances actually run
concurrently (both could overcommit the same real capacity, and there was no rule for which
one should win). Per the advisor consultation, this is the primary gap being closed: Phase B
now optimizes across the whole batch of concurrently-registered workflows at once, the same
scope Murakkab itself targets — using non-exact methods instead of Murakkab's MILP.

### 3.2 Two tracks, run for direct comparison

Both tracks read the same inputs — Layer 1's eligible pools, and Phase C's profiled
cost/latency/reliability data (see Section 4) — and both are scoped to the same offline
batch of workflows. They are structured for direct comparison, the same way the earlier
single-workflow design compared a heuristic against a search-based method.

#### Track A — HEFT (multi-workflow)

**Source:** Topcuoglu, Hariri & Wu (2002), IEEE TPDS 13(3):260-274 (the original HEFT
algorithm) + Zhao & Sakellariou (2006), IPDPS (the multi-DAG extension, six interleaving
policies, two explicitly for fairness).

```
Step 1 -- Rank every task, in every workflow, using REAL profiled cost:
    rank(t) = avg_cost(t) + max over successors s of [ comm_cost(t,s) + rank(s) ]
    (computed backward from the end of each DAG -- the "critical path")

Step 2 -- Interleave each workflow's own ranked list into ONE combined global order,
    using a fairness-aware policy (per Zhao & Sakellariou's multi-DAG extension) --
    this is the step that doesn't exist in the single-workflow version at all.

Step 3 -- Walk the single combined list, once, top to bottom. For each task, pick
    whichever eligible candidate (from Layer 1's pool) gives the earliest finish
    time, given what's already been committed to the SHARED resource pool by
    every higher-priority task processed so far.
```

**Trade-off:** fast, one pass. No built-in way to know how close the result is to the true
optimum — that has to be measured separately (e.g. against the offline MILP baseline, or
against Track B's bound — see below).

**A genuine reuse point, not a rebuild from scratch:** Step 3's "pick the best eligible
candidate" decision can directly reuse the filter-then-cheapest logic from the project's
original single-workflow heuristic (feasibility filter, then minimize cost among survivors)
— HEFT's own selection criterion (earliest finish time) can be adapted to a cost-based
version rather than treated as an unrelated new rule. This is not the "layering" the advisor
rejected (that was about stacking an unrelated structural-optimization step on top); this is
reusing an already-validated per-task decision rule *inside* a new multi-workflow
coordination mechanism.

#### Track B — Lagrangian Relaxation

**Source:** de la Torre & Halappanavar (2023), JSSPP — "Scaling Optimal Allocation of Cloud
Resources Using Lagrange Relaxation," applied to cost-efficient cloud resource allocation
for scientific workflows via demand decomposition.

```
Step 1 -- Take the one constraint that couples every workflow together (total
    resource usage across ALL workflows <= shared capacity) and move it into the
    objective as a penalty, weighted by a multiplier (lambda).

Step 2 -- With that constraint relaxed, the problem splits into N independent
    per-workflow subproblems -- one per workflow, each solvable on its own.

Step 3 -- Check total usage across all N solved subproblems against real capacity.
    Over? Raise lambda (discourage heavy use next round). Under? Lower it.
    Re-solve Steps 2-3 again with the updated lambda.

Repeat Steps 2-3 until lambda stabilizes.
```

**Trade-off:** iterative, slower than HEFT. In exchange, it produces a **mathematically
proven lower bound on the true optimal cost at every iteration** — a real property of
Lagrangian duality, not an estimate — so the optimality gap is known automatically, without
needing a separate exact-solver run to check.

**The same reuse point applies here too:** each of the N per-workflow subproblems in Step 2
is, on its own, exactly the single-workflow allocation problem the project's original
heuristic (feasibility filter, then minimize cost) already solves. That heuristic can serve
directly as the per-workflow subproblem solver — Lagrangian relaxation supplies the
cross-workflow *coordination* (the shared penalty), not a replacement for the per-workflow
decision logic itself.

### 3.3 The decision rule, formally (shared by both tracks' inner per-task/per-workflow step)

```
minimize      cost(c)
subject to    reliability(c)  >=  R_min(t)
              latency(c)      <=  L_min(t)
              consumption(c)  <=  remaining_shared_capacity
over          c in eligible_candidates(t)      [from Layer 1]
```

This is the same formulation as the project's original single-workflow decision rule (P3,
Cheng & Nguyen — feasibility-first, then minimize cost) — what's changed is that
`remaining_shared_capacity` is now a genuinely shared quantity across workflows, not a
private per-instance ledger.

### 3.4 Comparison to Murakkab's own optimizer, step by step

| Step | Murakkab | This project |
|---|---|---|
| **Scope** | Whole fleet, multi-tenant, jointly | Whole batch of concurrently-registered workflows, jointly — same scope |
| **Solver** | MILP (Gurobi), exact | HEFT (fast, no gap guarantee) and Lagrangian relaxation (iterative, proven gap bound) — both non-exact |
| **Cross-workflow interaction** | Handled exactly, by construction | HEFT: approximated via one shared pool and a fairness-interleaving policy. Lagrangian: approximated via penalty-coordinated decomposition |
| **Cold start** | Not directly addressed | Explicit seed-run policy (inherited from the per-workflow/per-task subproblem solver) |
| **Re-optimization trigger** | Fixed periodic epoch (60 min in their eval), fleet-wide | Event-triggered (profile drift past a threshold), triggers Phase B only |
| **Offline vs. online** | Periodic re-solve implies an evolving fleet over time | Explicitly offline — the batch is fixed for the duration of one optimization run (see Section 2.4) |

### 3.5 Fair-comparison principle

Per the Development Priority section: if this project changes a metric or condition that
Murakkab's own evaluation didn't use, Murakkab (or a faithful re-implementation) must be
re-run under that same changed condition before claiming an improvement. A result that only
looks better because the test was picked to favor this project's own system is not a valid
comparison. This applies directly to Stage 8's evaluation design (see `Project_Schedule.md`).

---

## 4. Phase C — Execution + Continuous Profiling

**Job:** execute the assignment Phase B produced, and maintain three distinct kinds of
profiled data — only one of which is new as of this update.

### 4.1 What Phase A and B already assume Phase C provides

- Cold-start seed-run execution for whichever track's per-workflow subproblem solver needs
  it.
- The task-candidate profile data itself — every feasibility check and cost comparison in
  Phase B reads data only Phase C can produce.
- The drift signal that fires Phase B re-optimization.

*(The earlier "sentinel-config execution for Phase A's structural comparison" item is
removed — Phase A no longer performs structural search, so this dependency no longer
exists.)*

### 4.2 Measurement mechanism — how Phase C actually captures cost/latency/reliability

Phase C intercepts at the call layer — the same pattern P6 (AgentOpt) uses for its own
profiling: patch the transport layer once, and attribute each intercepted call to (task,
candidate, workflow-instance) via call-context propagation. This is what makes profiling
framework-agnostic.

**What's recorded per call:** wall-clock latency, success/failure (or a graded correctness
signal where one exists), and cost.

### 4.3 Ground truth for "reliability" — fault injection (OS-log domain)

Synthetic fault injection generates test scenarios with a known, controlled outcome —
stress-based faults (CPU/memory/disk saturation), process-kill faults, and disk-fill faults.
Because the fault is injected deliberately, the "correct" incident report is known in
advance — a task's real output can be checked against it directly.

### 4.4 Three things being profiled — only one is new

| # | What | Tracks | Status |
|---|---|---|---|
| 1 | **Task-Candidate Profile** | cost, latency, reliability, resource consumption, per (task_type, candidate) | **Already built.** Core data both Phase B tracks read to make every decision. |
| 2 | **Workflow Arrival/Demand** | projected request rate per (workflow, SLO)-pair, derived from recent trends (Murakkab's own "arrival patterns" concept) | **NOT yet built.** New infrastructure — only becomes necessary once multi-workflow coordination needs to know relative demand across workflow types. Not needed for single-workflow allocation, which is why it was never built before. |
| 3 | **Compatibility / Drift Score** | `C(h2, h1)` — a comparison of the task-candidate profile's before/after state | **Already built** — but it is a *computed* comparison, not an independently profiled quantity. It depends entirely on #1's data existing. |

**Item 2 is the one concrete new piece of infrastructure this update introduces.** It is not
required for Phase B's core mechanism to run (both HEFT and Lagrangian relaxation can
operate on task-candidate profiles alone), but it becomes relevant if a future capacity-split
policy needs to weight workflows by expected demand rather than treating them identically.

### 4.5 Compatibility score, precisely

Following P9's own formalization (via Bansal et al.): for a stored plan `h1` and its
profile-recomputed version `h2`, the compatibility score is the fraction of
previously-correctly-handled cases that `h2` also handles correctly:

```
C(h2, h1) = | cases h1 got right AND h2 also gets right | / | cases h1 got right |
```

A score well below 1.0 fires the re-optimization trigger — **which now re-runs Phase B
only.** There is no structural search left in Phase A for this trigger to invoke.

### 4.6 Who owns the staged re-check cadence

Phase C keeps a per-registered-workflow counter of consecutive in-threshold compatibility
checks; the interval between checks widens as that counter grows, and resets to the
frequent/early interval the moment a check ever crosses the threshold. This governs how
often Phase B gets re-invoked, not Phase A (which no longer has anything to reconsider).

### 4.7 Worked example

Over 50 real runs, `small-model`'s observed reliability on `classify_severity` averages
0.89 — below its 0.90 floor. The EMA update pulls the profile down. The compatibility check
fires the drift trigger. **Phase B re-runs directly** — no structural step involved — using
whichever track (HEFT or Lagrangian) is active, and `large-model` now wins where
`small-model` no longer does. The log records:

> *"classify_severity reassigned from small-model to large-model — observed reliability
> 0.89 fell below the 0.90 floor over the last 50 runs."*

---

## 5. Domain Discussion

**Status: not yet fully settled — confirm with Ano.**

### 5.1 Candidate domain: OS-level incident detection

Sources: syslog, kernel log, systemd journal. Chosen specifically because synthetic fault
injection can generate a test set with known ground truth entirely in-house, avoiding the
need for external labeled data. Output artifact: an Incident Report.

### 5.2 Document processing — not active scope

Was discussed as a possible second domain in earlier consultations. Not currently active
scope, and not required for the multi-workflow optimization work described in Section 3,
which is domain-agnostic by construction (it operates on task-candidate profiles and
resource pools, not on domain-specific content).

---

## 6. Cross-Cutting Divergences From Murakkab

| Dimension | Murakkab | This project |
|---|---|---|
| Workflow shape creation | LLM interprets NL, generates DAG | No generation — arrives pre-structured |
| Runtime workflow composition | Supports raw NL end-user queries | Not supported — must reference registered workflow |
| Workflow shape after creation | Frozen forever once generated | Also frozen — structural reoptimization is out of scope entirely (not just paused) |
| Allocation scope | Whole fleet, multi-tenant, jointly | Whole batch of registered workflows, jointly — **same scope as Murakkab**, this is no longer a divergence |
| Core allocation solver | MILP (Gurobi), exact | HEFT + Lagrangian relaxation, both non-exact; MILP = offline baseline only |
| Cross-workflow interaction | Handled exactly, by construction | Approximated (HEFT: shared pool + fairness policy; Lagrangian: penalty-coordinated decomposition) |
| Problem timing | Periodic re-solve (60-min epoch), implies an evolving fleet | Explicitly offline — fixed batch per optimization run |
| Profile updating | Offline once; vague periodic refresh | Continuous, per-execution EMA |
| Re-optimization trigger | Fixed periodic epoch, fleet-wide | Event-triggered (profile drift), per Phase B re-run |
| Demand scaling | Dedicated Auto-Scaler, fleet-wide | Not adopted — out of scope |

**Note the one row that changed character:** allocation *scope* is no longer a divergence —
this project now targets the same multi-workflow scope Murakkab does. The divergence moved
to *how* that scope is solved (exact vs. non-exact), which is a cleaner, more defensible
comparison than the earlier single-vs-multi-workflow scope mismatch.

---

## 7. What's Taken From Where — Full Reference List

| Paper | Role in this design |
|---|---|
| **P1 — Murakkab** (Chaudhry et al., 2026, arXiv:2508.18298) | Technical base: DAG structure, profile-guided principle, and — as of this update — the multi-workflow allocation *scope* itself (previously only its declarative structure was adopted). |
| **P3 — Fast Heterogeneous Serving** (Cheng & Nguyen, 2026, arXiv:2604.07472) | Source of the feasibility-first-then-minimize-cost decision rule (Section 3.3) — now reused as the inner per-task/per-workflow solver inside both multi-workflow tracks, not a standalone allocator. |
| **HEFT — Topcuoglu, Hariri & Wu (2002)**, IEEE TPDS 13(3):260-274 | Direct mechanism for Track A: the two-phase rank-then-assign algorithm. |
| **Multi-DAG HEFT extension — Zhao & Sakellariou (2006)**, IPDPS | Source of the cross-workflow interleaving step (Section 3.2, Track A, Step 2) and its fairness-aware policy variants. |
| **Lagrangian relaxation for cloud resource allocation — de la Torre & Halappanavar (2023)**, JSSPP | Direct mechanism for Track B: demand decomposition into per-workflow subproblems coordinated via a shared penalty. |
| **P6 — AgentOpt** (Hua et al., 2026, arXiv:2604.06296) | Transport-layer measurement pattern (Section 4.2) — its own search-based allocator (Matrix UCB-E/Arm Elimination) is no longer part of core Phase B scope, since Phase B's mechanism is now HEFT/Lagrangian rather than single-workflow search. |
| **P7 — MASTER / MARL** (Bruinaars, 2025) | Evaluation methodology (baselines + statistical tests). Its own RL-based allocation approach remains not adopted. |
| **P9 — Update Opacity** (Hatherley, 2025) | Compatibility-score formula (Section 4.5) + the motivating rationale for structured, transparent drift logging. |
| ~~**P10 — Palimpzest**~~ | **No longer part of active scope.** Previously the direct mechanism precedent for structural DAG-shape optimization; that feature has been removed per the advisor consultation recorded in this document's opening section. Retained in `Research Paper/paper_map/` for historical reference only. |
| **P11 — DocETL** | No longer directly relevant — was tied to the document-processing second domain and Palimpzest-style structural rewriting, both currently out of scope. |

---

## 8. Confirmed Decisions Log

- **[Updated]** Multi-workflow optimization is the primary goal, not a future extension.
  Single-workflow optimization alone was assessed by the advisor as not demonstrating enough
  to justify as the project's main contribution.
- **[Updated — reasoning recorded]** Structural DAG-shape optimization (Palimpzest-derived)
  is removed from scope entirely. Specific reasoning: even where it helps independently, it
  doesn't meaningfully improve results when combined with resource optimization — the
  combined outcome isn't better than resource optimization alone.
- **[New]** The problem is explicitly offline: the full batch of workflows and the executor
  registry are fixed before any optimization run starts. No mid-run additions.
- **[New]** Phase B's core mechanism is now two multi-workflow algorithms: HEFT (multi-DAG
  extension) as the primary/fast track, Lagrangian relaxation as the comparison track that
  additionally produces a proven optimality-gap bound.
- **[New]** Both tracks reuse the original single-workflow decision rule (feasibility filter,
  then minimize cost) as their inner per-task/per-workflow solver — this is a deliberate
  reuse of validated logic, not the "layering" the advisor cautioned against (which referred
  specifically to stacking structural optimization on top of resource optimization).
- **[New]** Layer 1 (task-to-executor eligibility lookup) is now an explicit, separately
  named step in Phase A — exact match on `task_type`, automated at request time; the
  registry itself remains manually populated per domain, following Murakkab's own onboarding
  pattern and three-field schema.
- **[New]** Any comparison to Murakkab must be run under matched conditions — if this
  project changes a metric or condition Murakkab wasn't evaluated under, Murakkab must be
  re-run under that same condition before claiming improvement.
- **[New]** Three distinct kinds of profiled data now exist in Phase C: task-candidate
  profile (built), workflow arrival/demand (not yet built — new infrastructure), and
  compatibility/drift score (built, derived from task-candidate data).
- **[Carried forward]** NLP: cut entirely, at both of Murakkab's touchpoints.
- **[Carried forward]** Developer interface: a standard DAG (JSON), no special terse API, no
  natural language.
- **[Carried forward]** Registry storage and structure: executors are described via
  Murakkab's three-field schema (description, interface spec, configurable knobs), manually
  registered.

---

## 9. Still Open (Not Resolved by This Document)

- **Domain is not fully settled** — OS-log incident detection is the working candidate;
  confirm with Ano before treating it as locked.
- **HEFT's fairness-interleaving policy** — Zhao & Sakellariou's paper presents six
  candidate policies; which one (or what adaptation) this project actually uses is not yet
  chosen.
- **Lagrangian relaxation's multiplier-update procedure** — the subgradient step size and
  convergence criteria need real tuning once profiling data exists to tune against; not yet
  designed in detail.
- **Workflow arrival/demand profiling (Section 4.4, item 2)** — not yet designed at all; only
  identified as necessary if a future capacity-split policy needs to weight workflows by
  demand.
- **Exact drift threshold `tau` and EMA rate `alpha`** — placeholders, need real values once
  initial profiling data exists.
- **Whether HEFT and Lagrangian relaxation should both run live, or whether one becomes the
  sole live mechanism after comparison** — not yet decided; currently both are built for
  direct comparison, per Section 3.2.
- **The exact criterion for Layer 1 eligibility remains exact-match only** — no semantic
  matching between similar-but-not-identical task types; whether this needs to be relaxed is
  an open question, not yet raised with the advisor.
