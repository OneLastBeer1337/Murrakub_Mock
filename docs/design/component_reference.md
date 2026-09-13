# Component reference — what each part does, and what it must become

**Purpose.** A per-component record of what was built, how it actually behaves (including
the behaviours that surprised us), whether it earns its place, and what it has to become in
the full system. Written to be the thing you consult in February when someone asks "why is
this like this?"

Every "behaves" line is measured, not intended. Every "becomes" line is a proposal, not a
decision.

Status key: **Keep** = works, carries forward · **Change** = works, needs rework for the full
system · **Cut** = measurement says drop it.

---

## 1. The formulation layer

### `formulation/types.py` — the data model · **Keep**

**Does.** Task, ProfileSpec, AllocationResult, Infeasible, AdmitCost, Observation.

**Behaves.** Failure is an `AllocationResult(feasible=False)` carrying an `Infeasible`, not
an exception — so the harness records failures as data instead of crashing. O1 is settled
here: no per-invocation cost term, so `ProfileSpec` has no `varcost` field.

**Fits.** Yes. Flat dataclasses, no inheritance, no abstraction. Every other module depends
on it and none of them fight it.

**Becomes.** Two additions the full system forces: `Observation` needs an executor identity
once J5 is real (attribution is per `(workflowInstance, taskId, profileId)` in §4.5, and the
current type has no run identity), and `ProfileSpec` likely needs an observation *timestamp*
so staleness can be distinguished from low count.

**Expected improvement.** Small but unblocking — without run identity, telemetry from
concurrent batches cannot be separated, and §4.5's "unattributable calls are logged and
discarded" cannot be implemented.

### `formulation/invariants.py` — I1–I5 · **Keep**

**Does.** Returns the list of violated invariants for a result; empty means valid.

**Behaves.** An under-provisioned allocation returns `['I1','I2','I5']` — it catches
*multiple* violations rather than short-circuiting, which is what makes a diagnosis
possible. A **declared failure returns `[]`**: infeasibility is a recorded outcome, not a
violation. That distinction matters and is easy to get wrong.

**Fits.** This is the highest-value module in the repo. ~700 measured allocations across
nine conditions, two generators and four budget levels produced **zero violations**. It is
the reason every other result can be trusted.

**Becomes.** Unchanged in shape, but it needs to run in *production*, not only in tests —
§3.3's J3 step 5 already says verification failure is an internal error that must fail
loudly. Add I6 (every routed profile still exists in the registry snapshot) once the
registry is live.

**Expected improvement.** It is already the cheapest insurance in the system. In the full
build it becomes the thing that stops a bad allocation reaching an executor.

---

## 2. The instance layer

### `instances/generator.py` — synthetic instances · **Change**

**Does.** Parameterised instances: task count, profile count, budget tightness, seed.

**Behaves.** The budget anchor is a *reference allocation* (each task to its most
GPU-efficient eligible profile), not §6.4's original "one instance per profile" — because
the original made 0–16 of 25 instances solvable and T3 could not sweep (F2). The
consequence, learned three times the hard way: **`budget_tightness = 1.0` is a cliff, not a
neutral default** (F15).

**Fits.** Yes, but the parameter name still runs backwards against its value (1.0 is the
*loosest* budget), and the sweep only explores *below* the reference.

**Becomes.** Extend the range above 1.0 so the cliff is interior rather than at the
boundary; rename `budget_tightness` to `budget_ratio`.

**Expected improvement.** T3 currently cannot see anything above the reference, which is
where real systems operate. Fixing this changes what T3 is able to conclude, not just how
it reads.

### `instances/structured_generator.py` — the second generator · **Keep**

**Does.** Deliberately different structure: sublinear throughput against linear price,
lognormal loads, GPU tiers, clustered floors.

**Behaves.** Inverts the value-per-GPU relationship, so large profiles are *bad* value —
the opposite incentive to the first generator. Loads are 7× more heavy-tailed. Most findings
survived the switch; F7's "6× tighter" did not, and became "3–6×" (F12) — which F30 then
retracted in turn, because every version of it was a ratio of means. The claim that survives
is the paired difference: **12.57 pp [9.49, 15.64]**, tighter on 30 of 30.

**Fits.** Yes, and it is the only answer to the strongest objection against every result —
that one author wrote the distributions, the tracks and the metrics.

**Becomes.** A *third* source: real profile measurements from Semester 2's execution engine.
Two synthetic generators bracket the space; they cannot replace measurement.

**Expected improvement.** Any finding that survives synthetic-uniform, synthetic-structured
*and* real profiles is publishable. None currently has the third leg.

### `instances/fixtures/adversarial_3t2p.py` — the ground truth · **Keep**

**Does.** 3 tasks, 2 profiles, hand-verified optimum 280, greedy 300.

**Behaves.** Validates two different build steps — the MILP must return 280, greedy must
return 300. **Greedy returning 280 is a regression, not an improvement**, and there is a
test saying so.

**Fits.** Yes. It is the only artefact in the repo whose correctness does not depend on
other code in the repo.

**Becomes.** Add a second fixture for the F17 failure (LP prices by rate, wastes a large
instance) so both known failure modes have a named, hand-checkable case.

**Expected improvement.** Cheap regression protection on the two mechanisms most likely to
be broken by an optimisation.

---

## 3. The decision core

### `core/provisioning.py` — ProvisioningState · **Keep**

**Does.** Tracks load and instances per profile; `cost_to_admit` prices a task against the
current state.

**Behaves.** `n[m]` is **derived** (`ceil(load/thr)`), never stored. Verified: admit `t1`
to `m2` → `{m2: 1}`, headroom 17; `cost_to_admit(t2, m2)` is then **zero** because headroom
covers it; release `t1` → `{}`, instance handed back. That symmetry is why relocate and
repair passes cannot strand instances.

**Fits.** It is the correction at the heart of v2 (capacity is consumed by instances, not by
task assignments), and it makes I2 and I5 true by construction.

**Becomes.** One real limitation: it cannot hold spare instances no load justifies. A
production system that pre-warms capacity, or that keeps an instance alive across
re-optimisations to avoid cold starts, needs a different container.

**Expected improvement.** Once execution is real, instance *churn* between re-optimisations
becomes a cost the current model cannot express — F23's loop re-allocates without ever
asking what tearing down an instance costs.

### `core/decision_rule.py` — select_profile · **Change**

**Does.** The one inner rule all tracks call; `cost_adjust` is the seam.

**Behaves.** Ties break on profile id — and **ties are the common case**, because
`extra_cost` is zero for every profile with headroom. Verified: with `m2` already open and
free, `t2` goes to `m2` over a fresh `m1`.

**Fits.** Yes as a mechanism. **No as a policy** — it ranks on `extra_cost` and never looks
at `extra_gpus`, which is the mechanism behind F3's infeasibility and, downstream, F23's
abandonment.

**Becomes.** Needs a budget-aware ranking. `track_a_m1.py` shows a feasibility lookahead
works (failures 29 → 2 on structured instances) with no tuning parameter.

**Expected improvement.** The single highest-leverage change in the optimizer. It is one
function, and it is upstream of every track's feasibility.

### `core/consolidation.py` — multi-move neighbourhood · **Keep**

**Does.** Relocates *every* task on one profile to another, together.

**Behaves.** Cuts Track C's worst case from 100.85% to 44.01% at no runtime cost. Audited
(F30): the **median** paired improvement is **0.00%** — it does nothing on a typical instance.
The mean improvement is real (5.31% [0.56, 10.07]) but tail-carried, so describe it as a
rare-severe-failure fix, not as halving the gap. **It does not fix the adversarial fixture** — that needs
a *subset* move, and there is a test asserting the fixture is unchanged so the limitation is
not mistaken for a bug.

**Fits.** Yes. It fixes a diagnosed failure rather than a guessed one.

**Becomes.** The **subset-move neighbourhood** is the missing piece: one mechanism closing
both F1 (consolidating is right) and F17 (de-consolidating is right). It is the best
remaining technical idea in the project.

**Expected improvement.** Would close the last known optimality gap mechanism and let
§3.1.7 finally specify the neighbourhood it currently only gestures at.

---

## 4. The tracks

### `tracks/exact_milp.py` — ground truth · **Keep**

**Behaves.** Matches independent brute force on every instance tested. Costs 32 ms at 8
tasks, **21 s at 128** on uniform instances but only 1.9 s on structured — *instance
structure drives solver cost more than instance size* (F13). The `n[m]` cap is deliberately
slack and there is a test proving it never binds, because a cap that bound would make CBC
report a suboptimal answer as optimal.

**Becomes.** Keep as ground truth and as the Murakkab baseline (they are the same thing
under §1's formulation). Add a time limit so large-instance runs degrade to "best found with
gap" rather than hanging.

### `tracks/track_c_lp.py` (+ `_consolidate`) — LP relaxation · **Keep — this is the result**

**Behaves.** **Bounded runtime where the exact solver's is not** — **0.106 ± 0.020 s** against
**12.3 ± 10.3 s** at 128 tasks, for **3.03 ± 1.62%** above optimum (F29, superseding F16's
headline; the median speedup is 5×, and the "~110× for under 5%" is retracted). Runtime
essentially flat, 0.054 s → 0.162 s across a 16× increase in tasks. Its gap does not degrade
with scale. Its known failure — pricing profiles by rate and wasting a large integer
instance — is diagnosed (F17) and fixed by consolidation.

**Fits.** It is the answer to Objective 1.2.2 and the reason the closed loop is affordable.

**Becomes.** The production allocator. Needs: a time limit, warm starting from the previous
allocation across re-optimisations, and the subset-move neighbourhood.

**Expected improvement.** Warm starting matters most — F23's loop re-solves from scratch
every round, and a re-optimisation after small drift should be much cheaper than a cold one.

### `tracks/track_b_lagr.py` (+ `_cold`) — Lagrangian · **Change — bound only**

**Behaves.** Best bound in the repo: 2.40% below optimum against Track C's 15.21%,
strictly tighter on 30 of 30, zero invalid. But **~100× slower than the exact solver it
exists to replace** (34.5 s at 32 tasks against 0.32 s). Its answers are excellent and
irrelevant.

**Fits.** As a **bound generator**, yes — which is what §5.2.3 always said it was for. As an
allocator, no, at any size measured.

**Becomes.** Profile the knapsack subproblem before treating the runtime as settled — it is
pure-Python DP with a full traceback table and could plausibly gain an order of magnitude.
Then decide. Also: the **(C3) relaxation arm is unbuilt**, so T1 is only half answered.

**Expected improvement.** If the bound can be produced cheaply it becomes an optimality
certificate for Track C's answers, which is worth far more than another allocator.

### `tracks/track_a_greedy.py` / `track_a_m1.py` — greedy · **Cut / Change**

**Behaves.** Plain greedy sits 8–15% above optimum and *degrades* with scale. A+M1's
feasibility lookahead cuts failures 29 → 2 on structured instances at no runtime cost.

**Fits.** T4's answer is that Track A does not earn its complexity against Track C. But
A+M1's *lookahead* is the mechanism `decision_rule` needs.

**Becomes.** Cut Track A as a track; **promote the lookahead into the shared decision rule**,
where it benefits every track.

### `tracks/static_baseline.py` — no optimisation · **Keep**

**Behaves.** 23–25% above optimum, fails 58% of solvable instances.

**Fits.** Essential. Without it, "Track C is 4.58% above optimum" has no scale to be read
against.

### `tracks/track_c_multi.py`, `track_b_cold.py` — variants · **Cut**

**Behaves.** `C2` prices one realisation attempt against two. `B-cold` proved the warm start
is inert (identical on every column) — that job is done and is now a test.

**Becomes.** Delete both as standing conditions; keep their findings. Nine conditions is
more than the story needs, and §4.7 asks for five.

---

## 5. The evaluation layer

### `harness/runner.py` + `metrics.py` · **Keep**

**Behaves.** Every condition gets the *identical instance object*, so a generator change
cannot silently compare tracks against different problems. `metrics.summarise` excludes
unsolvable instances and **counts** infeasible runs rather than averaging over them —
because a track that only solves the easy instances otherwise posts the best mean gap.
`scale_sweep` defaults to 1.25× budget because 1.0 is the cliff.

**Fits.** Yes, and it exists in this shape because the first scale scripts bypassed it and
reintroduced exactly the survivor bias it prevents (F16).

**Becomes.** Add seeds and confidence intervals — 3 seeds is not enough for any scale claim
to reach Chapter 3. Add a results store so runs are comparable across days.

**Expected improvement.** Turns "we measured this once" into "we can show it is stable",
which is the difference between a finding and a claim.

---

## 6. The loop layer (`prototype/`)

### `registry.py` — Executor Registry + Eligibility Resolver · **Keep**

**Behaves.** Exact type match only. An **unknown task type raises**; a known type whose
floors exclude everything **returns an empty pool**. Conflating those two is exactly the
silent quality loss §4.2 warns about, and nothing had ever tested it.

**Becomes.** Registry entries need a *source* (who registered this, when, from what
measurement) once profiles are real, and the resolver needs to read from the Profile Store
snapshot rather than a static catalogue.

### `profiling.py` — Profile Store + Drift Detector · **Change**

**Behaves.** Latency uses the EMA §4.5 specifies. **Reliability does not**, because an EMA
on a binary signal reports 0.70 after 99 successes and one failure (F19) — and that value
filters `C(t)`. Now a decayed counting estimator, with the ceiling chosen so realistic
floors remain achievable.

**Fits.** Yes, and it is the half of the project carrying the novelty.

**Becomes.** Three things: reconcile the **[PROPOSED]** compatibility score against Hatherley
(2025); make drift detection cheap (it currently runs the allocator, so it is not the
lightweight signal §4.5 implies); and add a **confidence bound** - specifically an UPPER bound, exclude only when
confident the profile is below floor. F25 corrects an earlier statement here that said
lower bound, which was backwards, and measures the fix recovering the full 25% penalty.

**Expected improvement.** The confidence bound is the highest-value single change in the
whole project — it directly addresses F23's abandonment, needs no new machinery, and sits in
the novel half.

### `reoptimisation.py` — J9 · **Change**

**Behaves.** Scoped re-optimisation is well-defined but **vacuous**: a drifted profile is
used by 84–100% of workflows, so the affected set is nearly everything. Scoped narrower than
reality costs a mean 22% (F18).

**Becomes.** Delete the scoped path; J9 re-optimises globally. Keep the comparison as
evidence for why.

### `ingestion.py`, `simulator.py`, `loop.py` · **Keep**

**Behaves.** The loop runs J1–J9 on the real Zookeeper batch without thrashing, converges,
and catches genuine degradation — but **abandons within-floor profiles on noise in 8 of 10
runs and can never re-test them** (F23). Ingestion refuses to invent the load and floors the
manifest does not carry.

**Becomes.** The simulator is a stand-in for J5/J6 and must be replaced by a real Execution
Engine and Measurement Interceptor. The loop itself is close to the real orchestrator shape.

**Expected improvement.** Once execution is real, the same loop produces the project's
actual evaluation: does profile-guided allocation beat static allocation on a real workload
over time? Nothing in the PoC answers that, and this is the harness that would.

---

## 7. What the whole thing needs next, in one place

| Change | Where | Why it matters |
|---|---|---|
| Confidence-bound eligibility — **built, measured, off by default** | `profiling.py` + `registry.resolve` | Fixes F23's abandonment and recovers a 25% cost penalty with no loss of drift sensitivity (F25). Needs 077's sign-off to become the default |
| Budget-aware ranking | `core/decision_rule.py` | Upstream of every track's feasibility (F3) |
| Subset-move neighbourhood | `core/consolidation.py` | Closes both F1 and F17 with one mechanism |
| Warm-started re-optimisation | `track_c_lp.py` | The loop re-solves from scratch every round |
| Real execution | replaces `simulator.py` | Everything about real workloads is currently unknown |
| Seeds and confidence intervals | `harness/` | Nothing here is statistically defensible yet |
| Cut C2, B-cold, Track A | `harness/runner.py` | Nine conditions where the story needs five |

The first row is the one to do first. It is small, it fixes the most damaging behaviour
found, and it is in the half of the project that makes it novel.
