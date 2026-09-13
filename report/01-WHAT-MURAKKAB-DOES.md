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
