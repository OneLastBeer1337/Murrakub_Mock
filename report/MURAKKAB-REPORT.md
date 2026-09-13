# Murakkab: Reproduction Report

**A from-scratch reproduction of "Murakkab: Resource-Efficient Agentic Workflow Orchestration in
Cloud Platforms" (OSDI 2026), and what building it taught us about the paper.**

Prepared 2026-09-13. All paper claims in this report were re-verified against the source PDF
(`osdi26-chaudhry.pdf`) on that date, not recalled from earlier sessions.

---

## Contents

| Part | Title | What it covers |
|---|---|---|
| — | **Overview** | Summary, the five findings, how to weight the numbers, corrections |
| **1** | **What Murakkab Actually Does** | The paper's design, phase by phase. No critique. |
| **2** | **Reproduction Fidelity** | Matches, deliberate differences, forced differences, our own errors |
| **3** | **What Implementing It Revealed** | Five findings, each with measurement and confidence |
| **4** | **Improving Murakkab, From Inside** | Ten improvements traced to paper sentences |

---

## What this report is

There is no source release for Murakkab. There is only the paper. So "reproducing" it meant
building an original implementation of the components, interfaces and algorithms the paper
*describes* — a declarative specification layer, a workflow orchestrator, a profiling system, a
MILP optimizer, an auto-scaler, and a multi-tenant runtime — and then seeing which of the paper's
claims survive contact with a working implementation.

The result is roughly 8,500 lines of implementation and 570 tests, covering all three of
Murakkab's life-cycle phases. More importantly, it produced a set of findings that are only
visible from the inside: things that look fine on the page and stop working when you try to run
them.

This report has four parts, written to be read in order but usable separately.

| File | What it covers |
|---|---|
| **Part 1** | The paper's actual design, phase by phase and component by component. No critique — just what it says. |
| **Part 2** | Where our implementation matches, where it deliberately differs, where it was forced to differ, and the bugs we made. |
| **Part 3** | What implementing it revealed. Five major findings, each with the measurement behind it. |
| **Part 4** | Ten improvements, each traceable to a sentence in the paper that the formulation fails to encode. |

---

## The one-paragraph summary

Murakkab's central idea is sound and, in our reading, genuinely novel: take configuration away
from workflow developers, give the cloud platform visibility into workflow internals, and let a
periodic optimizer choose models, hardware and parallelism against an SLO. The implementation
confirms that the *architecture* works — the three phases compose, the registry hands off cleanly,
and the MILP solves in well under a second on an open-source solver.

What does not survive is the **formulation in Appendix A.5**. It is systematically narrower than
the system the paper's own prose and evaluation describe. Six specific capabilities are described
in Sections 2–4 and cannot be expressed in the appendix at all. And the paper's headline
multiplexing result — a 21.6% GPU reduction — turns out to enter the model entirely through a
coefficient that is defined in one clause, quantified nowhere, and which we could only obtain by
fitting it to the very number it is supposed to produce.

---

## The five findings, in one table

| # | Finding | Evidence |
|---|---|---|
| **1** | **A.5's structure produces zero multiplexing gain.** Sharing model instances across workflows saves exactly 0.00%. The entire reported 21.6% enters through the undefined `μ_m`. | Measured: 418 → 418 GPUs at μ=1; 326 at μ=0.784 |
| **2** | **eq. (5)'s blind spot is worth 0.3% or 69%**, depending entirely on token count. A single claim about "Murakkab's latency model" is too coarse to be useful. | Code Gen 0.24%; Video Q/A 69% (robust across ±3× band) |
| **3** | **The auto-scaler cannot do what §3.4 claims.** It monitors on a 60-second window; §4.7 assumes provisioning takes 20 minutes. | 81.5% violations with the paper's delay vs 36.5% without |
| **4** | **The appendix is narrower than the paper.** Six capabilities are described in prose and evaluated in §4, and cannot be written in A.5. | Verbatim quotes, Part 3 §4 |
| **5** | **The `c`/`m` decoupling is exploited, not latent.** 100% of allocated mass routed a video configuration onto a text-only model. | Measured under `baseline` |

---

## How to read the numbers in this report

Three levels of confidence, and they are not interchangeable:

**Structural claims are robust.** "Eq. (3) is linear, therefore pooling demand can only save
integrality rounding" follows from the algebra and would hold on real hardware. So does "A.5 has
no index for per-node executor assignment." These are the claims worth citing.

**Measured ratios are directionally sound, with bands.** The 69% blind spot, the 81.5% violation
rate, the 22.01% μ contribution. These come from reconstructed profiles digitized from the paper's
own figures, and each carries an uncertainty band. Where a conclusion depends on an invented
number, we tested it across the full band and say so.

**Absolute magnitudes are not reproductions of the paper's numbers.** We have no GPUs. Every
latency comes from eq. (5) evaluated on digitized curves; every energy figure comes from Table 3
per GPU type. Roughly 14% of the values the optimizer needs are recorded as `Unavailable` because
the paper does not report them — never guessed, never imputed.

One more caveat that applies everywhere: **the reproduction has not been validated against Tables
1–6 or Figures 7–14.** Everything has been checked for internal consistency and against the
paper's *structure*; nothing has been checked against its *reported results*. That remains the
last thing that could invalidate any finding here.

---

## Corrections to earlier drafts

Honesty about our own errors is part of the method, so they are listed rather than silently fixed.
Three claims made during development turned out to be wrong on re-verification:

1. **§4.6's "near-perfect parallel" is about two composed workflows**, not Video Q/A's internal
   `frame_extract ∥ stt` branch. The intra-workflow fan-out is real (it is in Listing 2), but that
   sentence is not evidence for it.
2. **Latency-tier runs DO have a quality floor.** §4.3 states it verbatim. Our claim that they had
   none described A.5's silence, not Murakkab's behaviour.
3. **The "separate" arm of the multiplexing comparison was not separate enough.** Re-measured per
   §4.1's own definition; the result was unchanged.

Details in **Part 2**, Part 4.

<div style="page-break-after: always"></div>

---

# Part 1 — What Murakkab Actually Does

*The paper's design, phase by phase and component by component. This part contains no critique.
It is a careful reading of what the paper says, with the quotes that support it, so that Part 3's
findings can be checked against something.*

---

## 1. The problem Murakkab is trying to solve

Before the architecture, the motivation — because the architecture only makes sense against it.

Agentic workflows are applications built from multiple AI "agents" that call models and tools and
pass data between them. A video question-answering workflow detects scenes, extracts frames,
transcribes audio, and asks a multi-modal LLM to answer. A code generation workflow has several
coder agents debate candidate solutions, tester agents write tests, an interpreter runs them, and
a ranker picks a winner.

Today these are built in frameworks like LangGraph or LlamaIndex, and §2.5 identifies the problem
as a **two-sided blindness**:

> *"Frameworks for agentic workflows place the burden of workflow configuration on developers.
> Most developers are neither systems nor ML experts, and cannot reason about accelerator choice,
> model parallelism, or model selection. Configurations are therefore often arbitrary and
> inefficient... Even experienced developers, lacking insight into user priorities, default to
> maximizing accuracy at the expense of efficiency."*

And from the other direction:

> *"From the cloud provider's perspective, these workflows are opaque. The cloud platform has
> little visibility into workflow components (e.g., models) or interactions (e.g., task sequences
> and data flow). Tightly coupled application logic and execution details prevent the platform
> from reconfiguring workflows to improve resource efficiency while meeting SLOs."*

This is crystallised as **Insight 1**:

> *"Cloud platforms lack visibility into workflow internals (e.g., tasks, requirements),
> preventing end-to-end optimization. Meanwhile, developers lack control or insight into
> system-level resource behavior."*

So the developer hardcodes `Llama-3.2`, `{"num_frames": 15}`, `{"GPUs": 8, "Type": "H100"}` into
their application (this is Listing 1, the paper's straw-man), and the platform — which knows the
current load, the spot prices, and which GPUs are idle — cannot change any of it.

**Murakkab's bet is that if you take the configuration out of the application, the platform can
optimise it continuously.** Everything in the design follows from that.

---

## 2. The life-cycle: three phases

§3.1 divides an agentic workflow's life into three phases. Table 1 in the paper lists which
decisions belong to each, and how often each is made. This structure is not incidental — it is
the paper's main organising claim, that existing systems *fragment* these phases across different
entities and Murakkab unifies them.

```
   ╔══════════════════════════════════════════════════════════════════════╗
   ║  PHASE 1: DEVELOPMENT          "Once at onboarding"                  ║
   ║  ──────────────────────────────────────────────────────────────────  ║
   ║   Developer writes a DECLARATIVE SPEC (sub-tasks + data flow only)    ║
   ║                         │                                            ║
   ║                         ▼                                            ║
   ║   ORCHESTRATOR (an LLM with tool-calling) consults the                ║
   ║   EXECUTOR LIBRARY and emits a LOGICAL WORKFLOW = a DAG               ║
   ╚═════════════════════════╤════════════════════════════════════════════╝
                             │  logical workflow
                             ▼
   ╔══════════════════════════════════════════════════════════════════════╗
   ║  PHASE 2: OPTIMIZATION         "Per epoch" (60 minutes)              ║
   ║  ──────────────────────────────────────────────────────────────────  ║
   ║   PROFILES (workflow: accuracy + tokens; model: latency, energy,      ║
   ║             cost, across LOAD LEVELS)                                 ║
   ║      +  demand forecast  +  SLO tiers  +  resource budget             ║
   ║                         │                                            ║
   ║                         ▼                                            ║
   ║   MILP OPTIMIZER  →  EXECUTABLE WORKFLOW (one per valid SLO tier)     ║
   ║                         │                                            ║
   ║                         ▼                                            ║
   ║                  WORKFLOW REGISTRY                                    ║
   ╚═════════════════════════╤════════════════════════════════════════════╝
                             │  deployment plan
                             ▼
   ╔══════════════════════════════════════════════════════════════════════╗
   ║  PHASE 3: EXECUTION            "Continuous" / "Per request"          ║
   ║  ──────────────────────────────────────────────────────────────────  ║
   ║   request(workflow_id | NL query, input, SLO)                        ║
   ║        → registry lookup → dispatch → execute DAG → answer           ║
   ║                                                                      ║
   ║   AUTO-SCALER runs continuously alongside, watching per-model load    ║
   ╚══════════════════════════════════════════════════════════════════════╝
```

Table 1's decision list, which is worth reading closely because several of Part 3's findings are
about the gap between this table and the appendix:

| Phase | Decision | Frequency | Scope |
|---|---|---|---|
| 1 | Workflow DAG structure | Once at onboarding | Workflow |
| 1 | **Executor assignment per DAG node** | Once at onboarding | Workflow — *"Refined per SLO tier by optimizer"* |
| 2 | Final model/tool per executor | Per epoch | (Workflow, SLO) |
| 2 | GPU type and parallelism | Per epoch | (Workflow, SLO) — *"Implicit via model-profile choice"* |
| 2 | Workflow-level knobs | Per epoch | (Workflow, SLO) |
| 2 | Per-model instance count `n_m` | Per epoch | Model — *"Sized for projected peak load"* |
| 3 | Reactive scale-out / scale-in | Continuous | Model |
| 3 | Batch composition | Continuous | Instance |
| 3 | Per-request routing and dispatch | Per request | Request |

---

## 3. Phase 1 — Development

### 3.1 The declarative specification

The developer writes *what* the workflow does, never *how*. Listing 2 in the paper is the full
Video Q/A specification, and it is short enough to reproduce entirely:

```python
# == Sub-tasks in the workflow ==
scene_detect  = "Given a list of videos, identify scenes in each."
frame_extract = "Given a list of scenes, extract frames."
stt           = "Given a list of scenes, convert audio to text."
q_a           = "Answer the query given some context."

# == Workflow description (sub-tasks and data flow) ==
def workflow(query, videos):
    scenes     = scene_detect(videos)
    frames     = frame_extract(scenes)
    transcript = stt(scenes)
    answer     = q_a(query, [frames, transcript])
    return answer
```

Two things to notice, because both matter later.

**First, there is no configuration anywhere.** §3.2 is explicit: *"Configuration details (e.g.,
which LLM to use, number of frames to extract, resource allocation) are omitted from the
specification."* Compare against Listing 1 — the imperative straw-man for the *same* workflow —
which hardcodes `Whisper`, `CLIP`, `Llama-3.2`, `{"num_frames": 15}`, `{"CPUs": 32}`, and
`{"GPUs": 8, "Type": "H100"}` inline. The entire difference between the two listings is what
Murakkab claims to remove.

**Second, this specification has a genuine parallel branch.** `frame_extract(scenes)` and
`stt(scenes)` both consume `scenes` and neither depends on the other; both then feed `q_a`. That
is a fan-out and fan-in, and it is the only one in either of the paper's two headline workflows —
Code Generation is a total order. This becomes important in Part 3.

The paper does allow developers to express preferences: *"Murakkab does not restrict developers
from specifying any execution preferences (e.g., particular LLM choice or hardware constraint),
which are then incorporated into the optimization process as constraints."* So preferences become
optimizer constraints rather than hardcoded values — the decoupling is about *defaults*, not about
forbidding control.

### 3.2 The Executor Library

An **executor** is the unit Murakkab schedules. §3.2 describes the library as spanning existing
ecosystems — *"LLMs and traditional machine learning (ML) models from repositories such as Hugging
Face, as well as tools from open-source libraries and platforms, including OpenAI Agents SDK,
Google Vertex AI Agent Garden, NVIDIA NeMo Agent Toolkits, and Microsoft Azure AI Foundry Tools."*

The key design constraint is that the library is **finite and known**:

> *"A key design choice in Murakkab is mapping a broad range of unknown tasks to executors that
> are built from a finite, known set of models and tools in the library. If none is found,
> Murakkab prompts the developer to onboard a suitable one."*

This is what makes the whole system tractable. An open-ended "any model" space could not be
profiled; a closed catalogue can.

Executors come in three kinds, and the distinction drives a great deal of Part 3:

```
   ┌──────────────┬────────────────────────────┬──────────────────────────┐
   │ KIND         │ EXAMPLES                   │ PROFILED?                │
   ├──────────────┼────────────────────────────┼──────────────────────────┤
   │ LLM          │ Gemma-3-27B, Phi-4,        │ YES — TTFT, TPOT,        │
   │              │ DeepSeek-Qwen-32B          │ throughput, energy       │
   │ COMPOSITION  │ multi-round debate         │ YES — via its LLM        │
   │              │ (D debaters × R rounds)    │ (knobs D and R)          │
   │ TOOL         │ Whisper, OmDet, CLIP,      │ NO — §3.3 profiles       │
   │              │ OpenCV, Python interpreter │ "TTFT and TPOT for LLMs" │
   └──────────────┴────────────────────────────┴──────────────────────────┘
```

### 3.3 The Workflow Orchestrator

> *"The workflow orchestrator transforms a declarative workflow specification into a logical
> workflow. It interprets the specification, parses tasks and sub-tasks, and maps each to an
> appropriate executor from Murakkab's library. At the core is an LLM with tool-calling
> capabilities, which receives a list of available executors and their descriptions..."*

So the mapping from "convert audio to text" to `whisper_stt` is done by an LLM reading executor
descriptions, not by a rule table. The output is the **logical workflow**: a DAG whose nodes are
tasks with assigned executors and whose edges are data dependencies.

Once deployed, *"workflows are exposed to end users via dedicated REST endpoints. Each request may
include an SLO, such as accuracy, latency, or cost tier."*

---

## 4. Phase 2 — Optimization

This is the heart of the system and where almost all of the paper's technical content lives.

### 4.1 Profiles

Murakkab cannot choose a configuration without knowing what each one costs. §3.3 defines two
profile types.

**Workflow profiles** capture quality and load per configuration. Quality is measured on a
benchmark — *"VideoMME, HumanEval, and Math with ground-truth results"*. Load is *"executor-level
load, including prompt and completion tokens for LLM-based executors, serving as a proxy for
resource usage."*

**Model profiles** capture what a model costs on given hardware:

> *"Each profile reports: (1) latency (TTFT and TPOT for LLMs), (2) energy consumption across
> hardware, and (3) cost per configuration."*

And critically:

> *"Profiles span load levels to expose trade-offs and guide the [optimizer]."*

That phrase matters. A model's latency is not one number — it degrades as you push more load
through an instance. Figure 3 plots exactly this: TPOT and TTFT against throughput, for five
models × two GPU types × four tensor-parallelism degrees. A profile is a *curve*, not a point.

```
   Figure 3's shape, for one (model, GPU, TP):

   TPOT ▲                                    ┆ the "knee": beyond here,
   (s)  │                                   ╱┆ latency degrades sharply
        │                                  ╱ ┆
        │                             ____╱  ┆
        │        ____________________╱       ┆
        │   ____╱                            ┆
        └────────────────────────────────────┴──────►  throughput (tokens/s)
                                          θ_m
```

### 4.2 The MILP optimizer

Once per 60-minute epoch, the optimizer takes the logical workflows, the profiles, a demand
forecast, the SLO tiers, and the resource budget, and decides four things (§3.3.1):

> 1. *"**Workflow configuration**: the workflow-level knob settings (e.g., number of frames, STT
>    on/off, debaters and rounds) for each (workflow, SLO)-pair, considering only those feasible
>    under the accuracy and latency SLO."*
> 2. *"**Model/tool provisioning**: the chosen model or tool for each executor in each selected
>    workflow configuration."*
> 3. *"**Resource allocation**: the number of instances `n_m` to launch for each selected model
>    profile `m`. A profile encodes a specific model, GPU type, and parallelism strategy, so
>    choosing `m` implicitly fixes the hardware and parallelism degree."*
> 4. *"**Routing map**: the fraction of load from each (workflow, SLO)-pair routed to each
>    provisioned instance, encoding cross-workflow multiplexing."*

Subject to four constraint families:

> 1. *"**SLO feasibility**: only configurations whose profiled accuracy and latency meet the SLO
>    tier are eligible."*
> 2. *"**Demand satisfaction**: the aggregate routed load to each instance must serve the projected
>    peak demand of the workflows assigned to it, leaving headroom for short-term variance that the
>    auto-scaler absorbs."*
> 3. *"**Capacity**: per-instance load stays within the throughput envelope at which the profile
>    satisfies the latency SLO."*
> 4. *"**Resource budget**: total GPU usage across all provisioned instances respects the available
>    pool per GPU type."*

And one of three interchangeable objectives: minimize energy, minimize cost, or maximize accuracy
under a cost budget.

### 4.3 The key design choice

The paper singles one thing out, and it is the hinge between Phase 2 and Phase 3:

> *"A key design choice is to **decouple peak provisioning from average utilization**: instance
> counts `n_m` are sized for projected peak demand (ensuring SLO compliance), while routing
> fractions are optimized against average demand (driving cost and energy efficiency through
> colocation)."*

Read carefully, this says: **provision for the worst case, route for the common case.** The fleet
is big enough for the peak; the traffic is packed to be cheap on average. The auto-scaler exists
to absorb what falls between.

### 4.4 The formulation itself (Appendix A.5)

The appendix gives the MILP. Its parameters:

```
   λ^peak_{w,s}   peak request rate for workflow w with SLO s
   λ^avg_{w,s}    average request rate
   α              "unified buffer factor (default 1.15)"
   τ_{w,s}        SLO threshold for workflow w and SLO type s
   a_c            accuracy of workflow configuration c
   t_c            tokens per request for configuration c
   θ_m            token throughput (tokens/sec) for model profile m
   ℓ^TTFT_m       time to first token
   ℓ^TPOT_m       time per output token
   g_m            parallelism for model m
   e_m            energy consumption (kWh)
   c_g            "cost per instance per second" for resource type g
   B_g            "maximum available resource instances" of type g
```

Its decision variables:

```
   n_m ∈ Z⁺              number of instances of model profile m
   x^peak_{w,s,c,m} ∈ R⁺  peak load allocation from (w,s,c) to model m
   x^avg_{w,s,c,m} ∈ R⁺   average load allocation
```

And its constraints, verbatim:

```
   (1)  λ^peak ≤ Σ x^peak ≤ α·λ^peak            demand satisfaction, peak
   (2)  λ^avg  ≤ Σ x^avg  ≤ α·λ^avg             demand satisfaction, average
   (3)  μ_m · Σ x^peak · t_c  ≤  n_m · θ_m      capacity, with multiplexing
   (4)  x^peak = 0  if  a_c < τ                 SLO filter, accuracy
   (5)  x^peak = 0  if  ℓ^TTFT + t_c·ℓ^TPOT > τ SLO filter, latency
   (6)  Σ x^avg·(t_c/θ_m)·g_m·c_g ≤ Cost_budget cost budget
   (7)  Σ n_m·g_m ≤ B_g                         resource budget
   (8)–(10)  verbatim duplicates of (4), (5), (6)
   (11) min Σ n_m·e_m·g_m                       minimize energy
   (12) min Σ n_m·g_m·c_g                       minimize cost
   (13) max (Σ x^avg·a_c)/(Σ λ^avg) − ε·Cost_total   maximize accuracy
```

Two observations that are simply facts about the text, not yet criticisms:

**A.5 states four constraints twice.** Equations (8) and (4) are verbatim identical, as are (9)
and (5); (10) is (6) with `Cost_budget` inlined. So thirteen numbered equations are ten distinct
ones. Anyone counting constraints from the numbering will overcount by three.

**`μ_m` is introduced and never defined.** Equation (3) is the only place it appears, and the
paper's complete definition of it is the clause *"where `μ_m` is the model-specific multiplexing
factor."* No value, no bound, no units, no estimation method, in either the OSDI or arXiv version.

The paper also notes that external models fit the same frame: *"Workflows that call proprietary
hosted models (e.g., GPT-4o, Claude) fit the same formulation: such models appear as additional
profiles with fixed per-token cost and latency, no GPU requirement, and provider-imposed rate
limits encoded as capacity constraints."*

Finally, solution method: *"solved using Gurobi with a time limit of 300 seconds."*

---

## 5. Phase 3 — Execution

### 5.1 The request path

> *"At runtime, Murakkab receives incoming requests from end-users with a payload that contains
> the identifier of the agentic workflow being invoked, any input query/data, and the SLOs.
> Murakkab looks up the registry to obtain the corresponding executable workflow and submits it
> for execution."*

An important boundary is drawn here:

> *"The deployment plan does not prescribe per-request dispatch, which remains a runtime
> responsibility. Once an executable workflow is generated for **all valid SLO tiers** of an
> onboarded workflow, it is added to the Murakkab workflow registry and is ready to serve
> requests."*

So the registry is keyed per *(workflow, SLO tier)*, not per workflow — onboarding one workflow
creates several entries.

### 5.2 Dynamic workflow requests

There is a second request shape, and it is more ambitious than the first:

> *"End-users can either invoke a particular agentic workflow or send a request with a natural
> language query, any input data to operate on, and SLOs, **without specifying an agentic workflow
> to use**. The workflow orchestrator parses the query into one or more sub-tasks, mapping each to
> an appropriate executor **or an existing workflow**. Thus, Murakkab dynamically composes
> workflows from existing building blocks available to it."*

This is what §4.6 demonstrates: a request like *"verify the student's coding solution from a
video"* fans out into the Video Q/A workflow and the Code Generation workflow running in parallel.

### 5.3 SLO tiers

> *"We assign four SLO tiers for quality and end-to-end latency: best, good, fair, and basic. The
> SLO tiers correspond to the best, 95th, 80th, and 50th percentile values of accuracy and latency
> available among the set of all workflow, model, and hardware configurations."*

So a tier is not an absolute promise. It is a **percentile of what the current catalogue can
achieve** — which means adding a model to the library shifts every tier.

§4.3 adds an important detail that is easy to miss: *"**We guarantee a basic accuracy tier even
for latency SLO requests** (e.g., 50% for video Q/A)."* A latency request is not allowed to return
arbitrarily bad answers.

### 5.4 The auto-scaler

The auto-scaler's justification is the unpredictability of agentic workloads:

> *"Predicting end-to-end resource usage in agentic workflows is difficult, as input-dependent
> control flow and intermediate outputs propagating along data flows determine actual demand. For
> example, a video Q/A workflow with 10 frames and STT on Llava-OneVision-7B produces 600 and 1200
> tokens in the 50th and 99th percentile, respectively, highlighting high variance."*

A 2× spread in tokens between the median and the tail, for the *same* configuration on the *same*
input type. You cannot provision for that with a static plan.

> *"To handle such variability, Murakkab includes an auto-scaler that monitors per-model instance
> load over short windows (seconds to minutes) and rapidly scales out when needed. The optimizer
> can be configured to be conservative (i.e., consider the tail percentile and provision more
> resources) or optimistic (i.e., consider a more common case and let the auto-scaler handle
> variations in the short-term)."*
>
> *"We set thresholds for auto-scaling based on the performance-throughput characteristic in
> executor profiles. This mechanism prioritizes avoiding SLO violations over short-term allocation
> optimality. Murakkab also maintains spare resources to absorb demand spikes and, when it detects
> significant deviations in workload or resource usage, triggers early re-optimization to adapt
> quickly."*

Four mechanisms in that paragraph: threshold-based scale-out, a conservative/optimistic knob,
spare capacity, and an early re-optimization trigger. Exactly one of them is specified — the
thresholds come from the profile curves of §3.3.

### 5.5 Runtime optimization loop

> *"The optimizer runs in the background after every optimization epoch, in our case every 60
> minutes, to adapt to the most up-to-date load and resource availability in the system. **The
> state of the previous epochs is used to project the load** for each workflow in the next epoch.
> Using this information, the optimizer reconfigures the workflows and updates their executable
> workflows in the registry."*

The projection method is not given in §3.4, but §4.7 supplies it: *"We use an exponentially
weighted moving average (EWMA), with α = 0.5, to predict workload demand at every epoch."*

§4.7 also states the cost of changing your mind: *"Provisioning new instances (i.e., VM
allocation, software setup, and model transfer to GPUs) is assumed to take **20 minutes**."*

---

## 6. How the paper evaluates itself

Understanding the evaluation setup matters, because several findings in Part 3 are about the
relationship between the evaluation and the formulation.

**Hardware** (§4.1): A100 and H100 VMs on Azure, 8 GPUs each. vLLM for LLM serving, speaches-ai
for speech-to-text, OmDet for object detection — three separate serving engines.

**Workload**: 24 hours of Azure LLM inference traces from May 2024, *"chat requests... mapped to
the video Q/A workflow and coding requests to the code generation workflow."*

**Policies compared**:

| Policy | What it is |
|---|---|
| LangGraph (LG) | Hand-crafted baseline, Gemma-3-27B on A100s, no adaptivity |
| LangGraph + Auto | Same, plus Murakkab's own auto-scaler, for fairness |
| **Murakkab Opt** | *"optimizes **each workflow–SLO combination**"* — separately |
| **Murakkab Opt+Mult** | *"**jointly** optimizes requests **across all** workflow–SLO combinations"* |

**Headline result (Table 2)**:

```
   Policy               # GPUs    Energy (MWh)   Cost (×1000 $)
   ─────────────────────────────────────────────────────────────
   LangGraph              2568         82.1           211.7
   LangGraph+Auto         2472         80.6           112.3
   Murakkab Opt           1164         27.7            57.2
   Murakkab Opt+Mult       912         22.1            47.2
   ─────────────────────────────────────────────────────────────
   Opt → Opt+Mult        −21.6%      −20.2%          −17.5%
```

So multiplexing is credited with roughly a fifth of the GPUs on top of what the optimizer already
saves. **Part 3, Finding 1 is about where that 21.6% actually comes from.**

**The multi-workflow experiment (§4.3)**: *"we run video Q/A and code generation requests together
and assign 70% requests to be high-accuracy and 30% requests to low-latency, both with good tier."*

**The scheduling study (§4.6)**: a composite request — *"verify the student's coding solution from
a video, with a 30-second latency SLO"* — that fans out into both workflows. Three configurations
are compared, differing in whether OmDet and Whisper run on GPU or CPU. Murakkab picks the hybrid
(OmDet on GPU, Whisper on CPU) at 5×A100, because *"Whisper's added CPU latency has minimal impact
on end-to-end time."*

**The epoch sensitivity study (§4.7)**: epochs from 20 minutes to 6 hours, producing three cost
zones. Zone 1 (10–60 minutes) is *"Buffer-dominated. Frequent reoptimization induces high
transition overhead. Excessive GPU provisioning during transitions leads to lower utilization...
Frequent model and tool changes can also reduce KV cache efficiency."*

---

## 7. Summary of the design

If you take one picture away from this part, it is this:

```
   THE CONTRACT BETWEEN PHASES

   Phase 1 produces   a DAG with executors assigned      ── structure
   Phase 2 produces   n_m + routing fractions per tier   ── allocation
   Phase 3 produces   answers, and adapts n_m live       ── execution

   The registry is the only interface between 2 and 3.
   The logical workflow is the only interface between 1 and 2.
   Nothing flows backwards.
```

The design is coherent and the phase boundaries are clean. Our implementation confirmed that: the
three phases compose without needing back-channels, and the MILP solves in well under a second on
an open-source solver.

What Part 3 examines is whether **Appendix A.5 can express the system just described.**

<div style="page-break-after: always"></div>

---

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

<div style="page-break-after: always"></div>

---

# Part 3 — What Implementing Murakkab Revealed

*Five findings. Each states the claim, shows the measurement, and separates what is structural
(robust) from what is numeric (banded).*

---

## Finding 1 — A.5's structure produces zero multiplexing gain

### The claim

Murakkab's headline result is that multiplexing cuts GPUs by 21.6%. **Appendix A.5's formulation
cannot produce that gain.** Sharing model instances across workflows — which is what the paper
says multiplexing *is* — saves exactly nothing. The entire reported benefit enters through a
coefficient the paper defines in one clause and quantifies nowhere.

### What the paper says multiplexing is

Two statements, and they point at different things.

§3.3.1, Decision 4, describing what the optimizer produces:

> *"**Routing map**: the fraction of load from each (workflow, SLO)-pair routed to each
> provisioned instance, **encoding cross-workflow multiplexing**."*

So multiplexing is *colocation via the routing map* — packing several workflows' traffic onto
shared instances.

Appendix A.5, equation (3):

```
   μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c  ≤  n_m · θ_m        ∀m ∈ M
```

> *"where `μ_m` is the model-specific multiplexing factor."*

That clause is the paper's complete definition of `μ_m`. No value, no bound, no units, no
estimation method, in either the OSDI or arXiv version. It does not appear in §3.3's list of what
a profile contains.

### The measurement

We separated the two mechanisms the paper reports as one number. Three arms, on the §4.3 setup
(both workflows, 70/30 accuracy/latency, `good` tier), minimising energy:

```
   A. SEPARATE      each (workflow, SLO) solved alone, summed        μ = 1
   B. JOINT         all four solved together, sharing n_m            μ = 1
   C. JOINT + MULT  same problem                                     μ = 0.784

   ┌─────────────────────────────┬──────────┬────────────────────────────┐
   │ A. separate (4 solves)      │  418     │                            │
   │ B. joint, μ=1               │  418     │  sharing gain    +0.00%    │
   │ C. joint, μ=0.784           │  326     │  μ contribution +22.01%    │
   └─────────────────────────────┴──────────┴────────────────────────────┘
                                              combined        +22.01%
                                              paper reports    −21.6%
```

**Arm B minus arm A is exactly zero.** And the zero is not vacuous: in the joint solution,
Phi-4/H100/TP=1 genuinely carried load from *both* workflows simultaneously (n=89). Sharing
happened. It just saved nothing.

### Why it is zero — the structural argument

This is the part that would hold on real hardware, because it follows from the algebra.

Equation (3) is **linear in both `x` and `n`**. The instances a model needs are directly
proportional to the token demand landing on it. So:

```
   SEPARATE:   n = ceil(d₁/θ)  +  ceil(d₂/θ)
   JOINT:      n = ceil((d₁ + d₂)/θ)

   difference ≤ 1 instance per shared model  ── integrality rounding, nothing more
```

There is no statistical smoothing term, no queueing model, no burstiness parameter. Pooling two
workflows' demand onto one instance count saves only the fractional instance you would otherwise
round up twice. At this scale that is under one percent, and here it happened to be exactly zero.

**So A.5 has no mechanism by which colocation produces a resource saving.** The structure the
paper describes in §3.3.1 (routing map encoding multiplexing) is present, and it does nothing.

### Where the 21.6% comes from, and the circularity

If the structure cannot produce the gain, `μ_m` must. And `μ_m` is undefined — so we had to obtain
it somehow. The only source in the paper is Table 2 itself:

```
   Table 2 (verified cell by cell):
     Murakkab Opt        1164 GPUs    27.7 MWh    $57.2k
     Murakkab Opt+Mult    912 GPUs    22.1 MWh    $47.2k
                        −21.6%       −20.2%      −17.5%

   Under three stated assumptions, n_m scales with μ, so:
     μ = 1 − 0.216 = 0.784   [OSDI]
     μ = 1 − 0.211 = 0.789   [arXiv]
```

This is a legitimate `DERIVED` value — it is inferred from a published number under stated
assumptions, not invented. **But the calibration is then spent.** Reproducing 21.6% using a `μ`
fitted to 21.6% is arithmetic, not validation. Our implementation stamps every such result
`CALIBRATION SPENT` and refuses to present it as a reproduction.

We measured 22.01% against a fitted target of 21.6%; the 0.4-point gap is integrality rounding,
and it confirms only that the arithmetic is consistent.

### The deeper problem: `μ_m` is a parameter of the wrong object

Statistical multiplexing gain depends on **how many independent streams share an instance and how
bursty they are**. Those are properties of the *assignment* — of `x` — not of the model. A.5 makes
`μ` a parameter of `m` alone, so the gain is **exogenous**: the optimizer is told the answer rather
than deriving it from the sharing it chooses.

And there is an algebraic identity that makes this sharp:

```
   μ_m · Σ(...)  ≤  n_m · θ_m          is identical to
        Σ(...)  ≤  n_m · (θ_m / μ_m)
```

**Scaling `μ` is indistinguishable from scaling throughput.** Multiplexing, in A.5, is a
throughput bonus under a different name. We have a test that demonstrates this: setting μ = 0.5
halves the fleet exactly as doubling θ would.

### One more inconsistency

Table 2 reports three reductions: 21.6% GPUs, 20.2% energy, 17.5% cost. **No single uniform `μ`
reproduces all three.** If one coefficient explained the gain, all three would move together. They
do not, and the spread measures how much of the reported benefit is *not* capacity sharing.

### Confidence

- **Structural (robust):** eq. (3) is linear ⇒ colocation saves only integrality rounding. `μ`
  is algebraically a throughput scalar. Both follow from the text.
- **Measured (banded):** the 418 → 418 → 326 figures come from reconstructed profiles.
- **Verified:** Table 2's cells, §4.1's definitions of the two policies, eq. (3) verbatim.

---

## Finding 2 — eq. (5)'s blind spot is worth 0.3% or 69%, depending entirely on token count

### The claim

Equation (5) is Murakkab's *entire* model of end-to-end latency. It omits several real sources of
delay. **How much that matters varies by two orders of magnitude between the paper's own two
workflows**, and the discriminator is `t_c`. A single claim about "Murakkab's latency model" is too
coarse to be useful.

### What eq. (5) is

```
   x^peak = 0   if   ℓ^TTFT_m + t_c · ℓ^TPOT_m  >  τ_{w,s}
                     └────────┬──────────────┘
                     one model's time-to-first-token
                     plus its per-token time times the
                     WHOLE configuration's token count
```

What it contains: one prefill, one token stream, on one model.

What it does not contain: a sum over sub-tasks, a max over parallel branches, any term a tool
could occupy, or any notion of queueing.

### The measurement

We ran one request end to end through each workflow, walking the DAG and recording per-node
timings, then set the observed span beside what eq. (5) charged.

```
   VIDEO Q/A  (NVLM-D-72B/H100/TP=8, STT on, t_c = 194 tokens)

     scene_detect   ██                            2.0 s   TOOL  ← free to A.5
     frame_extract    █                           1.0 s   TOOL  ← free
     stt              ████                        4.0 s   TOOL  ← free
                          ▲ these two overlap; q_a waits for max(1,4)
     q_a                  ███                     2.74 s  LLM   ← all A.5 sees
     ──────────────────────────────────────────────────
     observed span                                8.74 s
     eq. (5) sees                                 2.74 s
     ══════════════════════════════════════════════════
     BLIND SPOT                                     69%


   CODE GENERATION  (DeepSeek-Qwen-32B/H100/TP=4, D=4 R=4, t_c = 39,969 tokens)

     propose_solutions  ████████████████████████ 16 LLM calls
     write_tests        ██                        1 LLM call
     execute_tests      ·                         0.8 s  TOOL  ← free to A.5
     rank_solutions     █                         1 LLM call
     ──────────────────────────────────────────────────
     observed span                             1550.69 s
     eq. (5) sees                              1547.02 s
     ══════════════════════════════════════════════════
     BLIND SPOT                                   0.24%
```

### Why the difference — and why this is the interesting part

The omissions are the *same* in both cases: the tool stages cost nothing, and eq. (5) charges one
prefill where the request pays many. What differs is the size of the term that *is* modelled.

```
   eq.(5)  =  ℓ^TTFT  +  t_c · ℓ^TPOT
              └──┬──┘     └─────┬────┘
              ~0.2 s       dominates when t_c is large

   Video Q/A:     0.24  +    194 × 0.0129  =  2.74 s   ← small; omissions dominate
   Code Gen:      0.22  + 39,969 × 0.0387  = 1547 s    ← huge; omissions vanish
```

When a configuration generates forty thousand tokens, a few seconds of tool time and seventeen
extra prefills disappear into rounding. When it generates two hundred, they are most of the
latency.

**This is why the choice of demonstration workflow matters so much**, and why Code Generation —
the workflow originally scoped for our end-to-end milestone — is the worst possible case for
showing the defect.

### Robustness

Video Q/A's 69% rests partly on tool service times that have **no paper source** and are marked
`INVENTED` in a quarantined module (the paper profiles no tool latency at all). So we tested the
conclusion across the full ±3× band those values carry:

```
   tool times ÷ 3   →  blind spot 42%
   tool times × 3   →  blind spot 87%
```

The conclusion survives the entire band. It rests on the *structure* — small `t_c`, three tool
stages — not on the magnitudes we chose.

### The sub-finding: the prefill undercount

Equation (5) charges exactly one `ℓ^TTFT_m`. A `D=4, R=4` Code Generation request makes 16 debate
calls plus test-writing plus ranking — **18 LLM invocations**, each paying a prefill.

```
   ttft_undercount = (invocations − 1) × ℓ^TTFT_m = 17 × 0.216 s = 3.67 s
```

This is the cleanest defect in the comparison: integers times a profiled value, no invented
magnitude anywhere. It is also **0.2%–2.6%** of eq. (5) across every Code Generation profile, for
the same reason as above. Real, exact, and not worth leading with — we corrected an earlier draft
that called it the milestone's strongest result.

### Confidence

- **Structural (robust):** eq. (5) has no per-node sum, no max over branches, no queueing term,
  and charges one prefill. These are facts about the equation.
- **Measured (banded):** 69% and 0.24%. The 69% survives ±3× on invented inputs.
- **Corrected:** the parallel-branch overlap is real (Listing 2) but §4.6's "full overlap"
  sentence describes two composed *workflows*, not these two nodes.

---

## Finding 3 — The auto-scaler cannot do what §3.4 claims

### The claim

§3.4 describes an auto-scaler that reacts on a seconds-to-minutes timescale. §4.7 assumes
provisioning takes twenty minutes. **These cannot both be true of a component that absorbs
short-term variance**, and the paper never reconciles them.

### The two sentences

> §3.4: *"an auto-scaler that monitors per-model instance load over **short windows (seconds to
> minutes)** and **rapidly scales out** when needed."*

> §4.7: *"Provisioning new instances (i.e., VM allocation, software setup, and model transfer to
> GPUs) is assumed to take **20 minutes** [31, 38, 62]."*

### The measurement

Same deployment plan, same load, same thresholds. Only the provisioning delay changes. The load is
a 2.5× spike lasting 200 seconds — shorter than the delay, which is the *normal* case for the
Azure traces the paper uses.

```
   load  ────┐                    ┌────────────────────────
             │                    │
             │   2.5× spike       │
             └────────────────────┘
             ▲          ▲         ▲
             │          │         └── spike ends
             │          └── autoscaler detects (60 s window), orders capacity
             │
             └── t = 200 s
                        └──────────── 20 minutes ─────────────► capacity arrives
                                                                (spike long over)

   ┌────────────────────────────────┬───────────────────────┐
   │ 20-min provisioning (§4.7)     │  81.5% SLO violations │
   │ instant provisioning (not the  │  36.5% SLO violations │
   │   paper's assumption)          │                       │
   └────────────────────────────────┴───────────────────────┘

   In the 20-minute case the scaler DID react:
     7 scale-out events · 49 instances requested and granted
     141,680 GPU-seconds burned on capacity that arrived too late to help
```

**During any spike shorter than twenty minutes, the auto-scaler is worse than useless.** It pays
for capacity that is never used.

### The only reconciliation, and why it does not close

The gap can only be bridged by capacity that already exists — pre-warmed spare. §3.4 names it:

> *"Murakkab also **maintains spare resources** to absorb demand spikes..."*

And never sizes it. There is no spare-capacity parameter in A.5: `B_g` is a hard budget and `α` is
a demand buffer, neither of which is idle standby capacity. So the auto-scaler's entire
responsiveness claim rests on a quantity that appears once in prose and nowhere in the model.

We default spare to **zero**, because zero is the formulation's own answer and any other value
would be repairing the contradiction rather than exhibiting it.

### A second runtime finding from the same experiment

In the same run, violations attributable to **queueing** outnumbered those attributable to token
variance by more than ten to one:

```
   violations from queueing        12,451
   violations from token variance   1,119
```

Equation (5) admits a configuration on `ℓ^TTFT + t_c·ℓ^TPOT ≤ τ` with **no queueing term at
all**. So the dominant cause of SLO violation at runtime is latency the optimizer structurally
cannot model. A plan can be feasible on paper and violate its SLO in the run purely through
waiting.

### Confidence

- **Structural (robust):** 20 minutes > 60 seconds. A.5 has no spare-capacity parameter. eq. (5)
  has no queueing term. All verifiable from the text.
- **Measured (banded, simulated):** 81.5% vs 36.5%. This is a simulator with an `[OURS]` FIFO
  queueing model and no batching or KV cache. The *ratio* between the two arms is the finding; the
  absolute violation rate is not a prediction about production.

---

## Finding 4 — The appendix is systematically narrower than the paper

### The claim

This is the most reusable observation from the project. It is not one defect but a **pattern**:
six distinct capabilities are described in the paper's prose and exercised in its evaluation, and
none of them can be written in Appendix A.5.

### The table

| What the paper describes | Where | What A.5 encodes | Gap |
|---|---|---|---|
| Agents *"may employ the same or different LLMs"* | §2.2 | one `m` per configuration | no per-node index |
| *"the chosen model or tool **for each executor**"* | §3.3.1, Decision 2 | one `m` per configuration | same |
| Executor assignment *"refined per SLO tier by optimizer"* | Table 1 | same | same |
| *"throughput envelope at which the profile satisfies the latency SLO"* | §3.3.1, Constraint 3 | `θ_m` is a **constant** | SLO-dependence lost |
| *"routing map … encoding cross-workflow multiplexing"* | §3.3.1, Decision 4 | a coefficient `μ_m` | mechanism unnamed (Finding 1) |
| *"We guarantee a basic accuracy tier even for latency SLO requests"* | §4.3 | one `τ` per `(w,s)` | cannot express two floors |
| CPU offload of Whisper and OmDet | §4.6, Figs 12b/12c | `G` is GPU-only | no CPU resource type |
| Transition overhead dominates Zone 1 | §4.7 | no switching cost | no inter-epoch coupling |

### Three of these in detail

**Per-node model assignment.** Three separate places promise it, including the paper's own
description of its flagship workflow: *"Each agent plays a unique role (e.g., algorithm developer,
unit tester) and **may employ the same or different LLMs**."* Against that: `x_{w,s,c,m}` has one
model index, and Table 6 prints one Model column per row — four debating agents, one model. The
capability is described three times and delivered zero times.

The reason is deeper than a missing index. **Murakkab decides at executor granularity and profiles
at configuration granularity.** Accuracy `a_c` is measured for a whole configuration running on
one model (Figure 2c, Table 6). There is no data for a mixed assignment, and there are 5³
combinations to measure for Code Generation alone. The profiling methodology cannot supply what
the decision requires — which is why our own reproduction was forced to fold the model *into* the
configuration knobs.

**SLO-dependent throughput.** §3.3.1 says the capacity envelope is *"the throughput envelope at
which the profile satisfies the latency SLO."* That makes `θ` a function of the tier. A.5 makes it
a constant `θ_m`. The consequence is measurable: Tables 5 and 6 report the *same*
`(model, GPU, TP)` at up to four different `(TPOT, TPS)` operating points — Phi-4/H100/TP=1 appears
at (0.0373, 757), (0.0165, 248), (0.0253, 552) and (0.0372, 755). A.5 can hold one. Choosing
which collapses a 6.8× throughput range on one profile, and every GPU count moves with it.

**Inter-epoch coupling.** §4.7 builds an entire sensitivity analysis on transition overhead —
*"Zone 1 (10–60 minutes): Buffer-dominated. Frequent reoptimization induces high transition
overhead… Frequent model and tool changes can also reduce KV cache efficiency."* A.5 has no
switching cost, no warm-start term, no minimum instance lifetime. Our optimizer will legally tear
down an entire fleet between two adjacent hours at zero modelled cost, and we measure the churn
because the formulation cannot see it.

### Why this framing is better than a list of bugs

Calling these "errors in the appendix" understates them. The paper's *system* is richer than its
*model of the system*. Every one of these is a place where the authors clearly understood
something — they evaluated it — and the formulation they published cannot represent it.

For anyone building on Murakkab, this is the most actionable finding in the report: **the
improvements are not new ideas, they are making A.5 encode what Sections 2–4 already say.** Part 4
develops that.

### Confidence

- **Structural (robust).** Every row is a comparison between two pieces of the paper's own text.
  Verified verbatim on 2026-09-13.

---

## Finding 5 — The `c`/`m` decoupling is exploited, not latent

### The claim

A.5 has no constraint linking a workflow configuration to the model profile serving it. This is
not a theoretical gap. Under the baseline profile set, **100% of allocated mass exploited it** —
and in the worst way available.

### The mechanism

```
   x^peak_{w,s,c,m}
                ▲ ▲
                │ └── model profile:  (Phi-4, H100, TP=1)
                └──── configuration:  (F=10, model=Gemma-3-27B, STT on)

   Nothing requires these to name the same model.
   The optimizer claims Gemma's accuracy a_c while paying Phi-4's θ, ℓ and e.
```

### The measurement

On `baseline`, video_qa, accuracy-`best`, minimising energy:

```
   incoherent mass: 100.0% of allocation
     62.69 req/s of video_qa(F=10, model=Gemma-3-27B, STT on)
       routed onto Phi-4/H100/TP=1
```

And it is worse than an accuracy mismatch. **Phi-4 appears in no Video Q/A configuration at all** —
it is a Code Generation model. A.5's `M` is a global set with nothing tying it to the workflow's
own `C_w`, so the formulation permits serving a video question-answering workflow on a text-only
LLM while claiming the multi-modal model's accuracy.

### Why the optimizer does this

Because it is rewarded for it. Phi-4/H100/TP=1 delivers 757 tokens/s **per GPU**;
DeepSeek-Qwen-32B/H100/TP=4 delivers 347.5. A cost- or energy-minimising objective will take the
cheaper throughput and keep the expensive accuracy every time, because no constraint connects
them.

### What we did about it

Nothing — deliberately. Adding `c.model == m.model_id` is a one-line fix and it is improvement #3
in Part 4. Under the standing policy we built a *measurement* instead, quarantined from the
optimizer by test, so that the defect is quantified rather than absorbed.

**Either outcome would have been a finding.** A zero would have meant the defect is latent under
this profile set — not that A.5 is sound. That it is 100% means the formulation is not merely
under-specified but actively exploitable by its own objectives.

### Confidence

- **Structural (robust):** A.5 contains no such constraint; `M` is global. Verifiable from the
  appendix.
- **Measured:** the 100% figure depends on our reconstructed throughput values. The *direction* —
  that a cost-minimising optimizer will exploit the gap — follows from the objective's shape.

---

## Summary: what the implementation bought us

Reading the paper gives you the architecture. Implementing it gives you five things reading cannot:

1. **The multiplexing result has no mechanism behind it.** You cannot see this by reading eq. (3);
   you see it by building the joint solve and measuring zero.
2. **The latency-model defect is workload-dependent by two orders of magnitude.** Reading gives
   you "eq. (5) is too simple"; implementing gives you "and it matters enormously here and not at
   all there, and here is why."
3. **The auto-scaler's two timescales are incompatible.** Both numbers are in the paper, in
   different sections, and nothing connects them on the page.
4. **The appendix is narrower than the paper** — visible only when you try to write code for the
   prose and find there is no variable for it.
5. **The `c`/`m` gap is exploited, not latent** — a fact about the optimum, obtainable only by
   solving.

Every one of these came from the discipline of *refusing to fix things*. An implementation that
repaired eq. (5), linked `c` to `m`, and picked a sensible `μ` would be a better system and would
have found none of this.

<div style="page-break-after: always"></div>

---

# Part 4 — Improving Murakkab, From Inside Murakkab

*Ten improvements. Each is traceable to a sentence the paper already contains, expressed in A.5's
own vocabulary, and measurable against the literal baseline we built.*

---

## The organising principle

The strongest improvements here are **not new ideas**. They are:

> **Make Appendix A.5 encode what Sections 2–4 already claim.**

This matters for three reasons.

**It is comparable.** An improvement expressed in A.5's own symbols can be measured against the
literal A.5 we implemented — same profiles, same solver, same traces, one term different. An
improvement that imports a different architecture cannot.

**It is defensible.** Every change below cites a paper sentence. None of them requires arguing
that Murakkab *should* have done something; they argue that Murakkab *said* it did and the
formulation does not.

**It is bounded.** These are edits to a MILP, not a redesign. Most are a new index, a new
parameter, or a constraint the paper's prose already describes.

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  WHAT THE PAPER SAYS  ──────────────►  WHAT A.5 ENCODES         │
   │        (Sections 2–4)                      (Appendix A.5)        │
   │                                                                  │
   │              └──────────── the gap ───────────┘                  │
   │                             │                                    │
   │                             ▼                                    │
   │              THIS IS WHERE THE IMPROVEMENTS LIVE                 │
   └─────────────────────────────────────────────────────────────────┘
```

---

## The ten, ranked

| # | Improvement | Traceable to | Effort | Measurable gain |
|---|---|---|---|---|
| **1** | Peak-coincidence multiplexing | §3.3.1 Decision 4 | Medium | Makes 21.6% falsifiable |
| **2** | SLO-indexed throughput `θ_{m,s}` | §3.3.1 Constraint 3 | Low | Removes a 6.8× artifact |
| **3** | Coherence constraint | A.5 has none | Trivial | Eliminates 100% incoherent mass |
| **4** | SLO filters on `x^avg` | §3.3.1's peak/avg intent | Trivial | Closes objective (13)'s hole |
| **5** | Basic-accuracy floor on latency runs | §4.3 verbatim | Low | Matches described behaviour |
| **6** | Per-node executor index | §2.2 + Dec. 2 + Table 1 | Medium | 10.8–17.9% (banded) |
| **7** | Precedence + makespan | §4.6, Listing 2 | High | 69% of latency on Video Q/A |
| **8** | Spare capacity parameter | §3.4 "spare resources" | Low | Attacks 81.5% violation rate |
| **9** | Inter-epoch switching cost | §4.7 Zone 1 | Medium | Makes churn visible |
| **10** | CPU resource type | §4.6 Figs 12b/12c | Medium | Reproduces paper's own best config |

---

## 1. Replace `μ_m` with peak-coincidence modelling

**The problem.** Finding 1: A.5's structure produces zero multiplexing gain, and the entire
reported 21.6% enters through a coefficient that is undefined, unbounded, and algebraically
indistinguishable from scaling throughput. Worse, the only way to obtain it is to fit it to the
number it is supposed to explain.

**Where the real gain actually lives.** Equation (3) sums over `x^peak` — the *peak* rate of each
workflow:

```
   A.5 charges:        Σ_w  peak(w)        ← sum of peaks
   Reality is:         peak( Σ_w w )        ← peak of the sum
```

Those differ precisely when workflows peak at *different times*. The sum-of-peaks formulation
assumes every workflow peaks simultaneously — the worst case — and therefore provisions as though
colocation buys nothing. **Which is exactly what we measured.**

Statistical multiplexing gain *is* the difference between those two quantities. It is not a
coefficient; it is a property of the arrival traces.

**The change, in A.5's vocabulary.** Replace eq. (3)'s left side:

```
   BEFORE   μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c   ≤  n_m · θ_m

   AFTER    max_over_epochs( Σ_{w,s,c} x_{w,s,c,m}(t) · t_c )  ≤  n_m · θ_m
```

**Why this is strictly inside Murakkab.** §3.3.1 already says the routing map *"encodes
cross-workflow multiplexing."* This makes that true. And Figure 19's 24-hour traces — the chat and
coding series — are already in the repository, so the coincidence structure is computable today
with no new data.

**What it buys.** Multiplexing becomes **derived from the routing the optimizer chooses**, instead
of inserted through a fitted constant. Table 2's 21.6% turns from an assertion into a prediction
you can be wrong about. That is the single most valuable change on this list.

**Caveat worth stating.** The gain may come out well below 21.6%. Chat and coding traces may be
strongly correlated, in which case peak-coincidence multiplexing is worth little — and *that*
would also be a finding, because it would mean the reported number needs a different explanation.

---

## 2. Make throughput SLO-indexed: `θ_m → θ_{m,s}`

**The problem.** §3.3.1's third constraint says capacity means *"per-instance load stays within
the throughput envelope at which the profile satisfies the latency SLO."* That makes the envelope
a function of the tier. A.5 makes `θ_m` a constant.

**Evidence this is a real loss, not a quibble.** Tables 5 and 6 report the *same*
`(model, GPU, TP)` tuple at up to four different operating points:

```
   Phi-4 / H100 / TP=1, as reported by Table 6:
      accuracy-energy-basic   TPOT 0.0373   TPS  757
      latency-energy-good     TPOT 0.0165   TPS  248
      latency-energy-fair     TPOT 0.0253   TPS  552
      latency-energy-basic    TPOT 0.0372   TPS  755

   A.5 can hold ONE of these.
```

The paper is explicit about why in A.2: the system *"increases the allowed load per model instance
to increase batching as the SLO is relaxed."* So the operating point **is** SLO-dependent, by the
paper's own account, and the appendix discards that.

On Llava-OneVision-7B/H100/TP=4 the reported throughputs span 479 → 3271 tokens/s — a **6.8×
range** from Table 5's own rows. Which point you collapse to moves every GPU count by that factor.
In our implementation this is the single largest sensitivity knob.

**The change.** Index throughput and per-token latency by SLO tier: `θ_{m,s}`, `ℓ^TPOT_{m,s}`. The
profile data already supports it — it is literally what Tables 5/6 report.

**What it buys.** Removes the largest measurement artifact in the system, and lets the optimizer
do what A.2 says it does: trade batching against latency as the SLO relaxes.

---

## 3. Add the coherence constraint

**The problem.** Finding 5: 100% of allocated mass routed a Video Q/A configuration onto Phi-4, a
model that appears in no Video Q/A configuration at all.

**The change.** One line:

```
   x_{w,s,c,m} = 0   if   model(c) ≠ model(m)
```

**Why it is inside Murakkab.** This is not adding a capability — it is enforcing something the
paper clearly assumes. Tables 5 and 6 report a Model column *per configuration*; the notion that a
configuration's accuracy could be claimed while a different model serves it is never contemplated
in the prose. The gap is an artefact of the index structure, not a design decision.

**What it buys.** Every accuracy number the optimizer reports becomes achievable. Note it will make
results *worse* on paper — the optimizer loses a cheat — and that is the point: the current numbers
are partly obtained by exploiting it.

---

## 4. Apply the SLO filters to `x^avg`

**The problem.** Equations (4) and (5) constrain `x^peak` only. `x^avg` appears in equations (2),
(6)/(10) and objective (13) — **none of which is a filter**. So objective (13), which maximises
`Σ x^avg · a_c`, may place average load on configurations whose accuracy is below the very
threshold the run is named after.

```
   x^peak  ──► filtered by eq.(4) accuracy, eq.(5) latency   ✓
   x^avg   ──► eq.(2) demand · eq.(6) cost · obj.(13) accuracy
               └─────────── NO FILTER ANYWHERE ───────────┘
```

The objective that optimises quality is the one the quality filter does not reach.

**The change.** Extend the filters to both variables, or restrict `x^avg`'s domain to the
SLO-admissible set.

**Why it is inside Murakkab.** §3.3.1's first constraint says *"only configurations whose profiled
accuracy and latency meet the SLO tier are eligible."* Eligibility is a property of the
configuration, not of which variable references it. The appendix simply wrote the filter on one of
two variables.

---

## 5. Add the basic-accuracy floor on latency runs

**The problem.** §4.3 states, verbatim: *"We guarantee a basic accuracy tier even for latency SLO
requests (e.g., 50% for video Q/A)."* A.5 gives one `τ_{w,s}` per pair and scopes eq. (4) to
`s = max_accuracy`, so on a latency-tier run there is no accuracy constraint at all.

**The change.** Give each `(w,s)` two thresholds rather than one:

```
   BEFORE   τ_{w,s}              one number, dimension depends on s
   AFTER    τ^acc_{w,s}          accuracy floor  — always active
            τ^lat_{w,s}          latency ceiling — always active
```

**Why it is inside Murakkab.** This is the improvement with the least interpretive distance of any
on the list: the paper *says* it does this. Our implementation does not, because we reproduced the
formulation rather than the described behaviour — which is faithful, and also a divergence from
the system §4.3 evaluates.

**What it buys.** The implementation starts matching the paper's described behaviour. It also
closes a real hole: without it, a latency-tier run may legally select the worst configuration in
`C_w`.

---

## 6. Per-node executor assignment

**The problem.** Three places promise per-executor model choice — §2.2 (*"may employ the same or
different LLMs"*), §3.3.1 Decision 2 (*"for each executor"*), and Table 1 (*"refined per SLO tier
by optimizer"*). `x_{w,s,c,m}` has one model index.

**The change.** Add a node index:

```
   BEFORE   x_{w,s,c,m}
   AFTER    x_{w,s,c,v,m}        v ∈ nodes(DAG_c)

   plus a consistency constraint: each node's assigned mass equals the request rate.
```

**The concrete opportunity.** Code Generation's nodes do very different work:

```
   propose_solutions   the debate — where accuracy is created   → needs the strong model
   write_tests         generating unit tests                     → middling
   rank_solutions      picking the highest-voted candidate       → a tallying job

   DeepSeek-Qwen-32B/H100/TP=4   91.61% accuracy   347.5 tokens/s per GPU
   Phi-4/H100/TP=1               67.20% accuracy   757.0 tokens/s per GPU
                                                   └─ 2.2× more efficient
```

Under A.5 you must pick one model for the entire workflow, so choosing the accuracy means the
*ranking* step also runs on the expensive model. Moving a fraction *f* of tokens to Phi-4 saves
`f × (1 − 347.5/757) = f × 0.541`:

```
   ranker is 20% of tokens   →  10.8% fewer GPUs
   ranker + tests are 33%    →  17.9% fewer GPUs
```

**The honest blocker.** That band cannot be narrowed from the paper's data, for two reasons, and
both come from the same root:

```
   DECIDES at executor granularity      PROFILES at configuration granularity
   (§3.3.1 Decision 2)                  (§3.3, Figure 2c, Table 6)
        ┌─────────┐                          ┌──────────────────────┐
        │ propose │ ← pick m                 │  whole configuration │
        │ tests   │ ← pick m                 │  a_c = 91.61 %       │
        │ rank    │ ← pick m                 │  t_c = 39,969 tokens │
        └─────────┘                          └──────────────────────┘
              ▲                                          ▲
              └──────────── MISMATCH ───────────────────┘
```

There is no published per-node token split, and no accuracy measurement for mixed assignments.
**Implement the formulation change and report the band**; closing it needs measurement, which
needs GPUs.

---

## 7. Precedence and makespan

**The problem.** Finding 2: eq. (5) models a workflow as one serialised token stream on one model.
Listing 2's Video Q/A has a genuine fan-out, and the observed span is 69% latency the formulation
cannot see.

**The change.** Replace the single-stream filter with a critical path over the DAG:

```
   BEFORE   ℓ^TTFT_m + t_c · ℓ^TPOT_m  ≤  τ

   AFTER    makespan(c, m) ≤ τ,  where
            makespan = max over paths of Σ node durations
                     = L_scene + max(L_frames, L_stt) + L_qa    (Video Q/A)
```

**Why it is inside Murakkab.** The DAG already exists — Phase 1 produces it and the registry
carries it. Nothing new is imported; the optimizer is simply allowed to read a structure the
system already has. §4.6 measures parallel execution empirically, so the capability is one the
paper demonstrates.

**Effort and honesty.** This is the largest change on the list, and it needs per-node durations,
which need a per-node token split (see #6's blocker). On Video Q/A this is tractable — there is
one LLM node, so the split is exact. On Code Generation it is not.

**This is also where your own architecture's contribution lives**, so it is worth doing carefully
rather than quickly.

---

## 8. Give spare capacity a parameter

**The problem.** Finding 3: the auto-scaler's 60-second monitoring window cannot be answered by a
20-minute provisioning delay. §3.4 says Murakkab *"maintains spare resources to absorb demand
spikes"* and never sizes them. A.5 has nowhere to put one — `B_g` is a hard budget, `α` is a demand
buffer.

**The change.** Add `σ_g` (spare fraction) as a first-class parameter, and let the optimizer size
it against the projected variance rather than treating it as a constant:

```
   eq.(7)  becomes   Σ n_m · g_m  +  spare_g  ≤  B_g
                     with spare_g sized from the token distribution's p99/p50 spread
```

**Why it is inside Murakkab.** §3.4 already motivates the auto-scaler entirely with the p50/p99
token spread (*"600 and 1200 tokens… highlighting high variance"*). The data to size spare capacity
is the data already used to justify the component.

---

## 9. Add an inter-epoch switching cost

**The problem.** A.5 has no coupling between epochs — no warm start, no switching cost, no minimum
instance lifetime. So the optimizer may legally tear down an entire fleet between two adjacent
hours at zero modelled cost. Meanwhile §4.7 builds a whole sensitivity analysis on exactly that
overhead:

> *"Zone 1 (10–60 minutes): Buffer-dominated. Frequent reoptimization induces high transition
> overhead. Excessive GPU provisioning during transitions leads to lower utilization… Frequent
> model and tool changes can also reduce KV cache efficiency."*

**The change.** Add a term penalising `|n_m(e) − n_m(e−1)|`, priced at the 20-minute provisioning
cost §4.7 already assumes.

**What it buys.** Figure 13a's three-zone structure becomes *derivable* from the formulation rather
than measured around it. Right now the optimizer cannot see the cost that defines Zone 1.

---

## 10. Add a CPU resource type

**The problem.** §4.6's *chosen* configuration — the one Murakkab selects as most efficient — runs
OmDet on GPU and Whisper on CPU. A.5's resource set `G`, budget `B_g`, cost `c_g` and constraint
(7) are GPU-only. The paper's own best answer is not expressible in the paper's own model.

**The change.** Extend `G` to include CPU, with its own `B_g`, `c_g` and a capacity relation
appropriate to CPU serving.

**Prerequisite.** This only becomes meaningful alongside profiling tools at all — currently
Whisper, OmDet, CLIP and OpenCV have no profile of any kind, so they contribute zero to every
constraint. Giving tools a profile is the enabling step, and it is also what makes #7 produce real
numbers instead of invented ones.

---

## Suggested sequence

```
   PHASE A — cheap, high signal, no new data needed
   ├── 3. coherence constraint            (one line)
   ├── 4. filters on x^avg                (one line)
   └── 5. basic-accuracy floor            (one parameter)
        └─► these three make the baseline match the described system

   PHASE B — the headline
   ├── 2. SLO-indexed θ                   (removes the 6.8× artifact first)
   └── 1. peak-coincidence multiplexing   (the falsifiability result)
        └─► do 2 before 1, or the μ measurement inherits the θ artifact

   PHASE C — the architectural contribution
   ├── tool profiling                     (enabling step)
   ├── 7. precedence + makespan
   └── 6. per-node assignment
        └─► where your own system's thesis lives

   PHASE D — runtime realism
   ├── 8. spare capacity
   ├── 9. switching cost
   └── 10. CPU resource type
```

**Do #2 before #1.** The operating-point collapse is a 6.8× lever on `θ_m`; measuring a
multiplexing gain on top of that artifact would confound the two.

**One prerequisite before any of it:** validate the reproduction against Tables 1–6 and Figures
7–14. An improvement measured against an unvalidated baseline is not measurable. That work is
scoped and not yet done, and it is the only remaining thing that could invalidate the findings
these improvements rest on.