# Architectural Component Gaps — Registry & Resolution Matrix

**What this is.** A comprehensive registry of architectural gaps identified during loop decomposition (J1 through J10). Originally catalogued as areas where early prototypes omitted functionality or used placeholders, **all ten architectural gaps (G1–G10) have been fully resolved** in System Architecture v4 and v5.

**Design of Record Reference:** [`System_Architecture_v5.md`](System_Architecture_v5.md) (§7.1, §7.2, §7.3).  
**Companion Documents:** [`component_reference.md`](component_reference.md) for full component specifications, and [`../evidence/poc_findings.md`](../evidence/poc_findings.md) for empirical benchmark logs.

---

## Master Gap Resolution Matrix

| Gap ID | Description | Original Limitation | Status | Resolved In | Implementation File | Verification Test Suite |
|---|---|---|---|---|---|---|
| **G1** | Task Demand Scaling | Load was uniform per task type, ignoring input log volume | **Resolved** | Architecture v4 / v5 | `prototype/ingestion.py` (`_scale_load_by_input`) | `prototype/tests/test_loop.py` |
| **G2** | Online Self-Correcting Profiles | Throughput and price were static; only latency & reliability adapted | **Resolved** | Architecture v5 | `prototype/profiling.py` (`ProfileStore.record`) | `prototype/tests/test_profiling_v5.py`, `test_profiling_stress.py` |
| **G3** | Load-Scaled Telemetry Emission | Simulator emitted exactly 1 observation per task regardless of load | **Resolved** | Architecture v4 / v5 | `prototype/engine.py` (`WorkflowExecutionEngine`) | `prototype/tests/test_engine.py` |
| **G4** | DAG Acyclicity Verification | Ingestion parsed dependencies without checking for cycles | **Resolved** | Architecture v4 / v5 | `prototype/ingestion.py` (`_validate_acyclic`), `engine.py` | `prototype/tests/test_loop.py`, `test_engine.py` |
| **G5** | Snapshot Verb Disambiguation | Method name collision between profile snapshot and provisioning backtrack | **Resolved** | Architecture v4 / v5 | `prototype/profiling.py` vs `poc/core/provisioning.py` | `poc/tests/test_provisioning.py` |
| **G6** | Solver Invocation in Drift Check | Drift detector invoked full solver to evaluate compatibility score | **Resolved** | Architecture v4 / v5 | `prototype/profiling.py` (`DriftDetector.check`) | `prototype/tests/test_profiling.py` |
| **G7** | Parameter Cliff Blindness | Decision-space check was blind to degrading reliability near SLA floor | **Resolved** | Architecture v4 / v5 | `prototype/profiling.py` (Tier 1 Parameter Margin) | `prototype/tests/test_profiling.py`, `test_loop.py` |
| **G8** | Runtime Re-Optimization Wiring | `reoptimisation.py` was disconnected from runtime loop | **Resolved** | Architecture v4 / v5 | `prototype/loop.py` (`reoptimise_global`) | `prototype/tests/test_loop.py` |
| **G9** | Closed-Loop Evaluation Harness | Static harness evaluated single-shot optimization without drift | **Resolved** | Architecture v5 | `poc/harness/closed_loop_runner.py` (`ClosedLoopRunner`) | `poc/tests/test_closed_loop_harness.py`, `test_closed_loop_adversarial.py` |
| **G10**| Optimistic UCB Candidate Filtering| Raw reliability estimates caused premature profile abandonment | **Resolved** | Architecture v4 / v5 | `prototype/profiling.py` (`reliability_upper_bound`) | `prototype/tests/test_registry.py` |

---

## Detailed Gap Analyses & Resolution Records

### G1 · J1 — Task Demand Scaling via Input Volume
- **Component:** `prototype/ingestion.py` (`ingest`)
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** The v2 formulation required per-task `load(t)`. The manifest only specified task types, causing all tasks of the same type to collapse to identical demand regardless of input size.
- **Resolution:** `prototype/ingestion.py` implements `scale_load_by_input=True`. When parsing workflow tasks, it inspects `manifest["input_data"]["log_lines"]` and scales base demand proportionally:
  $$\text{load}(t) = \text{base\_load} \times \max\left(0.5, \; \min\left(2.5, \; \frac{\text{log\_lines}}{\text{reference\_lines}}\right)\right)$$
  Differentiates task demands across workflows (e.g. 181 vs 150 vs 138 lines in ZooKeeper test batches).
- **Reference:** `System_Architecture_v5.md` §7.1; verified in `prototype/tests/test_loop.py`.

---

### G2 · Online Self-Correcting Profiles for Throughput and Effective Cost
- **Component:** `prototype/profiling.py` (`ProfileStore`)
- **Status:** **Resolved** (Architecture v5)
- **Original Gap:** Only latency and reliability updated dynamically. Throughput, GPU count, and price were static, violating Principle P6 (*"profiles are measured, not declared"*) and allowing misdeclared throughput to silently corrupt capacity constraint (C2).
- **Resolution:** Architecture v5 implements online calibration in `ProfileStore.record()`:
  1. **Dual-Input Calibration:** Ingests direct throughput telemetry ($r_{\text{obs}}$) or computes latency-implied service rates ($r_{\text{implied}} = \text{thr}_0 \times L_0 / L_{\text{obs}}$).
  2. **Steady-State Kalman Filtering:** Smooths throughput via exponential moving average ($\beta = 0.2$), equivalent to the steady-state Kalman gain under Gaussian process noise.
  3. **4-Tier Outlier Damping Architecture:**
     - *Warmup Gate:* Suppresses updates for first $N_{\text{warmup}} = 3$ observations.
     - *Huber-Loss Attenuation:* Dampens updates when relative deviation $> 50\%$ ($\beta_{\text{eff}} = \beta / (1 + \text{dev}^2)$).
     - *Slew-Rate Limiter:* Restricts maximum single-step adjustment to $\pm 20\%$.
     - *Physiological Clamping:* Enforces throughput strictly within $[\max(0.10 \cdot \text{thr}_0, 1.0), \; 3.0 \cdot \text{thr}_0]$.
  4. **Thermodynamic Metrics:** Computes active energy ($E = P_{\text{avg}} \cdot \Delta t$), energy cost at $\$0.12/\text{kWh}$, effective instance cost, and thermodynamic efficiency ($\eta = \text{thr} / P_{\text{avg}}$ req/Joule) across CPU, Edge GPU, and Datacenter GPU tiers.
- **Reference:** `System_Architecture_v5.md` §7.2; verified in `prototype/tests/test_profiling_v5.py` and `test_profiling_stress.py`.

---

### G3 · Load-Scaled Telemetry Emission
- **Component:** `prototype/engine.py` (`WorkflowExecutionEngine`)
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** Early simulator emitted exactly one observation per task per round regardless of routed load, decoupling evidence accumulation rate from provisioned capacity.
- **Resolution:** The concrete DAG execution engine in `prototype/engine.py:252-257` scales observation emission proportionally to task demand:
  $$N_{\text{obs}} = \max\left(1, \; \text{round}\left(\frac{\text{load}(t)}{3.0}\right)\right)$$
  Heavily-loaded tasks generate proportionately more telemetry observations, driving faster Bayesian and Kalman convergence in `ProfileStore`.
- **Reference:** `System_Architecture_v5.md` §7.1; verified in `prototype/tests/test_engine.py`.

---

### G4 · DAG Acyclicity Verification via Kahn's Algorithm
- **Component:** `prototype/ingestion.py` (`_validate_acyclic`), `prototype/engine.py`
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** Manifest parsing validated node existence but did not detect cycles (`n1 -> n2 -> n1`).
- **Resolution:** Implemented Kahn's algorithm for topological sorting and cycle detection at admission time. Computes in-degrees for all workflow nodes and iteratively removes sources. If unvisited nodes remain, raises `InvalidBatch` with a descriptive cycle error before solver invocation.
- **Reference:** `System_Architecture_v5.md` §7.1; verified in `prototype/tests/test_loop.py` and `prototype/tests/test_engine.py`.

---

### G5 · Disambiguation of `snapshot()` Verbs
- **Components:** `prototype/profiling.py`, `poc/core/provisioning.py`
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** `ProfileStore.snapshot()` (exporting measured profile specs) collided conceptually with `ProvisioningState.snapshot()` (backtracking search state).
- **Resolution:** Renamed profile export to `export_profile_snapshot()` while reserving `snapshot()` and `restore_snapshot()` strictly for `ProvisioningState` backtracking. Fully documented in component interfaces.
- **Reference:** `System_Architecture_v5.md` §7.1; verified in `poc/tests/test_provisioning.py`.

---

### G6 & G7 · Lightweight Parameter Cliff Monitoring & Candidate Caching
- **Component:** `prototype/profiling.py` (`DriftDetector`)
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** Drift detection ran the entire combinatorial optimizer to compute decision compatibility, and the runtime loop called it a second time upon drift firing (G6). Furthermore, the decision check was completely blind to profiles drifting toward SLA floors until an allocation flipped (G7).
- **Resolution:**
  1. **Tier 1 Parameter Cliff Margin Check:** Compares updated profile estimates against task SLA floors:
     $$\Delta R = R_{\text{est}}(m) - R_{\min}(t) < 0.01 \quad \text{or} \quad \Delta L = L_{\max}(t) - L_{\text{est}}(m) < 5.0\text{ms}$$
     Fires immediate drift signal without invoking the solver, short-circuiting overhead.
  2. **Candidate Caching:** When Tier 2 decision compatibility check executes, the computed allocation is cached in `DriftSignal.candidate`. The runtime loop (`prototype/loop.py:178`) consumes the cached plan, eliminating duplicate solver runs.
- **Reference:** `System_Architecture_v5.md` §7.1, §8.2; verified in `prototype/tests/test_profiling.py`.

---

### G8 · Runtime Loop Re-Optimization Integration
- **Components:** `prototype/loop.py`, `prototype/reoptimisation.py`
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** `reoptimisation.py` existed only as an isolated test script for the O9 scoped-reoptimization experiment and was never imported by `prototype/loop.py`.
- **Resolution:** `prototype/loop.py:173-183` directly imports and wires `reoptimise_global()`. When drift is confirmed, the loop executes global re-optimization passing the cached candidate, persists new versioned assignment ($v_{k+1}$), and falls back gracefully if re-optimization fails.
- **Reference:** `System_Architecture_v5.md` §7.1, §8.1; verified in `prototype/tests/test_loop.py`.

---

### G9 · Formal Multi-Epoch Closed-Loop Benchmark Evaluation Harness
- **Component:** `poc/harness/closed_loop_runner.py` (`ClosedLoopRunner`)
- **Status:** **Resolved** (Architecture v5)
- **Original Gap:** `poc/harness/runner.py` was a static single-shot optimizer sweep with no temporal execution, no telemetry emission, and no ability to benchmark delivered reliability under physical drift.
- **Resolution:** Implemented `ClosedLoopRunner` in `poc/harness/closed_loop_runner.py`:
  - Multi-round, multi-epoch execution simulating physical drift scenarios (DVFS thermal throttling, demand floods, network congestion).
  - Direct comparative benchmarking of Static Murakkab Baseline (60-minute blind epoch) vs Event-Driven Adaptive Closed Loop.
  - Quantitative measurement of delivered reliability ($R_{\text{del}}$), SLA violations ($V_{\text{SLA}}$), fleet cost ($C_{\text{fleet}}$), solver latency ($t_{\text{reopt}}$), and recovery time (MTTR).
  - Formatted ASCII comparative summary tables and RFC 7159 / Draft-07 JSON schema audit reports.
- **Reference:** `System_Architecture_v5.md` §7.3; verified in `poc/tests/test_closed_loop_harness.py` and `test_closed_loop_adversarial.py`.

---

### G10 · Optimistic UCB Reliability Candidate Filtering
- **Components:** `prototype/profiling.py`, `prototype/registry.py`, `poc/harness/closed_loop_runner.py`
- **Status:** **Resolved** (Architecture v4 / v5)
- **Original Gap:** ProfileStore implemented Upper Confidence Bound (`reliability_upper_bound`), but the runtime loop defaulted `optimistic_eligibility=False`. Early random failures caused good profiles to be prematurely dropped from $C(t)$ without opportunity to recover (Finding F23).
- **Resolution:** Enabled optimistic UCB exploration by default in `prototype/registry.py` and `poc/harness/closed_loop_runner.py` (`ClosedLoopConfig.optimistic_eligibility = True`). Uses Beta-Binomial upper confidence bound with $z=1.96$ (defaulting to 1.0 for cold-start profiles with zero observations), ensuring statistical confidence before disqualifying any profile.
- **Reference:** `System_Architecture_v5.md` §7.1; verified in `prototype/tests/test_registry.py`.

---

## Recorded as *by design* — do not raise these as bugs

Noticed while reading, ratified elsewhere. Listed so the next reader does not re-open them.

| | Observation | Where it is settled |
|---|---|---|
| **No time dimension.** | `load` is a *rate*, not a duration. Nothing has a start, finish or makespan | `System_Architecture_v5.md` §1.9; `CLAUDE.md` |
| **No arrival dynamics.** | The batch is frozen at J1 and re-executed unchanged every round. Nothing "triggers"; no workflow is busier than another | `System_Architecture_v5.md` §1.9 — no queueing, no autoscaling |
| **No precedence in the optimisation.** | DAG edges are parsed and order topological execution in engine, but do not constrain offline resource sizing | `System_Architecture_v5.md` §1.9; settled rule 3 |
| **No resource *location*.** | (C3) is one undifferentiated integer `B`. No hosts, no placement, no affinity, no fragmentation | `System_Architecture_v5.md` §2.6 formulation |
| **Order-dependence is the heuristic's, not the problem's.** | The true optimum is order-free; greedy's answer is not | Finding T2; fixture `adversarial_3t2p` |
| **J9 re-optimisation is global, not scoped.** | Scoped re-optimization is vacuous under high profile sharing and costs 22–51% more | Finding F18; `prototype/tests/test_reoptimisation.py` |
