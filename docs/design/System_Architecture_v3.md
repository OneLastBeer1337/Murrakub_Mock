# System Architecture and Detailed Design — v3

**API-First Hybrid Multi-Workflow Resource Orchestration Platform**

*Supersedes `System_Architecture_v2.md` (v2).* Written to guide implementation on the `systemarchv3` branch.

---

## 0. Executive Summary: The Pivot from v2 to v3

### 0.1 The Core Problem with v2
System Architecture v2 was strictly scoped around **GPU instance provisioning** ($n[m]$ dedicated server instances under a physical GPU budget $B$), formalised as *Modular Capacitated Facility Location*. In that formulation:
- Profiles were physical GPU instances (e.g., A100/H100 nodes running vLLM).
- Cost was derived entirely from spinning up whole server instances ($\sum n[m] \cdot \text{price}(m)$).
- Per-invocation cost ($\text{varcost}$) was explicitly closed as "no".
- Execution was permanently trapped in simulation (`prototype/simulator.py`) because managing a physical multi-GPU cluster was inaccessible and disproportionately complex.

### 0.2 The v3 Realignment
Modern enterprise agentic workflows are **overwhelmingly API-first** (calling managed cloud models like OpenAI, Anthropic, Google Gemini, Groq, DeepSeek) while occasionally leveraging **local Small Language Models (SLMs)** for high-frequency, privacy-sensitive, or lightweight tasks.

v3 re-architects the platform from the ground up:
1. **Hybrid Resource Model:** Replaces physical GPU packing with a hybrid model combining **Cloud LLM APIs** (pay-per-token, governed by provider TPM/RPM rate limits and dollar budgets) with a **Local SLM Pool** (amortised cost, governed by local GPU concurrency slots).
2. **Multi-Tier Adjustable Knobs:** Expands the decision space beyond mere model selection to include reasoning effort, prompt depth, structural loops, and resilience policies.
3. **Redefined Executor (Dual-Role Gateway):** Replaces the abstract, unbuildable GPU container manager with an **application-level Dispatcher & Resilience Gateway**. Infrastructure management scope is drastically reduced, while execution becomes **100% real, testable, and runnable**.
4. **Hierarchical Two-Stage Optimizer:** Solves task-level knob selection via Pareto filtering (Stage 1), followed by global multi-workflow resource allocation via LP relaxation (Stage 2), preserving v2's sub-100ms bounded solver performance.
5. **Real-World Incident Analysis Workload:** Replaces synthetic generators with real multi-step pipelines built on the existing **LogHub** dataset (`zookeeper`, `spark`, `linux`).

---

## 1. Problem Formulation

### 1.1 Informal Statement
Given a batch of concurrent multi-step agentic workflows whose tasks require LLM inference, a fixed batch dollar budget, provider-imposed API rate limits (tokens per minute and requests per minute), and a bounded local SLM execution capacity:
1. Select the **model endpoint** (Cloud API tier vs. Local SLM) for each task.
2. Select the **configuration knobs** (reasoning budget, prompt exemplars, structural chunking, retry policy) for each task.

The objective is to **minimize total monetary cost** (or maximize delivered quality under a budget ceiling) such that:
- Every task passes its domain **reliability floor** $R_{\min}(t)$ and **latency ceiling** $L_{\max}(t)$.
- Combined demand across concurrent workflows does not breach **cloud API rate limits** (preventing 429 throttling).
- Concurrent demand on the local inference server does not exceed **local GPU concurrency slots** (preventing OOM and queuing delays).
- The total execution cost does not exceed the **dollar budget** $B_{\$}$.

---

### 1.2 Sets and Indices

```text
W           Set of concurrent workflows in the batch
T           Set of tasks across all workflows: T = ⋃_{w ∈ W} T_w
M           Set of model endpoints:
              M = M_cloud ∪ M_local
              M_cloud: {GPT-4o, Claude-3.5-Sonnet, Gemini-2.0-Flash, Groq-Llama-3.3-70B, ...}
              M_local: {Ollama-Llama-3.2-3B, vLLM-Qwen-2.5-7B, ...}
P           Cloud API providers: P = {OpenAI, Anthropic, Google, Groq, ...}
K           Set of discrete knob configurations (reasoning effort, prompt depth, chunk size)
C(t) ⊆ M × K  Feasible (model, knob) candidate pairs eligible for task t after floor filtering
```

---

### 1.3 Parameters

```text
# Workload Demands
in_tokens(t, k)     Expected input prompt tokens for task t under knob k
out_tokens(t, k)    Expected output completion tokens for task t under knob k
load_rpm(t)         Request rate contributed by task t (typically 1 call per workflow instance)

# Financial Cost Parameters
price_in(m)         Cost per input token for model m ($ / token)
price_out(m)        Cost per output token for model m ($ / token)
cost(t, m, k)       in_tokens(t, k) · price_in(m) + out_tokens(t, k) · price_out(m)
                    (For m ∈ M_local, marginal cost is $0.00)
B_$                 Total monetary budget for the batch / horizon ($)

# Capacity & Rate Limit Constraints
TPM_limit(p)        Tokens Per Minute rate limit for provider p (across all its models)
RPM_limit(p)        Requests Per Minute rate limit for provider p
Slots_local         Max concurrent active inference streams supported by local GPU

# Quality & SLA Floors
rel(t, m, k)        Empirical reliability (schema validity & success rate) of task t on (m, k)
lat(t, m, k)        Expected end-to-end latency (seconds) of task t on (m, k)
R_min(t)            Reliability floor for task t (minimum required success rate)
L_max(t)            Latency ceiling for task t (maximum tolerable SLA)
```

---

### 1.4 Decision Variables

```text
x[t][m, k] ∈ {0, 1}   1 if task t is assigned model m with knob configuration k; 0 otherwise.
```

---

### 1.5 Objective Function

```text
minimize   Σ_{t ∈ T} Σ_{(m, k) ∈ C(t)} x[t][m, k] · cost(t, m, k)
```

*(Note: If a fixed dollar budget $B_{\$}$ is strictly given and quality is prioritized, the objective dualizes to maximizing $\sum x[t][m, k] \cdot \text{rel}(t, m, k)$ subject to total cost $\le B_{\$}$.)*

---

### 1.6 Constraints

```text
(C1) Assignment:
     Σ_{(m, k) ∈ C(t)} x[t][m, k] = 1                              ∀ t ∈ T
     Every task is assigned exactly one model-knob configuration.

(C2) Local SLM Concurrency:
     Σ_{t ∈ T} Σ_{k} x[t][m, k]  ≤  Slots_local                    ∀ m ∈ M_local
     Concurrent tasks routed to local SLMs do not exceed hardware execution slots.

(C3) Provider Token Rate Limits (TPM):
     Σ_{t ∈ T} Σ_{m ∈ M(p)} Σ_{k} x[t][m, k] · (in_tokens(t, k) + out_tokens(t, k)) ≤ TPM_limit(p)
     Aggregate token demand on provider p does not trigger 429 throttling.

(C4) Provider Request Rate Limits (RPM):
     Σ_{t ∈ T} Σ_{m ∈ M(p)} Σ_{k} x[t][m, k] · load_rpm(t) ≤ RPM_limit(p)
     Aggregate call frequency on provider p remains within tier quotas.

(C5) Dollar Budget Ceiling:
     Σ_{t ∈ T} Σ_{(m, k) ∈ C(t)} x[t][m, k] · cost(t, m, k) ≤ B_$
     Total batch API expenditures do not exceed financial limits.
```

#### Feasibility Filtering (Construction of $C(t)$)
As established in principle **P3** (*feasibility first, cost second*), SLA constraints are not soft penalties in the objective; they are hard filters applied during candidate generation:

$$C(t) = \left\{ (m, k) \in M \times K \mid \text{rel}(t, m, k) \ge R_{\min}(t) \ \text{and} \ \text{lat}(t, m, k) \le L_{\max}(t) \right\}$$

---

### 1.7 Where the Coupling Lives in v3

| Constraint | Coupling Type | Real-World Enterprise Impact |
|---|---|---|
| **(C1)** | Intra-task | Mutually exclusive choice among candidate configurations. |
| **(C2)** | Cross-workflow (Local) | If Workflow A routes 3 heavy parsing tasks to local Ollama, Workflow B cannot use the local GPU without queuing. |
| **(C3) & (C4)** | Cross-workflow (Cloud) | If Workflow A bursts high-token reasoning calls to Claude 3.5 Sonnet, Workflow B's simultaneous calls hit HTTP 429 rate limits unless coordinated. |
| **(C5)** | Global Fleet | Shared financial quota across all pipelines in the enterprise tenant. |

---

### 1.8 Problem Class Identification
In v2, the problem was *Modular Capacitated Facility Location*. 
In v3, the problem transitions to a **Multi-Dimensional Multi-Choice Knapsack Problem (MMKP)** with shared rate constraints:
- **Knapsack Items:** Tasks $t \in T$.
- **Choice Classes:** Each task must select exactly one item from its candidate set $C(t)$.
- **Resource Dimensions:** Local slots (C2), Provider TPM (C3), Provider RPM (C4), and Dollar Budget (C5).
- **Benefit / Weight:** Item weight is cost and token consumption; benefit is meeting quality floors.

This mathematical structure is well-studied, guarantees polynomial-time LP relaxation, and allows **Track C** (LP + rounding) to solve large instances (128+ tasks) in **under 100 milliseconds**.

---

## 2. System Architecture

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MULTI-WORKFLOW BATCH                                 │
│                   (Workflow DAGs: LogHub Incident Triage)                        │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ J1: Ingest Batch
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             ELIGIBILITY RESOLVER                                 │
│           • Task type schema matching                                            │
│           • Pre-filtering by R_min(t) and L_max(t)                               │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ Pools C(t)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   HIERARCHICAL TWO-STAGE OPTIMIZER                               │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │ STAGE 1: Task-Level Pareto Filtering                                       │  │
│  │ Prunes dominated knob choices across (Model, Effort, Context, Structural)  │  │
│  │ Produces 3–4 non-dominated candidate profiles per task                     │  │
│  └─────────────────────────────────────┬──────────────────────────────────────┘  │
│                                        │ Pareto Candidate Pool                   │
│  ┌─────────────────────────────────────▼──────────────────────────────────────┐  │
│  │ STAGE 2: Multi-Workflow Fleet Resource Allocator                           │  │
│  │ Track C: LP Relaxation + Greedy Repair under Rate Limits & Budget          │  │
│  │ Decision: x[t][m, k]                                                       │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ J4: Persist Allocation
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   EXECUTOR ENGINE (DUAL-ROLE GATEWAY)                            │
│                                                                                  │
│   ┌───────────────────────────────┐     ┌────────────────────────────────────┐   │
│   │   Knob & Prompt Transformer   │     │  Rate-Limit Token Bucket Pacer     │   │
│   └───────────────┬───────────────┘     └─────────────────┬──────────────────┘   │
│                   │                                       │                      │
│                   ▼                                       ▼                      │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │           Multi-Provider Async Dispatcher with Fallback Chains           │   │
│   └───────────────────────┬───────────────────────────────┬──────────────────┘   │
│                           │                               │                      │
│                           ▼                               ▼                      │
│               [ Local SLM Inference ]             [ Cloud LLM APIs ]             │
│                 (Ollama / vLLM local)           (OpenAI / Anthropic / Gemini)    │
│                           │                               │                      │
│                           └───────────────┬───────────────┘                      │
│                                           │ J5/J6: Telemetry Stream              │
│                                           ▼                                      │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │                  Client-Side Telemetry Interceptor                       │   │
│   │       (Tokens, Dollar Cost, Latency/TTFT, Schema Pydantic Validation)    │   │
│   └───────────────────────────────────────┬──────────────────────────────────┘   │
└───────────────────────────────────────────┼──────────────────────────────────────┘
                                            │ Observations
                                            ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             PROFILING SUBSYSTEM                                  │
│   • Profile Store: Decayed counting estimator (reliability) + EMA (latency)      │
│   • Deterministic Drift Detector: Monitors 429 rate, schema errors, token drift  │
│   • J9 Event-Driven Trigger: Signals global re-optimisation on sustained drift   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Four-Tier Adjustable Knob Taxonomy

Instead of treating a model as a black box, v3 exposes four orthogonal tiers of adjustable knobs that can be configured per task:

```
                  ┌────────────────────────────────────────────────┐
                  │            TIER 1: MODEL ROUTING               │
                  │  Local SLM vs. Fast Cloud API vs. Frontier API │
                  └───────────────────────┬────────────────────────┘
                                          │
                  ┌───────────────────────▼────────────────────────┐
                  │        TIER 2: GENERATION & EFFORT             │
                  │  Reasoning tokens, few-shot depth, max tokens  │
                  └───────────────────────┬────────────────────────┘
                                          │
                  ┌───────────────────────▼────────────────────────┐
                  │       TIER 3: STRUCTURAL & PIPELINE            │
                  │  Chunking size, reflection, voting/ensemble k  │
                  └───────────────────────┬────────────────────────┘
                                          │
                  ┌───────────────────────▼────────────────────────┐
                  │        TIER 4: RESILIENCE & EXECUTION          │
                  │  Timeout, retry backoff, fallback target model │
                  └────────────────────────────────────────────────┘
```

### 3.1 Detail of Each Knob Tier

| Tier | Knob Name | Allowed Values | Impact on Cost | Impact on Quality / Latency |
|---|---|---|---|---|
| **1. Model Routing** | `endpoint` | `local-slm`, `fast-api`, `frontier-api` | 0x (local) to 50x (frontier) | Low capacity/quality to maximal reasoning capability |
| **2. Generation & Effort** | `reasoning_effort` | `none`, `low`, `medium`, `high` | Multiplies output tokens (2x–5x) | Massive gain on multi-step reasoning; none on formatting |
| | `few_shot_k` | `0`, `1`, `3` exemplars | Scales input tokens by $k \times \text{tokens}_{demo}$ | Dramatically stabilizes schema and JSON formatting |
| | `max_output_tokens` | `256`, `1024`, `4096` | Bounds worst-case runaway cost | Prevents output truncation errors |
| | `temperature` | `0.0`, `0.2`, `0.7` | Zero cost impact | 0.0 for deterministic schema parsing; 0.7 for synthesis |
| **3. Structural Pipeline** | `chunk_batch_size` | `10`, `50`, `200` log lines | Fewer total calls, larger prompts | Balances context window limits vs. call overhead |
| | `reflection_loops` | `0` (direct), `1` (self-check) | 2x call cost | Catches subtle extraction hallucinations |
| | `voting_k` | `1` (single), `3` (majority vote) | $k \times$ call cost | Maximizes precision on critical triage decisions |
| **4. Resilience** | `max_retries` | `1`, `3`, `5` | Only incurs cost on failures | Mitigates transient network blips and 503s |
| | `retry_backoff` | `exponential`, `linear` | Zero cost impact | Prevents exacerbating provider 429 storms |
| | `fallback_endpoint` | Specific alternative model | Variable backup pricing | Guarantees task completion if primary is throttled |

---

## 4. The Redefined Executor: Dual-Role Gateway

### 4.1 Scope Comparison: v2 vs. v3

```
v2 EXECUTOR SCOPE (Hypothetical & Trapped in Simulation)
  ❌ Deploy and manage Kubernetes / Docker containers on raw GPUs
  ❌ Bin-pack model weights into CUDA VRAM
  ❌ Start/stop vLLM server instances dynamically
  ❌ Manage GPU cluster networking and hardware failures
  Result: Impossible to run on commodity hardware; forced to use simulator.py.

v3 EXECUTOR SCOPE (Application-Level Gateway & Resilience Worker)
  ✅ Lightweight, asynchronous HTTP/REST client (using httpx / LiteLLM)
  ✅ Native client-side rate-limit pacer (Token Bucket) to prevent 429s
  ✅ Transforms task input with assigned knobs (prompt templates, reasoning tokens)
  ✅ Automatic failover: dispatches to fallback endpoint on HTTP 429/503
  ✅ Intercepts and parses exact telemetry (tokens, cost, latency, Pydantic schema validation)
  Result: 100% executable on any laptop, server, or cloud workstation.
```

### 4.2 Module Contract: `ExecutorGateway`

```python
class ExecutorGateway:
    """Dispatches tasks to Cloud APIs or Local SLM endpoints with rate-limiting,
    resilience fallbacks, and deterministic telemetry interception.
    """

    async def execute_task(
        self,
        task_id: TaskId,
        task_type: str,
        input_data: dict,
        assigned_profile: ModelEndpoint,
        assigned_knobs: KnobConfiguration,
        fallback_chain: list[ModelEndpoint]
    ) -> ExecutionResult:
        """
        1. Acquire rate-limit token-bucket permit for assigned_profile.provider.
        2. Render prompt template according to few_shot_k and input_data.
        3. Dispatch HTTP request with reasoning_effort, max_tokens, and json_schema.
        4. On 429 (rate limit) or 503 (overload):
             - Attempt exponential backoff retry up to max_retries.
             - If exhausted, seamlessly dispatch to fallback_chain[0].
        5. Validate response against task_type's Pydantic schema.
        6. Emit complete Observation telemetry:
             (task_id, model, input_tokens, output_tokens, cost, latency, success).
        """
```

---

## 5. Hierarchical Two-Stage Optimizer

Solving for all 4 knob tiers across all tasks and workflows simultaneously creates a combinatorial space of size $|M| \times |K|^{|T|}$. The Hierarchical Two-Stage Optimizer breaks this coupling cleanly:

```
[ All Combinations (M x K) ]
            │
            ▼
┌────────────────────────────────────────────────┐
│ STAGE 1: Task-Level Pareto Filtering (Local)   │
│   • Evaluates historical / benchmark profiles  │
│   • Filters out rel < R_min(t) or lat > L_max  │
│   • Computes Pareto Frontier on (Cost, Rel)    │
│   • Output: 3–4 non-dominated options in C(t)  │
└───────────────────────┬────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────┐
│ STAGE 2: Multi-Workflow Fleet Allocator (Global)│
│   • Solves MMKP across concurrent workflows    │
│   • Constraints: Local Slots, TPM, RPM, Budget │
│   • Track C: LP Relaxation + Rounding + Repair │
│   • Output: Exact assignment x[t][m, k]        │
│   • Solve Time: < 100 ms                       │
└────────────────────────────────────────────────┘
```

### 5.1 Stage 1: Local Pareto Filtering
For each task $t$, the candidate configuration pool $C(t)$ is pruned to the Pareto frontier:
- Configuration $A$ dominates configuration $B$ if:
  $$\text{cost}(t, A) \le \text{cost}(t, B) \quad \text{and} \quad \text{rel}(t, A) \ge \text{rel}(t, B) \quad \text{and} \quad \text{lat}(t, A) \le \text{lat}(t, B)$$
  with at least one strict inequality.
- Dominated configurations are dropped. For example:
  - *Frontier model with zero-shot reasoning* that is both more expensive and less accurate than *Small API with 3-shot exemplars* is pruned immediately.
- Result: Each task retains only **3 to 4 distinct, optimal operational points** (e.g., `Local-SLM-LowCost`, `Balanced-API-Medium`, `Frontier-API-HighAccuracy`).

### 5.2 Stage 2: Global Fleet Resource Allocator (Track C)
With $|C(t)| \le 4$, Stage 2 constructs the Linear Programming relaxation:
- Continuous relaxation: $x[t][m, k] \in [0, 1]$.
- Constraints (C1)–(C5) solved via standard interior-point / simplex solvers in **under 20 ms**.
- **Rounding & Repair Pass:**
  - Tasks with fractional assignments are greedily rounded to their cheapest feasible integer assignment.
  - If a rounding breaches a provider TPM or local slot constraint, the repair heuristic relocates the offending task to its secondary Pareto candidate.
- Preserves the proven **bounded runtime** property from v2: guaranteed sub-100ms allocation for batches of up to 128 tasks.

---

## 6. Profiling Subsystem & Deterministic Drift Detection

### 6.1 Why Drift Detection is Deterministic in v3
In v2, detecting semantic drift was an unresolved problem that relied on synthetic simulator shifts. In v3, calling real APIs introduces real, measurable degradation:
1. **HTTP Status Codes:** Provider throttling (429) or endpoint outage (500/503).
2. **Schema Validity:** Pydantic validation failure (model produced invalid JSON, omitted required keys, or hallucinated formatting).
3. **Token Usage Inflation:** Input prompt tokens or output completion tokens drifting significantly higher than baseline profiles.
4. **Latency / TTFT Spikes:** Provider server queuing causing latency to cross $L_{\max}(t)$.

### 6.2 Estimators
- **Reliability Metric ($\text{rel}$):** Tracked via the decayed counting estimator established in finding F19:
  $$\text{rel} = \frac{\text{decayed successes} + p}{\text{decayed trials} + 2p}$$
  where a "success" requires both HTTP 200 and schema validation pass.
- **Latency Metric ($\text{lat}$):** Tracked via Exponential Moving Average (EMA, $\alpha = 0.2$).

### 6.3 Global Re-Optimisation Trigger (J9)
When the Drift Detector flags that an endpoint's observed reliability drops below $R_{\min}(t)$ or its 429 rate exceeds 5%:
1. The endpoint's profile is updated in the **Profile Store**.
2. Stage 1 recalculates $C(t)$ for affected tasks.
3. Stage 2 re-solves the global allocation across the batch (**J9 executes globally**, adhering to finding F18).
4. Tasks are dynamically migrated away from degraded endpoints to healthy local SLMs or alternative cloud providers.

---

## 7. Real-World Evaluation: LogHub Incident Analysis

Instead of relying on synthetic instances, v3 evaluates against realistic multi-step agentic pipelines built from the **LogHub dataset** already in the repository (`data/zookeeper_sample.log`, `data/spark_sample.log`, `data/linux_sample.log`).

```
                    LOGHUB INCIDENT TRIAGE PIPELINE
                    
  [ Raw System Logs ]
          │
          ▼
  ┌────────────────────────────────────────────────────────┐
  │ TASK 1: High-Frequency Log Parsing & Template Structuring
  │ • Role: Regex extraction, timestamp & IP parsing       │
  │ • Volume: Thousands of records                         │
  │ • Ideal Assignment: Local SLM (Llama-3.2-3B / Qwen)   │
  │ • Knobs: Zero-shot, max_tokens=128, temp=0.0           │
  └───────────────────────┬────────────────────────────────┘
                          │ Structured Events
                          ▼
  ┌────────────────────────────────────────────────────────┐
  │ TASK 2: Anomaly Classification & Severity Filtering   │
  │ • Role: Identify error traces, drop routine heartbeats │
  │ • Volume: Hundreds of records                          │
  │ • Ideal Assignment: Fast Cloud API (Gemini / 4o-mini) │
  │ • Knobs: 3-shot exemplars, JSON mode, temp=0.0         │
  └───────────────────────┬────────────────────────────────┘
                          │ Suspect Incident Traces
                          ▼
  ┌────────────────────────────────────────────────────────┐
  │ TASK 3: Root Cause Synthesis & Mitigation Diagnosis   │
  │ • Role: Cross-log causal reasoning, markdown report   │
  │ • Volume: Dozens of incidents                          │
  │ • Ideal Assignment: Frontier API (Claude 3.5 Sonnet)  │
  │ • Knobs: High reasoning effort, reflection_loops=1     │
  └────────────────────────────────────────────────────────┘
```

### Why This Workload Validates v3
- **Demonstrates Natural Tiering:** Proves that a single model choice across the pipeline is wasteful. Using Claude 3.5 Sonnet for Task 1 burns the budget in seconds; using a Local SLM for Task 3 produces shallow, hallucinatory root-cause diagnoses.
- **Measures Real API Constraints:** Directly triggers and tests client-side rate limits (TPM/RPM), network latency, token pricing, and local GPU slot contention under real concurrency.

---

## 8. Traceability & Comparison Matrix: v2 vs. v3

| Architectural Aspect | Architecture v2 | Architecture v3 | Benefit of v3 |
|---|---|---|---|
| **Primary Resource** | Physical GPUs ($B$ GPUs, $n[m]$ servers) | API Dollars ($B_{\$}$), Provider TPM/RPM, Local GPU Slots | Matches real enterprise cloud usage |
| **Execution Reality** | Synthetic simulation (`simulator.py`) | 100% real API & local SLM execution | Eliminates the largest objection to the project |
| **Adjustable Knobs** | Model profile only | 4 Tiers: Model, Reasoning Effort, Prompts, Resilience | Rich, fine-grained optimization |
| **Problem Class** | Capacitated Facility Location | Multi-Choice Multi-Dimensional Knapsack (MMKP) | Cleaner math, faster relaxation |
| **Executor Role** | Unbuildable GPU container manager | Dual-Role Gateway & Resilience Interceptor | Greatly reduced infra scope, high practical value |
| **Solver Structure** | Flat multi-track solver | Hierarchical Two-Stage (Pareto filter + LP Allocator) | Avoids combinatorial explosion; sub-100ms solve |
| **Drift Detection** | Synthetic injected parameter shifts | Deterministic HTTP status, schema validity, token count | Objective, transparent, production-ready |
| **Evaluation Data** | Synthetic instance generators | LogHub multi-step incident triage workflows | Defensible on real data with real tokens |

---

*End of Architecture v3 specification.*
