# Profile-Guided Multi-Workflow Resource Orchestration Platform (Architecture v5)

Senior capstone project — team of 5, advised by Prof. Tossaphol.  
**Active Branch:** `systemarchv5` | **Design of Record:** [`docs/design/System_Architecture_v5.md`](docs/design/System_Architecture_v5.md) | **Test Baseline:** 721 passed, 4 skipped

> ### New here? Start with the guides:
> 1. [`docs/ORIENTATION.md`](docs/ORIENTATION.md) — The entire system explained from zero: problem, architecture, formal model, empirical findings, and roadmap.
> 2. [`docs/REPO_GUIDE.md`](docs/REPO_GUIDE.md) — Exhaustive, file-by-file annotated repository map, module index, reading paths, and change guide.
> 3. [`docs/design/System_Architecture_v5.md`](docs/design/System_Architecture_v5.md) — The active Design of Record establishing Architecture v5.
> 4. [`CLAUDE.md`](CLAUDE.md) — Operational guardrails, core invariants, build order, and settled decisions.

---

## 1. Executive Summary & System Mission

The **Enterprise Orchestration Platform** is a profile-guided, multi-workflow cloud resource orchestration system based on **Murakkab (OSDI '26 / arXiv:2508.18298)**. It jointly determines task-to-profile routing and integer profile instance provisioning across an owned, heterogeneous hardware fleet (CPU, edge GPU, datacenter GPU) to minimize total amortized fleet provisioning cost while guaranteeing capacity sufficiency, budget compliance, and per-task SLA reliability and latency floors under dynamic physical runtime drift.

The platform resolves the fundamental economic trade-off in enterprise agentic workflow serving: maximizing SLA compliance and hardware utilization while avoiding both the prohibitive capital cost of un-multiplexed over-provisioning and the silent SLA failures of static open-loop allocation.

### Authoritative Academic Lineage
All theoretical formulations, capacity models, and baseline comparisons cite and build upon:

> **Chaudhry, G. I., Choukse, E., Qiu, H., Goiri, I., Fonseca, R., Belay, A., & Bianchini, R. (2026).**  
> *Murakkab: Resource-Efficient Agentic Workflow Orchestration in Cloud Platforms.*  
> **Proceedings of the 20th USENIX Symposium on Operating Systems Design and Implementation (OSDI '26)**, pp. 567–587.  
> Preprint: arXiv:2508.18298 [cs.DC].

---

## 2. Mathematical Formulation: Modular Capacitated Facility Location (MCFL)

The offline resource allocation problem is mathematically formulated as **Modular Capacitated Facility Location (MCFL)** with an aggregate hardware knapsack budget constraint ($C3$).

### 2.1 Sets, Parameters, and Decision Variables

$$\begin{aligned}
W & \quad \text{Set of concurrent workflow requests in the batch} \\
T_w & \quad \text{Set of tasks comprising workflow } w \in W; \quad T = \bigcup_{w \in W} T_w \\
M & \quad \text{Catalog of instantiable model/hardware profile configurations } (model, hardware\_tier, config) \\
C(t) \subseteq M & \quad \text{Feasible candidate profile pool eligible for task } t \in T \text{ after SLA floor filtering} \\
\text{load}(t) \in \mathbb{R}^+ & \quad \text{Throughput demand rate of task } t \text{ (requests or tokens per second)} \\
\text{thr}(m) \in \mathbb{R}^+ & \quad \text{Serving throughput capacity of one provisioned instance of profile } m \text{ (req/sec)} \\
\text{gpu}(m) \in \mathbb{Z}_{\ge 0} & \quad \text{Hardware accelerator units (e.g., physical GPUs) consumed per instance of } m \\
\text{price}(m) \in \mathbb{R}^+ & \quad \text{Amortized capital hardware plus baseline power cost per instance of } m \text{ over horizon } H \\
B \in \mathbb{Z}^+ & \quad \text{Total fleet GPU accelerator budget cap} \\
R_{\min}(t), L_{\max}(t) & \quad \text{Contractual reliability floor and latency ceiling for task } t \\
x[t][m] \in \{0, 1\} & \quad \text{Binary routing decision: } 1 \text{ if task } t \text{ is assigned to profile } m; \ 0 \text{ otherwise} \\
n[m] \in \mathbb{Z}_{\ge 0} & \quad \text{Integer provisioning decision: number of instances of profile } m \text{ to deploy}
\end{aligned}$$

### 2.2 Objective Function: Amortized Provisioning Cost

$$\text{minimize} \quad \sum_{m \in M} n[m] \cdot \text{price}(m)$$

*Grounding (Finding F31, Open Item O1):* In an owned cluster or dedicated cloud reservation, instances are energized for the operational horizon; individual task calls incur no incremental rental fee. There is no per-invocation variable term $\sum x[t][m] \cdot \text{varcost}(t,m)$. Monetary savings derive strictly from consolidation: multiplexing multiple tasks onto fewer physical instances.

### 2.3 Constraints

$$\begin{aligned}
\text{(C1) Single Assignment:} & \quad \sum_{m \in C(t)} x[t][m] = 1 && \forall t \in T \\
\text{(C2) Instance Capacity:} & \quad \sum_{t \in T : m \in C(t)} x[t][m] \cdot \text{load}(t) \le n[m] \cdot \text{thr}(m) && \forall m \in M \\
\text{(C3) Fleet Resource Budget:} & \quad \sum_{m \in M} n[m] \cdot \text{gpu}(m) \le B &&
\end{aligned}$$

- **C1 (Indivisible Tasks):** Every task is assigned to exactly one profile within its pre-filtered feasible candidate pool $C(t)$.
- **C2 (Aggregate Coupling & Capacity):** Aggregate routed load must not exceed modular provisioned throughput. In numerical checking (`poc/formulation/invariants.py`), a strict numerical tolerance $\text{TOL} = 10^{-9}$ is enforced to prevent floating-point accumulation errors.
- **C3 (Physical Accelerator Knapsack):** Total physical GPUs consumed cannot exceed cluster budget $B$.

### 2.4 Feasibility-First Candidate Filtering (Principle P3) & UCB Exploration (G10)

Candidate pools $C(t)$ are filtered prior to solver invocation:
$$C(t) = \left\{ m \in M \;\middle|\; \text{rel}_{\text{eval}}(m) \ge R_{\min}(t) \ \land \ \text{lat}_{\text{eval}}(t, m) \le L_{\max}(t) \right\}$$

To prevent premature abandonment of high-performing profiles due to early random failures (Finding F23), $\text{rel}_{\text{eval}}(m)$ evaluates the Upper Confidence Bound (UCB):
$$\text{rel}_{\text{UCB}}(m) = \min\left(1.0, \; \hat{p} + z \sqrt{\frac{\hat{p}(1 - \hat{p})}{\max(\text{trials}, 1)}}\right)$$

### 2.5 Heterogeneous Fleet Decorrelation (Findings F31, F33)
The platform models three physical hardware tiers with decorrelated price and GPU metrics:
1. **CPU Workers ($\text{gpu}=0$):** High CPU throughput for parsing/regex (TDP ~65–125W, negligible capital cost).
2. **Edge GPUs ($\text{gpu}=1$):** Local PCIe accelerators (RTX 4090) hosting quantized SLMs (TDP ~150–250W).
3. **Datacenter Accelerators ($\text{gpu} \in \{2, 4, 8\}$):** High-density SXM nodes (A100, H100) hosting frontier models (TDP 300–700W/card).

Because `heterogeneous_generator.py` enforces near-zero correlation between `price(m)` and `gpu(m)`, constraint (C3) actively binds and drives multi-tier hardware trade-offs.

---

## 3. Core Murakkab Invariants (I1–I5)

Every candidate allocation plan $(x, n)$ generated across all solvers, benchmark runs, and adaptive loops must pass the five invariants asserted in `poc/formulation/invariants.py`:

```
       [Candidate Allocation Result (x, n)]
                        │
                        ▼
      ┌─────────────────────────────────────┐
      │   invariants.check(result, ...)     │
      └──────────────────┬──────────────────┘
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
 [feasible == False]              [feasible == True]
        │                                 │
        ▼                                 ▼
  Record Failure as Data          Assert Invariants I1 - I5:
  (No Invariant Breach)           ├── I1: Single Assignment (C1)
                                  ├── I2: Capacity Sufficiency (C2, TOL=1e-9)
                                  ├── I3: Fleet Budget Compliance (C3)
                                  ├── I4: Floor/Ceiling Feasibility
                                  └── I5: Active Instance Provisioning
```

| Invariant | Name | Formal Rule | Verification Code (`invariants.py`) |
|---|---|---|---|
| **I1** | Assignment Integrity (C1) | $\sum_{m \in C(t)} x[t][m] = 1 \quad \forall t \in T$, $\text{dom}(x) = T$ | `set(routing) == set(by_id)` |
| **I2** | Capacity Sufficiency (C2) | $\sum_{t: x[t]=m} \text{load}(t) \le n[m] \cdot \text{thr}(m) + 10^{-9}$ | `routed <= capacity + 1e-9` |
| **I3** | Fleet Budget Compliance (C3)| $\sum_{m \in M} n[m] \cdot \text{gpu}(m) \le B$ | `gpus <= budget` |
| **I4** | Feasibility Compliance | $x[t] \in C(t) \quad \forall t \in T$ | `profile_id in pools[task_id]` |
| **I5** | Active Provisioning | $\forall m \in \text{range}(x): n[m] \ge 1$ | `provisioning[profile_id] >= 1` |

*Semantics:* When an allocation result declares `result.feasible == False`, `invariants.check()` returns `[]` (empty list); infeasibility under over-constrained budgets is recorded as experimental data rather than an invariant violation.

---

## 4. Ratified Novelty Boundary (O12 / Finding F24)

### 4.1 Novelty Scope Lock (Ratified 3 September 2026)
- **Conceded Ground:** We make **no novelty claim** on the core static optimization problem, conceded as textbook Modular Capacitated Facility Location (CFL) with a knapsack budget constraint.
- **The Core Novelty Claim:** Academic and architectural novelty resides exclusively in the **Event-Driven Adaptive Closed Loop under Dynamic Runtime Drift**:
  $$\text{Observe Telemetry (J6)} \longrightarrow \text{Self-Correct Profiles (J7)} \longrightarrow \text{Detect Drift (J8)} \longrightarrow \text{Sub-100ms Re-Optimization (J9)}$$

### 4.2 Murakkab's Static 60-Minute Epoch Blindness
Murakkab (OSDI '26) operates with three foundational assumptions:
1. Coarse periodic re-optimization on a fixed 60-minute optimization epoch.
2. Pre-calibrated, immutable profile parameters ($\text{lat}, \text{rel}, \text{thr}$).
3. Reactive local autoscaling between epochs without parameter calibration or dynamic task re-routing.

**The Failure Mode:** Under physical hardware throttling (DVFS), workload surges, or model degradation, Murakkab's routing plan remains frozen. Autoscaling merely deploys more degraded instances of the same failing profile, exhausting budget while violating SLA floors.

### 4.3 Empirical Differentiator: Finding F24
Under real Zookeeper log incident workloads (12 tasks, 3 workflows) with reliability floor $R_{\min} = 0.95$ and unannounced physical degradation at round 6 ($0.99 \to 0.55$):
- **Murakkab Static Baseline:** Delivers **$0.542 \pm 0.018$** post-drift reliability (failing SLA on 100% of post-drift rounds) at **$400.00** reported cost. It exhibits **silent failure**: reporting nominal operation while delivering failing service.
- **Adaptive Closed Loop (Ours):** Detects parameter cliff breach ($\Delta R = R_{\text{est}} - R_{\min} < 0.01$), re-optimizes routing in sub-100ms, and delivers **$0.938 \pm 0.014$** reliability (recovering up to $1.000$) at **$1,013.00$** adapted cost.
- **Paired Reliability Gain:** **$+0.424$ [95% CI: 0.405, 0.442]** over the Murakkab static baseline ($p < 10^{-12}$).
- **The Economic Insight:** Comparing baseline cost ($400) to adaptive cost ($1013$) without conditioning on delivered SLA compliance is invalid; the static baseline appears cheaper only because it has silently stopped working.

---

## 5. Architecture v5 Capabilities

### 5.1 Online Self-Correcting Profiles (Closing Gap G2)
Implemented in `prototype/profiling.py` (`ProfileStore`), fulfilling Principle P6 (*"profiles are measured, not declared"*):
- **Dual-Input Service Rate Calibration:** Updates profile throughput from direct rate telemetry ($r_{\text{obs}}$) or latency-implied service rates ($r_{\text{implied}} = \text{thr}_0 \times L_0 / L_{\text{obs}}$).
- **Steady-State Kalman Smoothing:** Dynamically smoothed via exponential moving average ($\beta = 0.2$), equivalent to the steady-state Kalman gain under a 1D Gaussian state-space model.
- **4-Tier Outlier Damping Architecture:**
  1. *Cold-Start Warmup Gate:* Suppresses throughput updates for the first $N_{\text{warmup}} = 3$ observations.
  2. *Huber-Loss Attenuation:* Attenuates learning rate $\beta_{\text{eff}} = \beta / (1 + \text{dev}^2)$ on large deviations ($|r - \text{thr}| / \text{thr} > 0.5$).
  3. *Slew-Rate Limiter:* Restricts maximum single-step throughput adjustment to $\pm 20\%$.
  4. *Global Physiological Bounds:* Clamps throughput strictly within $[\max(0.10 \cdot \text{thr}_0, 1.0), \; 3.0 \cdot \text{thr}_0]$.
- **Thermodynamic Metrics:** Real-time tracking of active energy ($E = P_{\text{avg}} \cdot \Delta t$), electricity cost at $\$0.12/\text{kWh}$, thermodynamic efficiency ($\eta = \text{thr} / P_{\text{avg}}$ req/Joule), and effective cost per watt.

### 5.2 Formal Closed-Loop Benchmark Evaluation Harness (Closing Gap G9)
Implemented in `poc/harness/closed_loop_runner.py` (`ClosedLoopRunner`):
- Multi-epoch evaluation simulating dynamic physical runtime drift:
  - *Thermal Throttling (DVFS):* Clock frequency drops, cutting throughput and doubling latency.
  - *Workload Surges:* Demand multipliers $(1 + s)$ saturating instance headroom.
  - *Network Degradation:* Packet loss and additive transit latency (+120ms).
- Direct matched comparison between Static Murakkab Baseline (60-min blind epoch) and Event-Driven Adaptive Closed Loop.
- Export of quantitative metrics: Delivered Reliability ($R_{\text{del}}$), SLA Floor Violations ($V_{\text{SLA}}$), Cumulative Fleet Cost ($C_{\text{fleet}}$), Re-Optimization Latency ($t_{\text{reopt}}$), and Recovery Time (MTTR).
- Formatted ASCII comparative summary tables and Draft-07 JSON reports.

### 5.3 Concrete DAG Execution Engine & Full Pipeline Mockup
- **Concrete Topological Engine (`prototype/engine.py`):** Kahn's algorithm cycle detection (G4), real LogHub ZooKeeper incident trace parsing, and load-scaled observation emission (G3).
- **Full J1–J10 Pipeline Mockup (`prototype/pipeline_mockup.py`):** Executable end-to-end lifecycle demonstration across nominal execution, drift injection, instant drift detection, and sub-100ms global re-optimization.

---

## 6. Quickstart & CLI Verification

All commands below are verified to execute cleanly with zero invariant violations:

### 1. Run the Full End-to-End Pipeline Mockup (J1–J10)
```bash
python -m prototype.pipeline_mockup
```
*Demonstrates ingestion of real ZooKeeper logs, Track C allocation, drift injection, parameter cliff detection, automated re-optimization, and 100% SLA restored execution.*

### 2. Run the 15-Track Static Optimizer Sweep
```bash
python -m poc.harness.runner
```
*Evaluates 150 problem instances comparing Exact MILP against Track A heuristics, Track B Lagrangian relaxation, and Track C LP relaxation + repair.*

### 3. Run the Multi-Epoch Closed-Loop Benchmark Harness (G9)
```bash
python -c "from poc.harness.closed_loop_runner import ClosedLoopConfig, compare, export_summary_table; b, a = compare(ClosedLoopConfig(total_rounds=10, epoch_length=5)); print(export_summary_table(b, a))"
```
*Executes a multi-epoch matched comparison contrasting the static Murakkab baseline against our adaptive closed loop, printing a formatted comparative ASCII table.*

### 4. Run the Full Automated Regression Test Suite
```bash
python -m pytest poc/tests/ prototype/tests/ -q
```
*Verifies algorithmic correctness, invariant enforcement, self-correcting profiles, and benchmark harnesses:* **721 passed, 4 skipped in ~90s**.

---

## 7. Annotated Repository Layout Map

```
EnterpriseOrches/
├── .gitignore                                      # Git ignore rules
├── BRANCHES.md                                     # Branch register and migration history
├── CLAUDE.md                                       # Working summary, invariants, and guardrails
├── HANDOFF.md                                      # Session handoff records and open items
├── PLAN.md                                         # Implementation roadmap
├── PROGRESS.md                                     # Overall project progress tracker
├── README.md                                       # Root front door (this document)
├── pytest.ini                                      # Pytest configuration
├── requirements.txt                                # Python dependencies (pulp, numpy, pytest)
│
├── data/                                           # Domain trace data and batch manifests
│   ├── eval_batches/
│   │   └── eval_batch_3workflows.json              # 3-workflow ZooKeeper evaluation batch
│   ├── linux_sample.log                            # Linux system log trace sample
│   ├── spark_sample.log                            # Apache Spark execution log sample
│   └── zookeeper_sample.log                        # Apache ZooKeeper consensus log sample
│
├── docs/                                           # Documentation corpus
│   ├── ORIENTATION.md                              # Comprehensive onboarding guide from zero
│   ├── README.md                                   # Documentation index and reading paths
│   ├── REPO_GUIDE.md                               # Authoritative repository guide and module index
│   │
│   ├── design/                                     # Architecture specifications & gap registers
│   │   ├── System_Architecture_v5.md               # ACTIVE DESIGN OF RECORD (Architecture v5)
│   │   ├── System_Architecture_v4.md               # Design predecessor (Murakkab capacity model)
│   │   ├── System_Architecture_v3.md               # Retracted API detour (withdrawn)
│   │   ├── System_Architecture_v2.md               # Foundational predecessor (T0 formulation)
│   │   ├── component_gaps.md                       # G1–G10 gap resolution registry
│   │   ├── component_reference.md                  # Component specifications and roles
│   │   └── pipeline.md                             # End-to-end ASCII pipeline diagram
│   │
│   ├── evidence/                                   # Empirical benchmarks and findings
│   │   ├── chapter3_benchmark_results.md           # Chapter 3 scale benchmark tables
│   │   ├── poc_findings.md                         # Authoritative chronological log (F1–F35)
│   │   └── poc_findings_summary.md                 # Executive findings summary & corrections table
│   │
│   ├── presentation/                               # Presentation decks
│   │   └── T0_full_deck.html                       # 30-slide self-contained HTML deck
│   │
│   ├── proposal/                                   # Capstone deliverables
│   │   ├── D11_poc_report.md                       # PoC report for advisor
│   │   ├── M1_Proposal_Presentation_Slides.md      # Proposal presentation slides
│   │   ├── PoC_and_Validation_Plan.md              # Validation plan and risk analysis
│   │   └── proposal_narrative.md                   # Proposal narrative & Chapter 3 running order
│   │
│   ├── research_papers/                            # Curated literature database (Murakkab, etc.)
│   └── sessions/                                   # Ratification briefings and study guide
│
├── poc/                                            # Core mathematical formulation & solver tracks
│   ├── README.md                                   # PoC package guide
│   ├── core/                                       # Shared subroutines (provisioning, decision rule)
│   ├── formulation/                                # Data models (types.py) and Invariants I1–I5
│   ├── harness/                                    # Static runner & G9 closed_loop_runner.py
│   ├── instances/                                  # Generators (uniform, structured, heterogeneous)
│   ├── tests/                                      # 15 test modules (invariants, tracks, harness)
│   └── tracks/                                     # Solvers: exact_milp, track_a, track_b, track_c_lp
│
├── prototype/                                      # Concrete execution engine & adaptive closed loop
│   ├── README.md                                   # Prototype package guide
│   ├── engine.py                                   # Concrete DAG topological execution engine
│   ├── ingestion.py                                # Workflow ingestion & Kahn's cycle check (G4)
│   ├── loop.py                                     # End-to-end adaptive orchestration loop
│   ├── pipeline_mockup.py                          # Full J1–J10 pipeline mockup script
│   ├── profiling.py                                # Online ProfileStore (G2) & DriftDetector (G6/G7)
│   ├── registry.py                                 # Profile registry & candidate pool resolver (G10)
│   ├── reoptimisation.py                           # Global & scoped re-optimization (G8)
│   ├── simulator.py                                # Telemetry simulator
│   └── tests/                                      # 8 test modules (engine, loop, profiling_v5, stress)
│
└── scripts/                                        # Finding reproduction audits & data preparation
    ├── audit_budget_binding.py                     # T3/F33 budget binding audit
    ├── audit_f20_subset.py                         # T2/F32 subset move audit
    ├── audit_t1_arms.py                            # T1/F35 relaxation arms audit
    ├── generate_chapter3_tables.py                 # Benchmark table generator
    └── prepare_multiworkflow_batch.py              # LogHub ZooKeeper batch preparation
```

---

## 8. Navigating the Documentation

| To learn about... | Read this document |
|---|---|
| Complete project onboarding from zero | [`docs/ORIENTATION.md`](docs/ORIENTATION.md) |
| Every file in the repository explained | [`docs/REPO_GUIDE.md`](docs/REPO_GUIDE.md) |
| Active Design of Record & technical specs | [`docs/design/System_Architecture_v5.md`](docs/design/System_Architecture_v5.md) |
| Architectural gap resolutions (G1–G10) | [`docs/design/component_gaps.md`](docs/design/component_gaps.md) |
| Concrete execution engine & prototype guide | [`prototype/README.md`](prototype/README.md) |
| Empirical findings and statistical corrections | [`docs/evidence/poc_findings_summary.md`](docs/evidence/poc_findings_summary.md) |
| Coding guardrails and settled decisions | [`CLAUDE.md`](CLAUDE.md) |

---

## 9. Capstone Team & Ownership

| ID | Responsibilities | Focus |
|---|---|---|
| **035** | Greedy construction, subset consolidation, DAG cycle validation (G4) | Track A, Ingestion |
| **075** | Mathematical formulation, Track B Lagrangian relaxation, Track C LP relaxation | Tracks B & C |
| **077** | Online self-correcting profiling (G2), drift detection, closed loop | Prototype, Profiling |
| **083** | Heterogeneous fleet generator (F31), repository architecture, data preparation | Infrastructure |
| **089** | Exact MILP baseline, static harness, G9 closed-loop benchmark harness | Evaluation, Harness |
