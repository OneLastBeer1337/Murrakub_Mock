# Section 5 — Proof-of-Concept and Validation Plan

*Slots into `System_Architecture_and_Detailed_Design.md` as §5. Existing §5 (Development
Approach) becomes §6, §6 (Traceability) becomes §7, §7 (Reference Map) becomes §8.*

**Target completion: 30 September 2026**, coinciding with milestone M1 (Proposal
Presentation).

---

## 5.0 Why this section exists

Sections 1–4 specify mechanisms whose necessity has not been verified. Three specific
assumptions are load-bearing and untested:

1. That the Lagrangian relaxation decomposes usefully for this problem
2. That a greedy constructive heuristic can price assignments whose marginal cost depends on
   provisioning decisions not yet made
3. That the three tracks produce meaningfully different solutions at all

If any of these fail, the corresponding component in §3.1 is wrong, and building it first would
mean discovering that after 035 or 075 has spent a semester on it.

The proof-of-concept exists to settle these before implementation, using instances small enough
to solve exactly. It is deliberately **not** a scaled-down version of the system — it contains
no registry, no profiling, no execution, and no domain data.

---

## 5.1 Scope boundary

This boundary is the schedule. Anything moved across it puts 30 September at risk.

### In scope

| Item | Form |
|---|---|
| Formal two-level program | Written formulation, §5.3 T0 |
| Exact reference solver | MILP via PuLP + CBC, extending the existing baseline scripts |
| Track C prototype | LP relaxation + rounding |
| Track B prototype | Lagrangian relaxation, subgradient updates |
| Track A prototype | Plain greedy only — no multi-start, no relocate, no consolidate |
| Synthetic instance generator | Parameterised by task count, model count, budget tightness |
| Measurement harness | Cost, runtime, bound, feasibility, per condition |
| Results and written findings | Feeds §3.1, §4.2, and the proposal's Ch.3 |

### Explicitly out of scope

| Item | Why deferred |
|---|---|
| Executor Registry | Synthetic candidates suffice to answer T1–T4 |
| Profiling Subsystem (J6–J8) | Profiles are static inputs in the PoC |
| Execution Engine (J5) | Nothing is executed; allocations are evaluated, not run |
| Drift detection and re-optimisation (J9) | Requires profiling; answers no PoC question |
| Zookeeper / LogHub domain data | Synthetic instances give controlled budget tightness, which real data does not |
| Monitoring, fallback, framework integration | R7/R8/R9 — Semester 2 scope |
| Track A's multi-start, relocate, consolidate | T4 decides whether these are worth building at all |

### The scope rule

> If a task does not help answer T1, T2, T3, or T4, it does not belong in September.

---

## 5.2 Deliverables

| ID | Deliverable | Owner | Due |
|---|---|---|---|
| D1 | Formal two-level program, reviewed by the team | All (drafted by 075) | 8 Sep |
| D2 | Synthetic instance generator | 083 | 8 Sep |
| D3 | MILP reference solver at two levels | 089 | 15 Sep |
| D4 | Track C prototype (LP + rounding) | 075 | 15 Sep |
| D5 | T1 findings — does Lagrangian decompose? | 075 | 15 Sep |
| D6 | T2 findings — can greedy be fooled? | 035 | 15 Sep |
| D7 | Track B prototype (Lagrangian) | 075 | 22 Sep |
| D8 | Track A prototype (plain greedy) | 035 | 22 Sep |
| D9 | T3 findings — budget-binding region | 089 | 22 Sep |
| D10 | T4 findings — is Track A worth its cost? | 035 + 089 | 26 Sep |
| D11 | Consolidated PoC report | 077 | 29 Sep |
| D12 | Architecture doc updated with outcomes | 083 | 29 Sep |

---

## 5.3 Test specifications

### T0 — Formal two-level program

**Purpose.** Everything else is a question *about* this. Without it, no algorithm can be
justified and no bound can be verified.

**Draft to attack [PROPOSED].** This is a starting point for the team to correct, not a
settled formulation. It is written to be wrong in visible places.

*Sets and indices*

```text
T          tasks, across all workflows in the batch
M          model profiles — a (model, hardware tier, config) that can be instantiated
C(t) ⊆ M   candidates eligible for task t, after reliability/latency filtering
```

*Parameters*

```text
load(t)          throughput demand of task t          (tokens or requests per unit time)
thr(m)           throughput capacity of one instance of profile m
gpu(m)           GPUs consumed by one instance of profile m
price(m)         cost of one instance of profile m for the horizon
B                total GPU budget
R_min(t), L_max(t)   reliability and latency floors — applied when building C(t)
```

*Decision variables*

```text
x[t][c] ∈ {0,1}     task t routed to candidate c ∈ C(t)      (level 1 — selection)
n[m]    ∈ Z⁺        instances of profile m provisioned        (level 2 — provisioning)
```

*Objective*

```text
minimize   Σ_m  n[m] · price(m)
```

*Constraints*

```text
(1)  Σ_{c ∈ C(t)}  x[t][c]  =  1                              ∀ t ∈ T
(2)  Σ_t Σ_{c : profile(c)=m}  x[t][c] · load(t)  ≤  n[m] · thr(m)     ∀ m ∈ M
(3)  Σ_m  n[m] · gpu(m)  ≤  B
(4)  x[t][c]  ≤  y[m]  where profile(c)=m, y[m] = 1 iff n[m] ≥ 1        ∀ t, c
```

*Where the coupling lives — and why this shapes every track*

- **(2) couples tasks to provisioning**, and couples tasks *to each other* whenever they route
  to the same profile — including tasks from different workflows. This is the multi-workflow
  interaction.
- **(3) couples all profiles** through one shared budget.
- **The integrality gap lives in (2)**: `n[m]` must cover a ceiling of aggregate load over
  throughput. The LP will return fractional instance counts; rounding up costs real GPUs.

*Method.* 075 drafts from the above; the whole team reviews in one session; disagreements are
recorded rather than resolved silently.

*Exit criteria.* Every member can state, unprompted, what `x` and `n` mean and which
constraint couples workflows.

*Risk.* If the team cannot agree on this in one week, the PoC does not happen on time. This is
the single highest-risk item in the plan.

---

### T1 — Does the Lagrangian relaxation decompose usefully?

**Owner:** 075. **Due:** 15 Sep.

**Question.** §3.1.7 asserts that relaxing the coupling constraint yields independent
*per-workflow* subproblems. Against the T0 formulation, that looks wrong.

**Hypothesis to test.** Relaxing (3) leaves (2) intact. Constraint (2) is indexed by profile,
not by workflow. So the subproblems that fall out are likely **per model profile**, not per
workflow — and the current architecture assumes the wrong decomposition.

**Method.**

1. Write the Lagrangian of (3) with multiplier λ. Inspect the remaining constraint set.
2. Identify the natural decomposition: by workflow, by profile, or neither.
3. Repeat relaxing (2) instead, and both together. Record what each yields.
4. Numerically, on instances small enough for exact solution (≤10 tasks, ≤4 profiles):
   compute the true optimum, the LP bound, and the best Lagrangian bound.

**Decision criteria.**

| Outcome | Consequence |
|---|---|
| Decomposes per profile | §3.1.7's Subproblem Decomposer is rewritten; Track B stands |
| Decomposes per workflow | Architecture is correct as written |
| No useful decomposition under any single relaxation | Track B needs both constraints relaxed, or reconsidering |
| **Lagrangian bound = LP bound consistently** | **Track B provides nothing Track C does not; it should be cut or rejustified** |

The last row is the one to watch. If it fires, 075's entire component is in question, and it is
far better to know on 15 September than in February.

---

### T2 — Can the greedy ranker be fooled by aggregate coupling?

**Owner:** 035. **Due:** 15 Sep.

**Question.** Cheng & Nguyen's ranking prices an assignment using activation cost *given the
current provisioning state*. Under constraint (2), a task's true marginal cost depends on
assignments not yet made: routing task 1 to profile X may cost a whole new instance, or
nothing, depending on whether task 50 was going to activate X anyway.

**Method.** Construct by hand a small adversarial instance — approximately 4 tasks, 2 profiles,
budget tight enough to bind — where the greedy ordering leads to a provisioning pattern that a
better global solution avoids. Solve exactly for reference. Then run:

1. Plain greedy
2. Greedy + one relocate pass

**Decision criteria.**

| Outcome | Consequence |
|---|---|
| Greedy finds the optimum | The aggregate-coupling concern is overstated; proceed |
| Greedy fails, relocate recovers | **Relocate is load-bearing, not an enhancement.** Document it as required in §3.1.7 |
| Neither recovers | The ranker needs redesign before any Track A implementation |

**Note.** This test costs about a day and is mostly paper work. It is the cheapest test in the
plan and potentially the most consequential for 035's semester.

---

### T3 — Where does the budget actually bind?

**Owner:** 089. **Due:** 22 Sep. **Depends on:** D2, D3.

**Question.** If the GPU budget is loose, every method finds a near-identical solution and the
comparison shows nothing. The evaluation only has signal where the budget binds.

**Method.**

1. Fix a synthetic batch from the generator (D2).
2. Sweep `B` from generous to infeasible, roughly 15–20 points.
3. At each point, solve exactly (D3). Record: optimal cost, active profiles, instance counts,
   and whether the solution structure changed from the previous point.
4. Identify the range over which the solution structure changes materially.

**Decision criteria.**

| Outcome | Consequence |
|---|---|
| A wide binding region exists | That range becomes the evaluation's operating regime; record it |
| The region is narrow | The comparison has little room; the experimental design needs rethinking |
| No region — solutions barely change | **The problem may be too easy at this scale.** A finding about the whole project's premise, not just the evaluation |

**Note.** T3 is the only test whose failure mode threatens the project's framing rather than a
single component. It should not be deprioritised because it looks like plumbing.

---

### T4 — Is Track A worth its cost?

**Owner:** 035 with 089. **Due:** 26 Sep. **Depends on:** T3, D4, D8.

**Question.** Track A has six sub-modules in §3.1.7 and produces no bound. Track C is a solver
call plus rounding. Does the extra machinery pay?

**Method.**

1. Take instances from T3's binding region.
2. Run: plain greedy (D8), Track C (D4), exact MILP (D3).
3. Record cost gap to optimum and runtime for each.

**Decision criteria.**

| Outcome | Consequence |
|---|---|
| Greedy within a few percent of LP-rounding | The full AGH machinery likely does not pay; simplify or cut Track A |
| Large gap that relocate/multi-start would plausibly close | Track A justified; build it out in Semester 2 |
| Greedy frequently infeasible | The construction needs the M1 analogue (O2) before it is viable |

---

## 5.4 Schedule

Four weeks, running alongside proposal preparation. Proposal work is shown because it is the
main competing demand.

| Week | Dates | PoC work | Competing |
|---|---|---|---|
| **1** | 2–8 Sep | T0 draft (075) → team review session → agreed formulation. Instance generator (083) | Proposal draft |
| **2** | 9–15 Sep | MILP reference (089). Track C (075). T1 analysis (075). T2 adversarial test (035) | Proposal draft, slides |
| **3** | 16–22 Sep | Track B (075). Plain greedy (035). T3 budget sweep (089) | Slides, rehearsal |
| **4** | 23–30 Sep | T4 comparison (035 + 089). PoC report (077). Architecture update (083) | **M1 presentation, 30 Sep** |

**Hard checkpoints.**

| Date | Checkpoint | If missed |
|---|---|---|
| 8 Sep | T0 agreed | Everything slips. Escalate to advisor immediately — do not absorb quietly |
| 15 Sep | T1 and T2 answered | Drop Track B or Track A prototype; keep Track C and the MILP |
| 22 Sep | T3 answered | Report T1/T2 findings only; defer T4 to October |
| 26 Sep | T4 answered | Report as incomplete rather than rushing the comparison |

---

## 5.5 Ownership

| Member | PoC responsibility | Maps to |
|---|---|---|
| 035 | Greedy construction, T2, T4 | Track A ownership |
| 075 | Formulation draft, Lagrangian, Track C, T1 | Track B ownership |
| 077 | PoC report, results write-up | Phase C ownership deferred to Sem 2 |
| 083 | Instance generator, repo, architecture update | Infrastructure |
| 089 | MILP reference, T3, T4 support | Evaluation ownership |

**Note on 077.** Phase C is entirely out of PoC scope, so 077 has no implementation work in
September. Owning the report is real work and keeps them engaged with the findings, but this
imbalance should be visible rather than glossed — it is worth checking with 077 directly
whether they would rather take a share of the prototype work instead.

---

## 5.6 Success criteria

The PoC succeeds if, on 30 September, the team can answer all four:

1. **Does the Lagrangian relaxation decompose, and along what axis?**
2. **Does greedy construction survive aggregate coupling, with or without relocate?**
3. **Over what budget range does this problem have interesting structure?**
4. **Does Track A earn its complexity relative to Track C?**

A *negative* answer to any of these is a success. "Track B provides no bound advantage" is a
finding that saves a semester. The PoC fails only if the questions remain open.

---

## 5.7 What the PoC does not establish

Recorded so the results are not over-read:

- **Nothing about real workloads.** All instances are synthetic. Real profile distributions may
  behave differently.
- **Nothing about profile drift.** Profiles are static inputs; the entire Phase C premise is
  untested here.
- **Nothing about execution.** No allocation is run against a real executor.
- **Nothing about scale.** Instances are sized for exact solvability, deliberately small.
- **Nothing about the domain.** Zookeeper/LogHub is not involved.

The PoC settles *design* questions, not *performance* claims. Any statement in the proposal of
the form "our approach reduces cost by X%" remains unsupported after this work.

---

## 5.8 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| T0 not agreed by 8 Sep | Medium | **Critical** — blocks everything | Timebox to one session; record disagreements rather than resolving them; escalate to advisor |
| Proposal work crowds out PoC | **High** | High | Hard checkpoints in §5.4; drop tests from the end, never the formulation |
| Scope creep into registry/profiling/domain | Medium | High | The scope rule in §5.1 |
| T1 invalidates Track B late | Low | High | T1 is scheduled early precisely for this |
| Prototypes disagree due to bugs, not method | Medium | Medium | Property test on every output: all floors satisfied, capacity respected |
| One member blocked, work stalls | Medium | Medium | Cross-review at each checkpoint; no member is a single point of failure for T0 |

**On the second row.** This is the most likely failure mode. Four weeks containing both a
proposal presentation and a research prototype is genuinely tight for a five-person team that
has not yet built either. If something must give, give up T4 first, then T3 — but never T0,
because the proposal's Ch.3 depends on the formulation existing.

---

## 5.9 Effect on the rest of the document

| Section | Status pending PoC |
|---|---|
| §3.1.7 Track A | Provisional — T2 confirmed the coupling failure (F1); T4 now leans toward simplifying rather than expanding it (F10) |
| §3.1.7 Track B | Provisional — built relaxing (C1). Its bound beats the LP's by **12.6 pp [9.5, 15.6]** paired (F30); the "6× tighter" this row used to claim was a **ratio of means**, and the median per-instance ratio is 2.0–2.5×. Either way T1's "cut the track" outcome did not fire. The (C3) arm is **no longer unbuilt** — `B-C3` shipped in the step-1 merge, and its bound *matches* the LP's to 2e-5, because relaxing the integrality of `n[m]` is both what buys the per-task decomposition and what forfeits any advantage over the LP |
| §3.1.7 Track C | **Regime-dependent, and the earlier note here was wrong.** At 8 tasks it is the weakest track (F11). At 64+ tasks it is the only heuristic that returns an answer at all, at 1-3% of optimum with **bounded** runtime where the solver's is not — 0.106 ± 0.020 s against 12.3 ± 10.3 s at 128 tasks (F29). The "~100x speedup" this row used to claim has the same defect as the retracted 110x: it divided one mean by another. The median is 5x. An earlier revision of this row called it "weakest" on 8-task data alone; that was a confident conclusion from the only regime measured |
| §3.5 Shared Resource Ledger | **Requires rewrite.** Capacity is consumed by instances, not per-task assignments |
| §4.1 Data Model | Requires `n[m]` instance variables; current model has none |
| §4.2.1 Shared Decision Rule | Capacity filter does not apply as written; per-task consumption is not the constraint |
| §6.2 Open items O1–O3 | Resolved by adopting Murakkab's capacity model; O4–O6 resolved by T1–T4 |

Sections marked **requires rewrite** are known to be wrong under the two-level formulation and
are retained only until the PoC produces the corrected version.

---

*End of Section 5.*
