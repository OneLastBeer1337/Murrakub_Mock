# `prototype/` — Event-Driven Adaptive Closed Loop & Concrete Execution Engine

**Architecture Role:** The tangible operational manifestation of the platform's core novelty boundary (**O12 / Finding F24**). It closes the feedback loop around Murakkab's static formulation by realizing Principle P6 (*"profiles are measured, not declared"*), executing concrete workflow DAGs on real system logs, dynamically self-correcting profile throughput and cost (G2), and triggering sub-100ms re-optimization upon parameter drift.

**Design of Record Reference:** [`docs/design/System_Architecture_v5.md`](../docs/design/System_Architecture_v5.md) (§6, §7.1, §7.2, §8).

---

## 1. Concrete DAG Topological Execution Engine (`engine.py`)

`prototype/engine.py` implements the `WorkflowExecutionEngine` (Jobs J5 and J6), replacing synthetic placeholders with concrete DAG execution:
- **Kahn's Topological Sort (G4):** Validates acyclicity and computes a valid topological dispatch sequence across workflow tasks at admission time.
- **Real Trace Data Flow:** Processes real Apache ZooKeeper LogHub records (`data/eval_batches/eval_batch_3workflows.json`) across four concrete task types:
  1. `parse_log_line`: Ingests raw log lines, parses timestamps, log levels, thread names, and socket endpoints.
  2. `classify_severity`: Evaluates error frequencies and anomaly counts into `NORMAL`, `WARNING`, or `CRITICAL`.
  3. `enrich_context`: Resolves quorum membership (Leader, Follower, Listener) and peer IP connections.
  4. `generate_report`: Produces structured, human-readable incident mitigation recommendations.
- **Load-Scaled Telemetry Interception (G3):** Scales emitted telemetry observations proportionally to routed task demand:
  $$N_{\text{obs}} = \max\left(1, \; \text{round}\left(\frac{\text{load}(t)}{3.0}\right)\right)$$
  ensuring heavily-loaded workflows generate proportionately more evidence for rapid Bayesian and Kalman profile convergence.
- **Runtime Degradation Injection:** Supports explicit degradation scheduling (`schedule_degradation`) to simulate thermal throttling, clock throttling, and network latency jitter.

---

## 2. Online Self-Correcting ProfileStore (G2) & Drift Detection (`profiling.py`)

`prototype/profiling.py` implements the online calibration engine, fulfilling Principle P6:
- **Dual-Input Service Rate Estimation:** Updates profile throughput dynamically via direct rate telemetry ($r_{\text{obs}}$) or latency-implied service rates:
  $$r_{\text{implied}} = \text{thr}_0 \cdot \left(\frac{L_0}{\max(L_{\text{obs}}, 10^{-3})}\right)$$
- **Steady-State Kalman Filtering:** Smooths throughput via exponential moving average ($\beta = 0.2$), equivalent to steady-state Kalman gain under a 1D Gaussian state-space model.
- **4-Tier Outlier Damping Architecture:**
  1. *Cold-Start Warmup Gate:* Suppresses throughput updates for the first $N_{\text{warmup}} = 3$ observations.
  2. *Huber-Loss Attenuation:* Attenuates learning rate $\beta_{\text{eff}} = \beta / (1 + \text{dev}^2)$ on large deviations ($|r - \text{thr}| / \text{thr} > 0.5$).
  3. *Slew-Rate Limiter:* Restricts maximum single-step adjustment to $\pm 20\%$.
  4. *Global Physiological Bounds:* Clamps throughput strictly within $[\max(0.10 \cdot \text{thr}_0, 1.0), \; 3.0 \cdot \text{thr}_0]$.
- **Thermodynamic Metrics:** Real-time tracking of active energy ($E = P_{\text{avg}} \cdot \Delta t$), energy cost at $\$0.12/\text{kWh}$, thermodynamic efficiency ($\eta = \text{thr} / P_{\text{avg}}$ req/Joule), and effective cost per watt across CPU, Edge GPU, and Datacenter GPU tiers.
- **Two-Tier Drift Detection (G6/G7):**
  - *Tier 1 Parameter Cliff Margin Check:* Instantly flags parameter degradation near SLA floors ($\Delta R < 0.01$, $\Delta L < 5.0\text{ms}$) without invoking the solver.
  - *Tier 2 Decision Compatibility Check:* Computes decision churn and caches the would-be allocation plan in `DriftSignal.candidate` to eliminate duplicate solver invocations.

---

## 3. Full J1–J10 Pipeline Mockup (`pipeline_mockup.py`)

`prototype/pipeline_mockup.py` is the executable end-to-end demonstration of the complete lifecycle:
```bash
python -m prototype.pipeline_mockup
```

### Execution Walkthrough
1. **J1 (Ingestion):** Ingests ZooKeeper evaluation batch, validates DAG acyclicity via Kahn's algorithm (G4), and scales demand by log lines (G1).
2. **J2 (Candidate Pools):** Builds candidate pools $C(t)$ using optimistic UCB reliability floors (G10).
3. **J3 & J4 (Allocation):** Solves multi-workflow placement via Track C LP relaxation, persisting assignment `v0` ($400.00, 4/8 GPUs).
4. **J5 & J6 (Execution):** Dispatches real log events through the topological engine, outputs structured incident reports, and intercepts 18 load-scaled observations (G3).
5. **Drift Injection:** Injects thermal throttling on `classify_severity-cheap` ($R: 0.96 \to 0.45$, $L: 60\text{ms} \to 280\text{ms}$).
6. **J7 & J8 (Profiling & Drift):** Online `ProfileStore` records degraded telemetry; `DriftDetector` immediately flags parameter cliff breach ($\Delta R = -0.1607, \Delta L = -1.6\text{ms}$).
7. **J9 (Re-Optimization):** Automatically triggers global re-optimization (`reoptimise_global()`), migrating affected tasks to `classify_severity-solid` in 37.6ms, persisting assignment `v1` ($560.00, 5/8 GPUs).
8. **Round 3 Execution:** Dispatches work under adapted plan, restoring delivered SLA compliance to 100%.
9. **J10 (Executive Summary):** Prints comparative scorecard contrasting Murakkab static baseline failure vs our adaptive closed loop.

---

## 4. Module Directory & Responsibilities

| File | Lines | Job | What it is |
|---|---|---|---|
| **`engine.py`** | 346 | J5/J6 | Concrete DAG topological execution engine, LogHub ZooKeeper processing, load-scaled telemetry (G3), and Kahn's cycle check (G4) |
| **`pipeline_mockup.py`** | 249 | J1–J10 | Full end-to-end pipeline mockup script demonstrating the complete closed-loop lifecycle |
| **`loop.py`** | 184 | — | Closed-loop controller orchestrating rounds, assignment versioning, drift detection, and re-optimization handoff |
| **`ingestion.py`** | 119 | J1 | Workflow DAG ingestion, Kahn's cycle check (G4), input volume demand scaling (G1), and batch freezing |
| **`registry.py`** | 95 | J2 | Executor Registry and candidate pool resolver with optimistic UCB reliability bounds (G10) |
| **`profiling.py`** | 424 | J7/J8 | Online self-correcting `ProfileStore` (G2) with 4-tier damping, thermodynamic metrics, and Two-Tier `DriftDetector` (G6/G7) |
| **`reoptimisation.py`** | 129 | J9 | Global re-optimization (`reoptimise_global()`) and scoped re-optimization subroutines |
| **`simulator.py`** | 121 | J5/J6 | Synthetic workflow telemetry simulator (fallback alternative to concrete engine) |

### Test Suite (`prototype/tests/`)

| Test Module | Lines | What it covers |
|---|---|---|
| `test_engine.py` | 245 | Concrete DAG topological execution engine, Kahn's cycle check (G4), load-scaled observation emission (G3), and LogHub trace processing |
| `test_profiling_v5.py` | 589 | Architecture v5 G2 self-correcting profiling suite: dual-input rate updates, 4-tier damping architecture, Kalman EMA, thermodynamic efficiency |
| `test_profiling_stress.py` | 511 | Chaos fuzzing, multithreaded snapshot isolation, rapid oscillation damping, transient GC pause spikes |
| `test_loop.py` | 227 | End-to-end closed-loop adaptation, versioning, parameter cliff detection, anti-thrashing |
| `test_profiling.py` | 186 | Core ProfileStore, Beta-Binomial reliability estimation, EMA latency |
| `test_registry.py` | 69 | Registry type filtering and candidate pool resolution C(t) |
| `test_reoptimisation.py` | 167 | Global vs scoped re-optimization scoping tests (O9 / F18) |
