# Part 2 — Reproduction Fidelity

*Where our implementation matches the paper, where it deliberately differs, where it was forced to
differ, and where we simply got things wrong. This part exists so that every number in Part 3 can
be discounted appropriately.*

---

## 1. What was built

```
   /development/          PHASE 1
     specs/               declarative specs (Video Q/A verbatim from Listing 2)
     executor_lib/        26 executors: 15 models/compositions, 11 tools
     orchestrator.py      spec → LogicalWorkflow via an abstract LLM client
     type_check.py        port/type checking across DAG edges

   /optimization/         PHASE 2
     profiles/            provenance system, digitized figures, profile sets
       critique/          quarantined: invented tool times, critical-path compare
     milp/                A5.py (verbatim), model, objectives, solve, joint, compare
       critique/          quarantined: incoherence measurement, structural record

   /execution/            PHASE 3
     registry.py          ExecutableWorkflow, WorkflowRegistry
     dispatch.py          three policies for turning fractions into choices
     autoscaler.py        control loop, thresholds, hysteresis
     sim/                 clock, fleet (with provisioning delay), service model
     workflow_run.py      the DAG walk
       critique/          quarantined: observed-path comparison

   /tests/                570 tests
```

Roughly 8,500 lines. All seven milestones complete. Every test passes.

---

## 2. The governing policy, and why it shaped everything

The project ran under one standing rule, agreed at the start:

> **Where the paper is ambiguous, unsound, or silent, take the paper's reading and RECORD the
> problem. Never silently repair it.**

This is unusual for an implementation and it is worth explaining, because it produces code that
looks wrong in places.

A normal engineer reproducing this paper would hit equation (5), notice it cannot express a
workflow's real latency, and fix it. They would hit the missing link between configurations and
model profiles and add the obvious constraint. They would give `μ_m` a sensible value. The result
would be a better system — and it would be useless as a *measurement* of Murakkab, because every
defect would have been silently absorbed into the implementer's judgement.

So instead: when the formulation says something impossible, we implement the impossible thing and
report what happens. When a value is missing, we mark it `Unavailable` and let the affected
computation fail loudly. The findings in Part 3 exist because of this discipline, not despite it.

A concrete consequence: under the `baseline` profile set, **latency-tier runs come out
infeasible**. That is not a bug. The paper's printed tier thresholds (Figure 7b: `Best ≤0.5s`) are
not reachable under the paper's own equation (5) using the paper's own chosen configuration from
Table 5. We report the infeasibility with the arithmetic attached:

```
   INFEASIBLE_STRUCTURAL -- eq. (5) removed every candidate
     nearest miss: 0.24169 + 179 × 0.0129 = 2.551 s > tau = 0.5 s
```

An implementation that "worked" here would have loosened something.

---

## 3. Deliberate differences — faithful to the formulation

These are places where we implemented what A.5 says rather than what would work better.

### 3.1 Printed SLO tiers kept, even though they are unreachable

The Figure 7b/8b labels are typeset text — exact. Equation (5) cannot reach them. We keep the
labels and report the infeasibility. A second profile set, `derived_tiers`, computes thresholds
from our own eq. (5) population and is used strictly as a control, never as a headline.

**Why it matters:** this is the difference between "our reproduction found the latency tiers
infeasible" and "our reproduction quietly used different tiers."

### 3.2 Configurations and model profiles left unlinked

A.5 indexes allocation as `x_{w,s,c,m}` — a configuration `c` and a model profile `m`,
independently. Nothing requires them to name the same model. We did not add the obvious
constraint. Instead we built a measurement (`milp/critique/incoherence.py`) that reports how much
allocated mass exploits the gap. Part 3, Finding 5 is the result.

### 3.3 No precedence, no makespan

A.5 has neither, so neither do we. Milestones 4, 5 and 6 are forbidden by test from reading the
DAG at all. Milestone 7 walks it — but only for data-flow correctness, never for allocation, and
four tests enforce the distinction:

```
   PERMITTED                              FORBIDDEN
   ─────────                              ─────────
   node starts when predecessors finish   choosing m per node to go faster
   ties break on declaration order        ties break on duration
   exactly one module imports the DAG     any allocation module reading edges
   (c,m) fixed before the walk begins     re-planning mid-walk
```

### 3.4 `μ_m = 1` by default

Setting it to 1 adds no information — equation (3) then reads "peak token demand must fit in
provisioned throughput," which is its evident intent. Any other value would be inserting an answer.

### 3.5 The duplicate equations implemented once

A.5's thirteen numbered equations are ten distinct ones. We implement the ten and record the map,
rather than emitting three redundant constraints to match the numbering.

---

## 4. Forced differences — the consequences of having no GPUs

These are not choices. They are the cost of reproducing a systems paper without the system.

### 4.1 Every profile is reconstructed, and ~14% is missing

The paper measured its profiles on real A100s and H100s. We digitized them from Figures 2, 3 and 4
and Tables 5 and 6.

```
   HOW A VALUE GETS INTO THE REPRODUCTION

   PAPER_TABLE ──────────► exact, no band        ┐
   PAPER_TEXT ───────────► exact, quote required │  36 + 1 values
   PAPER_FIGURE_LABEL ───► typeset, exact        │
   PAPER_FIGURE_READ ────► digitized, BAND REQUIRED  ── 1,013 values
   DERIVED ──────────────► arithmetic + anchors      ── 588 values
   EXTERNAL ─────────────► vendor price + date       ── 2 values
   ─────────────────────────────────────────────────────────────────
   INVENTED ─────────────► 0 in any profile set (test-enforced)
   Unavailable ──────────► ~14% of MILP-facing values
```

The provenance system is enforced, not documentary. A value below `PAPER_FIGURE_READ` strength
*cannot be constructed* without an uncertainty band; a `DERIVED` value cannot be constructed
without naming its anchors; a value cannot claim provenance stronger than what it was derived
from. A reflective test walks 1,656 values and fails on any bare float outside a short, pinned
allow-list.

**The `Unavailable` state is the important part.** When the paper does not report something, we do
not interpolate. Reading an `Unavailable` raises an exception. The affected configuration is
excluded from the optimization and *reported as excluded for lack of data* — which is a different
claim from "excluded because it was bad," and the two are never summed.

### 4.2 PuLP + CBC instead of Gurobi

Forced by licensing. The substitution is confined to one call site. We rejected OR-Tools CP-SAT
explicitly: it is integer-only, and A.5 declares `x ∈ R⁺`. Using it would have discretised request
rates — a modelling change smuggled in as a backend change. A test solves the same model on every
installed backend and asserts identical objective values.

### 4.3 The mock LLM client — and this one is not harmless

§3.2's orchestrator is *"an LLM with tool-calling capabilities."* We have no LLM. We built an
abstract client interface with a mock implementation.

**The mock is biased in a known, documented way.** Its keyword scorer divides overlap by candidate
description length, so longer and more discriminating descriptions *lose*. On Video Q/A it picks
an invented `fixed_interval_segmenter` over the paper's `opencv_scene_detector`, and the type
checker cannot catch the substitution because both type-check identically.

We did not fix this. Under the standing policy the defect stays visible — but at Milestone 7 we
**pinned** the resulting assignment with a snapshot test, so that editing any executor description
breaks a test with a diff rather than silently moving a published number.

**What this means for the report:** every executor assignment in this project comes from a biased
selector. Findings that depend on *which* executor was chosen are weak. Findings that depend on
the *structure* of the DAG or the *shape* of the formulation are unaffected.

### 4.4 Cost from a vendor price list

The paper reports no cost-per-GPU-second anywhere, yet equations (6) and (12) need one. We
retrieved Azure list prices for the two SKUs, stamped `EXTERNAL` with a retrieval date, and swept
them ±50%. A cross-check corroborates the SKU identification: the ratio between our two prices
(3.615) is within 2.3% of the ratio Table 3's own energy/cost sweep implies (3.533), while the
absolute level differs by 1.9× on both — consistent with the paper using negotiated rather than
list pricing.

### 4.5 Scope

Two of the paper's workflows are implemented (Video Q/A, Code Generation). Math Q/A, the OS-log
extension, and §4.4's dynamic coding pipeline are deferred. CPU placement is not implemented,
because A.5 has no CPU resource type to implement it against.

---

## 5. Where we were wrong

Three claims made during development did not survive re-verification on 2026-09-13. They are
listed here rather than quietly corrected, because the method of this project is to be checkable.

### 5.1 §4.6's "near-perfect parallel" is about two workflows, not two sub-tasks

**What we claimed:** that §4.6 measures the overlap between `frame_extract` and `stt` inside Video
Q/A, and that this was empirical evidence for the intra-workflow parallel branch.

**What the paper says:**

> *"The orchestrator constructs a DAG with a fan-out for **the two sub-tasks that can execute in
> parallel: (1) video Q/A (Figure 1a)... and (2) code generation (Figure 1b)**..."*
>
> *"The two sub-tasks run in near-perfect parallel, with full overlap in execution."*

"The two sub-tasks" are the two **composed workflows** in a dynamic request, not two nodes inside
one workflow.

**What survives:** the intra-workflow fan-out is still real — Listing 2 has `frame_extract` and
`stt` both consuming `scenes` and both feeding `q_a`, and Figure 12's Gantt chart shows them as
separate timeline rows. Our decision to execute siblings concurrently still stands on Listing 2's
structure. Only the citation supporting it was wrong.

### 5.2 Latency-tier runs DO have a quality floor

**What we claimed:** that because `τ_{w,s}` is one number per pair, a latency-tier run places "no
floor on answer quality whatsoever" and the optimizer is free to pick the worst configuration
available.

**What the paper says**, §4.3 verbatim:

> *"**We guarantee a basic accuracy tier even for latency SLO requests** (e.g., 50% for video
> Q/A)."*

**What survives, and what does not:**

```
   CLAIM                                              STATUS
   ─────                                              ──────
   A.5 gives one τ per (w,s)                          ✓ true
   eq. (4) is scoped to s = max_accuracy              ✓ true
   ⇒ A.5 cannot express two simultaneous floors       ✓ TRUE — this is the finding
   ⇒ Murakkab therefore has no quality floor on       ✗ FALSE — §4.3 says it does
      latency runs
```

This is not a small correction. It changes the finding from "the system has a hole" to "**the
evaluation applies a constraint the formulation cannot state**" — which is a cleaner and more
useful observation, and another instance of the pattern in Part 3, Finding 4.

It also means our M4/M6 code is faithful to A.5 but **not** to the system §4.3 describes. Adding
the basic-accuracy floor is improvement #5 in Part 4.

A third small discrepancy surfaced while checking this: Figure 7a's printed `basic` label is
**54.9%**, while §4.3's prose says **"e.g., 50%"**. Minor, but they are not the same number.

### 5.3 The multiplexing comparison's "separate" arm was not separate enough

**What we did:** compared "each workflow solved alone" against "both solved jointly," keeping both
SLO tiers together within each arm.

**What §4.1 defines:**

> *"Murakkab Optimized (Mkb Opt) optimizes **each workflow–SLO combination** for a specific
> objective."*
> *"Murakkab Optimized + Multiplexing (Mkb Opt+Mult) **jointly** optimizes requests **across all**
> workflow–SLO combinations."*

So the paper's separate arm is four solves (2 workflows × 2 SLO tiers), not two.

**Re-measured with the paper's own definition:**

```
   video_qa        accuracy-good      38 GPUs
   video_qa        latency-good      328 GPUs
   code_generation accuracy-good      44 GPUs
   code_generation latency-good        8 GPUs
   ────────────────────────────────────────────
   Mkb Opt (4 separate solves)       418 GPUs
   joint, μ=1                        418 GPUs   →  +0.00%
   joint, μ=0.784                    326 GPUs   →  +22.01%
```

**The finding was unchanged.** Still exactly zero. This also settles a question the design had
refused to answer: Table 2's "Murakkab Opt" *is* the separate arm, by §4.1's own wording.

---

## 6. Bugs we introduced, and how they were caught

Four real bugs made it into the implementation. All four were caught by the project's own
machinery rather than by inspection, which is the only reason to trust the rest.

| Bug | Symptom | Why it was dangerous | Caught by |
|---|---|---|---|
| Double unit conversion on arrival rates | 1–2 GPUs where ~68 was right | A plausible small integer. No test, no solver status, and no eyeball would have flagged it. | The units guard — arrival rates carry a unit tag and `demand()` refuses to guess |
| `derived_tiers` was a byte-for-byte copy of `baseline` | The control against our own bugs did not exist | Every infeasibility claim rested on an unchecked assumption | M4's own §7.4 control test, which expected the control to differ |
| Derived latency tiers pooled across workflows | Video Q/A and Code Gen both got τ = 2.938 s | Made the multi-workflow experiment unrunnable on the latency arm under *either* profile set | Verifying a design claim before accepting it |
| `total_gpus` returned instance counts | 41 reported where 328 was right | A.5 multiplies by `g_m` everywhere; TP degrees run 1–8 | M6's fleet reporting a different number than the MILP |

The first and last are worth dwelling on. The unit bug is exactly the failure mode the design
document had predicted in advance — it called §3.4 "the one place a silent bug would be fatal" and
built a `Quantity` wrapper specifically to catch it. It earned that description within a day.

The `total_gpus` bug affected the headline multiplexing result, so we recomputed it. The finding
survived (0.00% either way), but had it not, the published number would have been wrong by a
factor of 8 on some profiles.

---

## 7. What the reproduction has NOT done

Stated plainly, because a reader is entitled to know the boundary.

- **No validation against the paper's reported results.** Tables 1–6 and Figures 7–14 are
  transcribed into the repository but never compared against our own output. Everything has been
  checked for internal consistency and against the paper's *structure*; nothing against its
  *numbers*. This is the last thing that could invalidate any finding in Part 3.
- **No real LLM.** The orchestrator has never run against a real model.
- **No GPUs, no serving engine, no batching, no KV cache, no network.** The Phase 3 simulator uses
  eq. (5) for service time and an `[OURS]` FIFO queueing model.
- **Two of four-plus workflows.** Math Q/A and the OS-log extension are deferred.
- **No CPU placement**, so §4.6's chosen configuration cannot be reproduced at all.

---

## 8. How to weight a number from this project

```
   ┌────────────────────────────────────────────────────────────────────┐
   │ STRUCTURAL          "eq. (3) is linear, so pooling saves only      │
   │ ROBUST              rounding" · "A.5 has no per-node index"        │
   │                     → would hold on real hardware. Cite these.     │
   ├────────────────────────────────────────────────────────────────────┤
   │ MEASURED RATIO      69% blind spot · 22.01% μ contribution ·       │
   │ DIRECTIONAL         81.5% violation rate                           │
   │                     → from digitized profiles, carry bands.        │
   │                       Quote with the band, never bare.             │
   ├────────────────────────────────────────────────────────────────────┤
   │ ABSOLUTE            418 GPUs · 1,547 s · 141,680 GPU-seconds       │
   │ ILLUSTRATIVE        → NOT reproductions of the paper's numbers.    │
   │                       Use for shape and comparison only.           │
   └────────────────────────────────────────────────────────────────────┘
```
