# T0 / D1: Mathematical Formulation Ratification & Advisor Briefing Note

> **Two T0 documents exist and they do different jobs.** This one is the **formal statement of
> the model being ratified** — the mathematics, the problem classification, and the reasoning
> behind the floor-versus-objective choice. [`T0_briefing.md`](T0_briefing.md) is the **agenda
> for running the 8 September session**: confirm-or-object, a default for every item, and the
> sign-off template. Read this for *what* is being ratified; read that to *run the meeting*.

**Project:** Profile-Guided Multi-Workflow Resource Orchestration Platform  
**Target Milestone:** $T_0 / D_1$ (Formulation Ratification) — **8 September 2026**  
**Stakeholders:** 5 Senior Capstone Engineers (Roles: 035, 075, 077, 083, 089), Advisor (Prof. Tossaphol)  
**Primary Reference:** `docs/System_Architecture_v2.md` §1  
**Supporting Benchmarks:** `docs/poc_findings_summary.md`, `docs/chapter3_benchmark_results.md`  

---

## 1. Executive Summary & Purpose

This briefing document establishes the formal mathematical programming model for the capstone project. In accordance with the Project Validation Plan (`docs/PoC_and_Validation_Plan.md`), milestone $T_0 / D_1$ requires all team members and the advisor to ratify Section 1 of the architecture before proceeding into Semester 2 implementation.

The Proof-of-Concept (PoC) phase has rigorously verified this formulation across **647 unit tests**, hand-calculated adversarial fixtures, and multi-scale benchmarks (8 to 64 tasks) on three instance generators. This briefing outlines the exact mathematical model, presents the theoretical problem classification, and addresses the critical architectural decision: **whether reliability should be enforced as a hard SLA floor constraint or treated as an objective optimization term.**

> **ANSWERED 3 September 2026 — the advisor confirmed reliability is a FLOOR, not an
> objective (open question O10).** That is **Option A** below, which is what this document
> already recommended. §1.9 stands, the objective remains single-term provisioning cost, and
> the session does not need to re-litigate it. The comparison is kept because the reasoning is
> what a reader should be able to reconstruct if asked why.

---

## 2. The Formal Optimization Model

The system solves an offline, joint resource allocation problem across multiple concurrent workflow DAGs:

### 2.1 Sets and Parameters
- $T$: The set of all tasks across all submitted workflows in the scheduling horizon.
- $M$: The catalog of available model execution profiles (instantiable `[model, hardware_tier, batch_config]` tuples).
- $\text{load}(t) \in \mathbb{R}^+$: Throughput demand of task $t$ (tokens or requests per second).
- $\text{thr}(m) \in \mathbb{R}^+$: Sustained throughput capacity of a single provisioned instance of profile $m$.
- $\text{gpu}(m) \in \mathbb{Z}^+$: Physical GPUs consumed by one instance of profile $m$.
- $\text{price}(m) \in \mathbb{R}^+$: Dollar cost of running one instance of profile $m$ over the scheduling horizon.
- $B \in \mathbb{Z}^+$: Total cluster GPU budget cap.
- $R_{\min}(t) \in [0, 1]$: Minimum acceptable reliability SLA for task $t$.
- $L_{\max}(t) \in \mathbb{R}^+$: Maximum acceptable latency SLA for task $t$.
- $\text{rel}(m) \in [0, 1]$: Empirical reliability score of profile $m$ (estimated via decayed counting estimator).
- $\text{lat}(t, m) \in \mathbb{R}^+$: Profiling latency of task $t$ on profile $m$.

### 2.2 Candidate Eligibility Construction
Candidate profiles for each task are filtered strictly by SLA floors prior to optimization:
$$C(t) = \{ m \in M : \text{rel}(m) \ge R_{\min}(t) \quad \text{and} \quad \text{lat}(t, m) \le L_{\max}(t) \}$$

### 2.3 Decision Variables
- $x[t][m] \in \{0, 1\}$: Binary routing variable; $1$ if task $t$ is routed to profile $m \in C(t)$, $0$ otherwise.
- $n[m] \in \mathbb{Z}^+$: Integer provisioning variable; number of dedicated instances of profile $m$ provisioned.

### 2.4 Mathematical Program
$$\min_{x, n} \quad \sum_{m \in M} n[m] \cdot \text{price}(m)$$
$$\text{subject to:}$$
$$(C_1) \quad \sum_{m \in C(t)} x[t][m] = 1 \quad \forall t \in T \quad \text{(Unit Assignment)}$$
$$(C_2) \quad \sum_{t: m \in C(t)} x[t][m] \cdot \text{load}(t) \le n[m] \cdot \text{thr}(m) \quad \forall m \in M \quad \text{(Capacity Coverage)}$$
$$(C_3) \quad \sum_{m \in M} n[m] \cdot \text{gpu}(m) \le B \quad \text{(Global GPU Budget)}$$
$$x[t][m] \in \{0, 1\} \quad \forall t \in T, m \in C(t)$$
$$n[m] \in \{0, 1, 2, \dots\} \quad \forall m \in M$$

---

## 3. Mathematical Classification & Justification

Formally, this model belongs to the class of **Modular Capacitated Facility Location Problems with a Budget Constraint (MCFLP-B)**:
- **Facilities:** Model profiles $m \in M$.
- **Facility Capacity:** Modular units $n[m] \cdot \text{thr}(m)$ opened in integer steps.
- **Customers:** Workflow tasks $t \in T$ with non-negative demands $\text{load}(t)$.
- **Side Constraint:** Knapsack-style global resource ceiling $\sum n[m] \cdot \text{gpu}(m) \le B$.

### Why this classification matters:
1. **Coupling Structure:** (C2) couples tasks to each other because instance provisioning costs are step-functions of aggregate routed load.
2. **Lagrangian Duality:** It formally proves why relaxing $(C_1)$ decouples per profile into 0/1 knapsacks (Track B), while relaxing $(C_3)$ decouples per task (Track B-C3).
3. **Academic Lineage:** Bridges cloud systems literature (Murakkab, OSDI '26; Fast Heterogeneous Serving, Cheng & Nguyen 2026) with classic combinatorial optimization.

---

## 4. Key Architectural Decision: Reliability Floor vs. Multi-Objective

A fundamental question for ratification is how reliability requirements should enter the formulation:

```
[Option A: Hard SLA Floor Constraint (Current)]
  Task Floor: rel(m) >= R_min(t) applied during candidate pool construction C(t).
  Objective: Minimize dollar provisioning cost under fixed GPU budget.

[Option B: Multi-Objective / Weighted Optimization]
  Objective: Minimize Cost - gamma * Reliability
  or computing multi-dimensional Pareto frontiers across Cost and Quality.
```

### Comparative Analysis:

| Architectural Property | Option A: Hard SLA Floor (Recommended) | Option B: Multi-Objective Term |
|---|---|---|
| **Business/System Alignment** | **Exact match for enterprise SLAs.** Workflows specify hard operational reliability contracts (e.g. 99.5% execution success). Exceeding SLA provides minimal value; violating SLA is failure. | Blurs SLA guarantees. High reliability on one non-critical task can trade off and cause SLA violations on a critical task. |
| **Mathematical Cleanliness** | **Single-objective MCFLP.** Integer programming, LP relaxations, and Lagrangian dual bounds are exact, convex, and unambiguous. | **Bi-criterion optimization.** Objective scalar $\gamma$ is arbitrary ($/reliability fraction). Bound quality becomes dependent on tuning $\gamma$. |
| **Literature Precedent** | Follows **Murakkab (OSDI '26)** and **Cheng & Nguyen (2026)**, which treat SLOs/SLAs strictly as feasibility criteria. | Follows heuristic multi-objective papers (e.g. RouteLLM), which lack hardware provisioning bounds. |
| **Runtime Efficiency** | Candidate filtering pre-prunes search space $|C(t)| \ll |M|$, accelerating MILP, LP, and greedy solvers. | Expands candidate search space; requires Pareto frontier tracing or multi-start hyperparameter sweeps. |

### Recommendation for Advisor Sign-Off:
**We strongly recommend ratifying Option A.** Hard reliability filtering reflects enterprise cloud reality, maintains a rigorous single-objective facility location formulation, and avoids introducing unprincipled trade-off hyperparameters between dollars and reliability percentages.

---

## 5. Verification & Proof of Feasibility

The formulation is not theoretical; it has been completely implemented and stress-tested:
1. **Ground Truth Fixture (`adversarial_3t2p`):** Hand-calculated global optimum of 280 (3 GPUs) verified exactly by the reference MILP solver (`poc/tracks/exact_milp.py`).
2. **Algorithmic Solvability:**
   - Heuristic allocation (`A+subset`) solves in $< 15\text{ms}$ with $< 2\%$ gap on small/medium instances and $< 14\%$ at 64 tasks.
   - Linear programming relaxation with consolidation repair (`C+cons`) delivers $\le 5.5\%$ optimality gap at 64 tasks in $0.06\text{s}$.
   - Exact solver (`MILP`) executes in $< 0.22\text{s}$ at 32 tasks and $< 8\text{s}$ at 64 tasks.
3. **Invariants Guarantee:** Every allocation rigorously satisfies invariant gates $I_1$ (unit assignment), $I_2$ (throughput coverage), $I_3$ (budget cap), $I_4$ (candidate pool compliance), and $I_5$ (instance economy).

---

## 6. Ratification & Sign-Off Sheet

By signing below, the team members and advisor ratify the mathematical formulation in Section 2 (Option A: Hard SLA Floor) as the authoritative specification for the Senior Capstone Project:

- [ ] **Role 035 (Heuristics & Algorithmic Lead):** ___________________________ Date: _________
- [ ] **Role 075 (Mathematical Programming & Dual Theory):** _________________ Date: _________
- [ ] **Role 077 (Systems, Profiling & Prototype Integration):** ______________ Date: _________
- [ ] **Role 083 (Software Architecture & Formulation Gatekeeper):** _________ Date: _________
- [ ] **Role 089 (Empirical Methodology & Harness Lead):** ____________________ Date: _________
- [ ] **Project Advisor (Prof. Tossaphol):** _________________________________ Date: _________

---
*Document Version: 1.0 | Date: 3 September 2026 | Branch: `mickie`*
