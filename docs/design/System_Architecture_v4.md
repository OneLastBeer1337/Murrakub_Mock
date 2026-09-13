# System Architecture and Detailed Design — v4

**Recreating Murakkab: Resource-Efficient Multi-Workflow Orchestration with an Adaptive Closed Loop**

*Supersedes `System_Architecture_v2.md` and replaces/retracts `System_Architecture_v3.md`.*  
*Ratified following supervisory consultation on 7 September 2026.*

---

## 0. Executive Summary & Consultation Directive

### 0.1 The Consultation Mandate: Scope Lock to Murakkab
Following supervisory consultation on 7 September 2026, the project received unambiguous guidance:
> *"Recreate the Murakkab paper because we would not want to go too far away from scope. Draft a v4."*

This directive decisively halts the ungrounded API-rate-limit detour attempted in `System_Architecture_v3.md` (which had introduced per-token pricing, TPM/RPM limits, and prompt engineering knobs). That divergence broke the mathematical foundation, discarded the 12-paper literature network, and abandoned the project's empirical baseline.

**System Architecture v4 re-anchors the platform firmly on [Murakkab (Chaudhry et al., 2026, OSDI '26)](file:///d:/intern/EnterpriseOrches/docs/research_papers/papers.json#L184-L227).** The project's primary mission is to replicate Murakkab's capacity provisioning model, reproduce its core fleet-scale efficiency claims, and deliver the **adaptive closed loop** that Murakkab explicitly omitted.

### 0.2 System Lineage & Comparison

| Dimension | Murakkab (OSDI '26) | System Arch v2 (Design of Record) | System Arch v3 (Retracted Detour) | **System Arch v4 (Recreating Murakkab)** |
|---|---|---|---|---|
| **Problem Class** | Capacity-constrained multi-tenant allocation | Modular Capacitated Facility Location | Multi-knob API-rate knapsack | **Modular Capacitated Facility Location (Murakkab model)** |
| **Resource Model** | Provisioned instances ($n[m]$) across heterogeneous hardware (A100, H100, CPU) | Provisioned instances ($n[m]$) under GPU budget $B$ | Pay-per-token API quotas (TPM/RPM) + local slots | **Provisioned instances ($n[m]$) across heterogeneous fleet (CPU, edge GPU, datacenter GPU)** |
| **Fleet Pricing** | Heterogeneous hardware classes (GPU count, energy, dollar cost decorrelated) | Homogeneous generators ($\text{corr}(\text{price}, \text{gpus}) \approx 1.0$) | API token input/output costs ($\$ / \text{token}$) | **Owned heterogeneous fleet (F31/F33): price decorrelated from GPU count by hardware class** |
| **Optimization Method** | Exact MILP (Gurobi, 300s limit) | Fast tracks (A, B, C) + exact MILP baseline | 2-stage Pareto filter + LP relaxation | **Exact MILP baseline (Murakkab replication) + Sub-100ms Tracks (A, B, C)** |
| **Optimization Cadence** | Periodic offline epochs (60 min) with EWMA | Event-driven on drift signal | Static horizon per batch | **Adaptive closed loop: continuous profiling + lightweight drift detection + rapid re-solve** |
| **Execution Reality** | Azure VM cluster (2,560 GPUs) | Abstract simulator (`prototype/simulator.py`) | Abstract dispatcher gateway | **Two-Tier: Macro trace-driven fleet replay + Micro runnable heterogeneous testbed** |
| **Novelty Claim** | Declarative DAG + MILP multiplexing | Closed loop under drift (O12) | API gateway knobs (unratified) | **Closed loop under drift (O12, F24: $+0.424$ reliability recovery over Murakkab baseline)** |

---

## 1. Formal Problem Formulation

### 1.1 Informal Statement
Given a concurrent batch of multi-step agentic workflows whose tasks require model or tool execution, and a fixed hardware resource budget $B$ (e.g. physical GPUs):
1. Select the **model/tool profile** $m \in C(t)$ to serve each task $t$.
2. Determine the **number of instances** $n[m]$ of each profile to provision across the heterogeneous fleet.

The objective is to **minimize total provisioning cost** such that:
- Aggregate load routed to each profile does not exceed the provisioned instance throughput.
- Total hardware resource usage across provisioned instances does not exceed budget $B$.
- Every assigned profile satisfies the task's domain reliability floor $R_{\min}(t)$ and latency ceiling $L_{\max}(t)$.

### 1.2 Sets and Indices
```text
W           Set of concurrent workflows in the batch
T           Set of tasks across all workflows: T = ⋃_{w ∈ W} T_w
M           Set of instantiable model/tool profiles across hardware classes
            (e.g., CPU-whisper, CPU-parser, local-vLLM-Qwen-7B, remote-A100-Llama-70B)
C(t) ⊆ M    Feasible candidate profiles eligible for task t after floor filtering
```

### 1.3 Parameters
```text
load(t)     Throughput demand of task t (requests or token load per unit time)
thr(m)      Throughput capacity of one instance of profile m (same units as load)
gpu(m)      Hardware units (e.g., GPUs) consumed by one instance of profile m
price(m)    Amortised capital + energy cost of running one instance of m over the horizon
B           Total fleet GPU budget
rel(m)      Empirical reliability (success rate) of profile m ∈ [0, 1]
lat(t, m)   Expected latency of task t when executed on profile m
R_min(t)    Reliability floor for task t (anchored to baseline-delivered reliability)
L_max(t)    Latency ceiling for task t
```

### 1.4 Decision Variables
```text
x[t][m] ∈ {0, 1}   Routing: 1 if task t is assigned to profile m; 0 otherwise
n[m]    ∈ Z⁺       Provisioning: Integer number of instances of profile m to open
```

### 1.5 Objective Function
$$\text{minimize} \quad \sum_{m \in M} n[m] \cdot \text{price}(m)$$

*Note on Variable Cost:* Following ratified finding F31 and advisor guidance (O1, 2 Sep 2026), the objective models **provisioning cost only**. Under an owned/allocated infrastructure model, hardware instances are turned on for the epoch/horizon; individual calls do not generate incremental cloud rental invoices.

### 1.6 Constraints
$$\begin{aligned}
\text{(C1) Single Assignment:} & \quad \sum_{m \in C(t)} x[t][m] = 1 && \forall t \in T \\
\text{(C2) Instance Capacity:} & \quad \sum_{t \in T : m \in C(t)} x[t][m] \cdot \text{load}(t) \le n[m] \cdot \text{thr}(m) && \forall m \in M \\
\text{(C3) Fleet Resource Budget:} & \quad \sum_{m \in M} n[m] \cdot \text{gpu}(m) \le B &&
\end{aligned}$$

#### Feasibility-First Candidate Filtering (Principle P3)
Candidate pools $C(t)$ are constructed ahead of the optimization program by strict floor filtering:
$$C(t) = \left\{ m \in M \mid \text{rel}(m) \ge R_{\min}(t) \ \land \ \text{lat}(t, m) \le L_{\max}(t) \right\}$$
Filtering out violating profiles prior to optimization guarantees that the LP relaxation remains valid and prevents the solver from illegally trading SLA compliance for monetary savings.

### 1.7 Heterogeneous Fleet Decorrelation (F31, F33)
In early project iterations, synthetic generators tied price linearly to GPU count ($\text{corr}(\text{price}, \text{gpus}) \approx 0.95\text{--}1.0$), causing (C3) to become redundant with the objective. 

As demonstrated in finding **F31**, Murakkab's own published results report GPU count, energy, and dollar cost as three distinct metrics that move by different ratios ($2.82\times$, $3.72\times$, and $4.33\times$ respectively on Video-QA + CodeGen). This decorrelation occurs because Murakkab balances workloads across distinct hardware classes:
1. **CPUs ($\text{gpu}(m) = 0$):** High CPU throughput for non-autoregressive tools (e.g. Whisper, OpenCV scene detection) at minimal cost.
2. **Workstation/Edge GPUs (1 GPU):** Amortised local nodes with moderate throughput and low capital cost.
3. **Datacenter Accelerators (2–8 GPUs):** High-throughput frontier accelerators (A100, H100) with steep power and capital amortization.

In v4, instances generated by `heterogeneous_generator.py` enforce near-zero correlation between `price(m)` and `gpu(m)`, ensuring that constraint (C3) actively binds and forces genuine trade-offs across hardware classes.

---

## 2. Faithful Murakkab Recreation Strategy

### 2.1 Replicating the Declarative Architecture
Murakkab decouples workflow specification from resource allocation. Developers express agentic pipelines as directed acyclic graphs of sub-tasks without specifying models, batch sizes, or hardware bindings.

```
       [Video File / Incident Log]
                   │
                   ▼
         ┌───────────────────┐
         │ t1: Preprocessing │ (Scene detect / Log parsing)
         └─────────┬─────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐ ┌──────────────────┐
│ t2: Audio/Text   │ │ t3: Visual/Error │ (Whisper / BERT / regex)
│     Extraction   │ │     Detection    │
└────────┬─────────┘ └────────┬─────────┘
         │                    │
         └─────────┬──────────┘
                   ▼
         ┌───────────────────┐
         │ t4: Synthesis     │ (Multimodal LLM / CodeGen)
         └───────────────────┘
```

v4 adopts Murakkab's declarative execution lifecycle:
1. **Specification:** JSON-based batch DAG specification containing task types, input load, and SLA floors.
2. **Resolution:** Exact task-type catalog matching and floor filtering into candidate sets $C(t)$.
3. **Optimization:** Joint determination of routing $x[t][m]$ and instance provisioning $n[m]$.
4. **Dispatch:** Dispatching tasks to provisioned instances according to the compiled routing plan.

### 2.2 Replicating Murakkab's Core Benchmark Workloads
To replicate Murakkab's findings without deviation, v4 structures evaluation around three representative workload patterns directly aligned with Chaudhry et al. (2026):

1. **Video Q/A Pipeline:** Multi-modal pipeline combining CPU-intensive preprocessing (OpenCV / PySceneDetect), speech transcription (Whisper), object feature extraction, and reasoning (Vision-LLM).
2. **Code Generation Pipeline:** Multi-agent debate pattern (Coder agent, Tester agent, Critic agent) executing iterative refinement.
3. **Enterprise Incident Analysis (LogHub):** Real-world enterprise pipeline ingesting raw system logs (`zookeeper`, `spark`, `linux`), parsing structured templates, isolating anomalies, and generating incident root-cause summaries.

### 2.3 Replicating the Exact MILP Baseline
Murakkab's optimizer is an exact Mixed Integer Linear Program solved via commercial solvers (Gurobi / CBC) on 60-minute epochs. 

v4 retains [`poc/tracks/exact_milp.py`](file:///d:/intern/EnterpriseOrches/poc/tracks/exact_milp.py) as the **ground truth Murakkab baseline**. Replicating Murakkab's published results:
- Murakkab achieves up to **$2.8\times$ lower GPU usage, $3.7\times$ lower energy, and $4.3\times$ lower cost** compared to static hand-crafted baselines.
- Cross-workflow multiplexing provides an additional $\sim 21\%$ GPU and $\sim 17\%$ cost reduction over per-workflow optimization.
- v4 measures all fast heuristic tracks against this exact Murakkab baseline across identical batch inputs.

---

## 3. The Novelty Dimension: The Adaptive Closed Loop (O12)

### 3.1 Murakkab's Static Epoch Limitation
While Murakkab achieves high efficiency for static workloads, its architecture possesses a critical structural limitation:
- Re-optimization occurs on a coarse **60-minute periodic epoch**, using an EWMA load predictor.
- Hardware and model profiles ($\text{lat}(t, m)$, $\text{rel}(m)$) are treated as **static, pre-calibrated inputs**.
- Between epochs, Murakkab relies solely on reactive local autoscaling to handle volume spikes.

**The Failure Mode:** If an execution profile suffers runtime drift—due to server-side thermal throttling, network contention, quantization artifacts, prompt drift, or backend service degradation—Murakkab's static routing remains frozen. The static allocator continues routing traffic to degraded nodes, causing widespread, unmonitored SLO violations.

### 3.2 Our Ratified Novelty: Continuous Adaptive Profiling (O12)
As ratified with the project advisor on 3 September 2026 (open item **O12**), our novel contribution is the **adaptive closed loop**:
$$\text{Observe Telemetry (J6)} \longrightarrow \text{Update Profiles (J7)} \longrightarrow \text{Detect Drift (J8)} \longrightarrow \text{Global Re-Optimization (J9)}$$

```
  ┌─────────────────────────────────────────────────────────────┐
  │                 Multi-Workflow Ingestion (J1)               │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 Eligibility Resolver (J2)                   │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
   ┌───────────────────────────────────────────────────────────┐
   │             Multi-Workflow Optimizer (J3)                 │◄────────┐
   │     [Track A: Greedy] [Track B: Lagr] [Track C: LP]      │         │
   └─────────────────────────────┬─────────────────────────────┘         │
                                 │                                       │
                                 ▼                                       │
   ┌───────────────────────────────────────────────────────────┐         │
   │               Assignment Registry (J4)                    │         │
   └─────────────────────────────┬─────────────────────────────┘         │
                                 │                                       │
                                 ▼                                       │
   ┌───────────────────────────────────────────────────────────┐         │
   │            Two-Tier Execution Engine (J5)                 │         │
   │   (Macro Trace Replay  /  Micro Heterogeneous Testbed)    │         │
   └─────────────────────────────┬─────────────────────────────┘         │
                                 │                                       │
                                 ▼                                       │
   ┌───────────────────────────────────────────────────────────┐         │
   │                Telemetry Interceptor (J6)                 │         │
   │           Attribution: (workflow, task, profile)          │         │
   └─────────────────────────────┬─────────────────────────────┘         │
                                 │                                       │
                                 ▼                                       │
   ┌───────────────────────────────────────────────────────────┐         │
   │               Profile Store & Updater (J7)                │         │
   │       EMA Latency  +  Decayed Beta-Binomial Reliability   │         │
   └─────────────────────────────┬─────────────────────────────┘         │
                                 │                                       │
                                 ▼                                       │
   ┌───────────────────────────────────────────────────────────┐         │
   │                 Drift Detector (J8)                       │         │
   │      Lightweight Parameter-Margin & Compatibility Check   │         │
   └─────────────────────────────┬─────────────────────────────┘         │
                                 │                                       │
                                 └──────── [Drift Fired] ────────────────┘
```

### 3.3 The Core Empirical Evidence: Finding F24
The core empirical justification for this project is finding **F24**:
- Under simulated runtime profile drift across 16 consecutive rounds, Murakkab's static allocation delivered an average **$0.542$ reliability against a $0.95$ floor**, while reporting no errors and maintaining a nominal cost of 400.
- Our adaptive closed loop detected the drift, triggered re-optimization, and delivered **$0.938$ reliability** at cost 1013.
- Paired reliability advantage: **$+0.424$ [0.405, 0.442]** over 20 random seeds.
- On cost alone, a static system appears artificially cheaper because it quietly fails its SLAs. The closed loop is necessary to guarantee delivered quality under real-world uncertainty.

### 3.4 Why the Loop Demands Sub-100ms Solvers
Murakkab solves its MILP using Gurobi with a 300-second timeout. While acceptable for a 60-minute batch epoch, a 300-second solver cannot function inside an online re-optimization loop.

As proven in **F13** and **F16**:
- The exact MILP solver requires $12.3 \pm 10.3$ seconds on 64-task batches and occasionally fails to terminate within reasonable interactive limits.
- **Track C (LP Relaxation + Repair)** solves in **$0.106 \pm 0.020$ seconds** (sub-150ms bounded execution) while achieving objective costs within $3\%$ of the MILP optimum.
- Fast heuristic tracks make online closed-loop re-optimization computationally feasible.

---

## 4. Two-Tier Execution Architecture (Bridging Simulation to Reality)

`System_Architecture_v3.md` was prompted by the fear that managing physical enterprise multi-GPU clusters was unattainable. v4 addresses this pragmatically using standard systems benchmarking methodology: a **Two-Tier Execution Architecture**.

```
                           ┌─────────────────────────────────────────┐
                           │      Execution Engine Router (J5)       │
                           └────────────────────┬────────────────────┘
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       │                                                 │
                       ▼                                                 ▼
        ┌─────────────────────────────┐                   ┌─────────────────────────────┐
        │   Tier 1: Macro Replay      │                   │   Tier 2: Concrete Testbed  │
        │   (Trace-Driven Simulation) │                   │   (Physical Heterogeneous)  │
        ├─────────────────────────────┤                   ├─────────────────────────────┤
        │ • Azure LLM-serving traces  │                   │ • Local CPU workers         │
        │ • Murakkab published A100/  │                   │ • Local vLLM/Ollama SLMs    │
        │   H100/CPU hardware tables  │                   │ • Real prompt execution     │
        │ • Validates fleet scale     │                   │ • Measures actual TTFT/TPOT │
        │   (1,000–2,500 GPUs)        │                   │ • Live fault injection      │
        └─────────────────────────────┘                   └─────────────────────────────┘
```

### 4.1 Tier 1: Macro-Scale Trace-Driven Fleet Replay
- **Goal:** Reproduce Murakkab's fleet-scale findings across hundreds of concurrent workflows and up to 2,560 GPUs.
- **Mechanism:** Ingests Azure LLM trace arrivals and Murakkab's published performance tables (latency, energy, throughput, and hardware costs across A100, H100, and CPU).
- **Function:** Replays high-volume request streams through the optimizer, validating multi-tenant multiplexing, budget binding (C3), and large-scale scaling behavior without requiring multi-million-dollar hardware.

### 4.2 Tier 2: Micro-Scale Concrete Heterogeneous Testbed
- **Goal:** Provide real, runnable, tangible execution with physical wall-clock timing, genuine process boundaries, and live telemetry.
- **Physical Testbed Topology:**
  1. **CPU Workers:** Lightweight Python runtimes executing log parsing (LogHub drain), regex extraction, and deterministic NLP utilities.
  2. **Local GPU SLMs:** vLLM / Ollama instances hosting quantized models (e.g. Qwen-2.5-7B, Llama-3.2-3B) with explicit concurrency slots and physical VRAM constraints.
  3. **Simulated Enterprise Endpoints:** High-tier profiles calibrated with precise delay distributions and failure injection hooks to emulate remote cluster nodes.
- **Function:** Exercises the Telemetry Interceptor (J6), Profile Store (J7), and Drift Detector (J8) against real wall-clock latency (TTFT/TPOT) and HTTP socket responses.

---

## 5. Systematic Resolution of Component Gaps (G1–G10)

System Architecture v4 explicitly integrates fixes for the 10 known architectural gaps identified in [`docs/design/component_gaps.md`](file:///d:/intern/EnterpriseOrches/docs/design/component_gaps.md):

### G1: Per-Task Demand Differentiation (J1)
- **Problem:** Tasks previously drew `load(t)` from `task_type` spec alone, causing all tasks of the same type to have identical demands and ignoring input data sizes.
- **v4 Resolution:** Task demand is dynamically derived at ingestion from workflow input attributes:
  $$\text{load}(t) = \text{base\_load}(\text{task\_type}) \times f(\text{input\_tokens / log\_lines})$$
  Each task instance carries differentiated load into J3.

### G2: Multi-Parameter Profile Updating (J7)
- **Problem:** `ProfileStore` updated only latency and reliability; throughput $\text{thr}(m)$, GPUs, and price were immutable, allowing misdeclared throughput to corrupt capacity calculations.
- **v4 Resolution:** While physical attributes ($\text{gpu}(m)$, hardware class amortised rate) remain configuration constants, effective serving throughput $\text{thr}(m)$ is continuously measured as observed completed requests per second of active execution time:
  $$\text{thr}(m)_{\text{new}} = (1 - \beta) \cdot \text{thr}(m)_{\text{old}} + \beta \cdot \text{observed\_throughput}$$

### G3: Load-Scaled Observation Emission (J5/J6)
- **Problem:** Simulated execution emitted exactly 1 observation per round regardless of task load, so a task with $10\times$ load accumulated evidence no faster than an idle one.
- **v4 Resolution:** The execution engine scales telemetry observations proportionally to routed load: $N_{\text{obs}}(t) = \max(1, \lfloor \text{load}(t) / \text{batch\_unit} \rfloor)$. High-throughput tasks converge profile estimates proportionally faster.

### G4: DAG Acyclicity Verification (J1)
- **Problem:** `ingest()` validated dependency target existence but omitted cycle detection.
- **v4 Resolution:** J1 applies Tarjan’s / Kahn’s topological sort algorithm during manifest parsing. Cyclic dependencies fail fast at ingestion with an explicit `CyclicWorkflowError`.

### G5: Disambiguation of Snapshot Interfaces
- **Problem:** The verb `snapshot()` was ambiguously used for both `ProfileStore.snapshot()` (telemetry records) and `ProvisioningState.snapshot()` (search backtracking).
- **v4 Resolution:** Disambiguated method contracts:
  - `ProfileStore.export_profile_snapshot() -> ProfileSnapshot`
  - `ProvisioningState.checkpoint() -> StateCheckpoint` and `restore_checkpoint(cp)`

### G6 & G7: Lightweight Parameter-Margin Drift Detection (J8)
- **Problem:** Drift detector ran the full combinatorial optimizer to check if decisions flipped (expensive, duplicate runs), and gave zero warning when a profile was degrading toward a feasibility cliff.
- **v4 Resolution:** Drift detection runs a lightweight two-tier check:
  1. **Parameter Cliff Margin Check:** Triggers if a profile's estimated reliability or latency drops within safety margin $\epsilon$ of any routed task's floor:
     $$\text{rel}(m) - R_{\min}(t) < \epsilon_{\text{rel}} \quad \lor \quad L_{\max}(t) - \text{lat}(t, m) < \epsilon_{\text{lat}}$$
  2. **Fast Heuristic Compatibility Check:** Evaluates whether marginal cost ordering changes for currently routed tasks, without re-solving the entire global program.

### G8: Seamless Integration of Re-Optimization (J9)
- **Problem:** `reoptimisation.py` was disconnected from `prototype/loop.py`; when drift fired, `loop.py` performed an inline solve rather than structured re-optimization.
- **v4 Resolution:** `loop.py` directly invokes the ratified `reoptimise_global()` pipeline from `reoptimisation.py`, ensuring consistent state transfer and result auditing.

### G9: Unified Closed-Loop Evaluation in Harness (J10)
- **Problem:** `poc/harness/runner.py` only evaluated single-shot static allocations, leaving closed-loop drift evaluation isolated in one-off test scripts.
- **v4 Resolution:** Harness adds a multi-epoch evaluation mode that steps through simulated drift scenarios, recording delivered reliability, SLA violation rates, and re-optimization overhead across all tracks alongside static baselines.

### G10: Default Optimistic Eligibility via UCB (J2/J7)
- **Problem:** Optimistic eligibility was disabled by default (`optimistic_eligibility=False`), causing profiles suffering transient noise to be prematurely and permanently discarded (F23).
- **v4 Resolution:** Candidate eligibility resolution $C(t)$ enables Upper Confidence Bound (UCB) filtering by default:
  $$\text{rel}_{\text{eval}}(m) = \text{rel}_{\text{mean}}(m) + c \cdot \sqrt{\frac{\ln(\sum N)}{N(m)}}$$
  This guarantees exploration of noisy profiles while preserving safety floors.

---

## 6. Functional Architecture & Component Specifications

### 6.1 Job Execution Flow

```text
J1 Ingest Batch            Parse, validate DAG acyclicity (G4), compute per-task load (G1)
     │
J2 Resolve Eligibility     Filter C(t) using UCB floors (G10)
     │
J3 Produce Allocation      Execute selected optimizer Track (MILP, A, B, or C)
     │
J4 Persist Assignment      Store immutable versioned routing plan and provisioning state
     │
J5 Execute Workflows       Run via Tier 1 Trace Replay or Tier 2 Heterogeneous Testbed
     │
J6 Intercept Telemetry     Attribute latency, success/failure, emit load-scaled observations (G3)
     │
J7 Update Profiles         Update EMA latency, decayed beta-binomial reliability, thr (G2)
     │
J8 Detect Drift            Run lightweight margin and compatibility check (G6, G7)
     │
J9 Global Re-Optimize      Trigger global re-allocation upon verified drift signal (G8)
     │
J10 Evaluate Performance   Execute multi-epoch benchmark harness under matched conditions (G9)
```

### 6.2 The Multi-Track Optimizer (J3)

All optimizer tracks implement the unified interface:
```python
def allocate(
    tasks: list[Task],
    pools: dict[TaskId, list[str]],     # C(t)
    profiles: dict[str, ProfileSpec],
    budget: int,
    seed: int = 0
) -> AllocationResult: ...
```

#### Track Specifications:
1. **Exact MILP Baseline (Murakkab Replication):** Formulated in PuLP/CBC. Solves the exact integer program $\min \sum n[m] \cdot \text{price}(m)$ subject to (C1)–(C3). Serves as ground truth and direct replication of Murakkab.
2. **Track A (Greedy Construction + Feasibility Lookahead):** Ranks tasks by marginal activation cost, incorporating Cheng & Nguyen lookahead heuristics and multi-start permutations.
3. **Track B (Lagrangian Relaxation on C1):** Relaxes assignment constraints (C1) with subgradient multiplier updates, decomposing into independent profile subproblems and computing a valid theoretical lower bound.
4. **Track C (LP Relaxation + Integer Repair):** Relaxes $x[t][m]$ and $n[m]$ to continuous variables, solves the linear program in $<20\text{ms}$, and executes a deterministic integer repair pass to restore feasibility under (C2) and (C3). This is the production track powering the sub-100ms adaptive loop.

### 6.3 System Invariants
Every allocation produced by any track must satisfy the 5 formal invariants:
- **I1 (Assignment Integrity):** Every task $t \in T$ is assigned to exactly one profile $m \in C(t)$.
- **I2 (Capacity Sufficiency):** For every profile $m$, $\sum x[t][m] \cdot \text{load}(t) \le n[m] \cdot \text{thr}(m)$.
- **I3 (Budget Compliance):** $\sum_{m \in M} n[m] \cdot \text{gpu}(m) \le B$.
- **I4 (Floor Compliance):** Every routed profile meets task reliability and latency thresholds.
- **I5 (Active Provisioning):** $n[m] \ge 1$ for all profiles appearing in the routing plan.

---

## 7. Traceability, Literature & Test Strategy

### 7.1 Requirement Traceability

| Req | Description | Status | Architectural Mapping |
|---|---|---|---|
| **R1** | Per-task model/tool allocation | Covered | Optimizer Tracks (§6.2), Invariant I1 |
| **R2** | Multiple concurrent workflow multiplexing | Covered | Cross-workflow (C2) capacity sharing |
| **R3** | Non-exact fast alternative to MILP | Covered | Tracks A, B, C (Sub-100ms Track C) |
| **R4** | Profile-guided, self-updating telemetry | Covered | J6 Interceptor, J7 Decayed Estimator |
| **R5** | Event-driven re-optimization under drift | Covered | J8 Margin Detector, J9 Global Re-Solve |
| **R6** | Rigorous evaluation vs. exact Murakkab baseline | Covered | J10 Harness with matched seeds & bias guards |
| **R7** | Execution monitoring & telemetry | Covered | J6 Interceptor & Tier 2 Concrete Testbed |
| **R8** | Execution-time reliability assurance | Covered | Baseline-anchored floors ($R_{\min}(t)$) + UCB filtering |
| **R9** | Framework integration | Planned (Sem 2) | Clean DAG JSON interface ingestible from DSPy / LangGraph |

### 7.2 Literature Grounding

| Reference | What is Adopted | Architectural Role |
|---|---|---|
| **Chaudhry et al. (2026), Murakkab** *(OSDI '26)* | Declarative DAG workflow model, instance-based capacity model ($n[m]$), heterogeneous hardware profiles, exact MILP formulation | Foundational Base & Baseline |
| **Cheng & Nguyen (2026)** | Feasibility-first candidate filtering, marginal cost prioritization | Heuristic Track A design |
| **de la Torre & Halappanavar (2023)** | Lagrangian relaxation with subgradient updates | Heuristic Track B bound computation |
| **Hua et al. (2026), AgentOpt** | Non-invasive transport-layer interception and call attribution | Profiling Telemetry (J6) |
| **Classical Facility Location Literature** | Modular Capacitated Facility Location formulation with budget constraint | Formal Problem Class (§1.8) |

### 7.3 Verification and Regression Guard
The existing codebase contains **651 automated tests** covering invariants, provisioning arithmetic, track convergence, adversarial cases, and closed-loop behavior. System Architecture v4 guarantees 100% backward compatibility: all 651 tests remain green without modification.
