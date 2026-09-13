# Proof-of-Concept Report

**Profile-Guided Multi-Workflow Resource Orchestration Platform**
Deliverable D11 · September 2026 · *draft for team review before M1*

---

## 1. What the PoC was for

Sections 1–4 of the architecture specified mechanisms whose necessity had not been verified.
Four questions were load-bearing, and the PoC existed to settle them before implementation
rather than after:

| | question |
|---|---|
| **T1** | Does the Lagrangian relaxation decompose, and along what axis? |
| **T2** | Does greedy construction survive aggregate coupling? |
| **T3** | Over what budget range does the problem have interesting structure? |
| **T4** | Does Track A earn its complexity relative to Track C? |

The plan states that a *negative* answer to any of these is a success. Three of the four came
back negative, and each removed work from Semester 2.

---

## 2. The four answers

### T1 — It decomposes three different ways, and only one of them is useful

All three relaxations the method asks for were built and measured. Bound gap is the distance
below the true optimum; smaller is tighter.

| relaxed | decomposes into | uniform | structured |
|---|---|---|---|
| **(C1) assignment** | one knapsack **per profile** | **3.02%** | **4.63%** |
| (C2) capacity | one choice **per task** | 12.68% | 26.85% |
| (C3) budget | **does not decompose** | — | — |
| LP relaxation | — | 12.16% | 24.61% |

**None of them decomposes per workflow**, which is what the earlier design claimed. Workflow
membership never appears in any subproblem, because no constraint is indexed by workflow.

The plan flags one outcome to watch: a Lagrangian bound matching the LP bound means the track
provides nothing the LP does not. **That fires for the (C2) arm** — 12.68% against the LP's
12.16% — and the reason is structural: (C2) is where the coupling and the integrality gap
live, so relaxing it buys an easy subproblem that no longer describes the problem. The
criterion firing for the *wrong* arm is what vindicates the right one.

The (C3) arm does not decompose — the assignment constraint still couples every profile
through the tasks, so each iteration costs a full exact solve. Its bound could not be
meaningfully compared here for the reason in §4.

### T2 — No. Greedy is defeated, and multi-start does not save it

On a hand-verified instance (3 tasks, 2 profiles), greedy returns 300 against an optimum of
280. Exhaustive enumeration confirms **all six task orderings return 300**. A single-move
relocate pass was then built and run, as the method specifies, and **also returns 300** — the
improving move requires relocating two tasks together, which a one-at-a-time neighbourhood
cannot see.

This is not a tuning problem. It is a structural property of pricing a task against the
current provisioning state when later assignments change that state.

### T3 — The operating region is 0.8× to 1.25× the reference allocation

Below 0.8 most instances are infeasible; above 1.25 every measurement freezes because the
budget stops constraining anything. Two distinct transitions sit inside that window:
feasibility (0.6–1.0) and *heuristic* feasibility (1.0–1.5), which happens later.

A counter-intuitive result worth carrying into the evaluation design: **gaps get worse as the
budget loosens** (Track C: 10.3% → 21.8%). A tight budget does the heuristic's job by leaving
nowhere to stray, so **a heuristic evaluated only at tight budgets looks better than it is.**

### T4 — No, and the answer is regime-dependent

| instance size | verdict |
|---|---|
| ≤ 8 tasks | **No heuristic is justified.** The exact solver is optimal in 32 ms |
| 16–128 tasks | **Track C, decisively.** Greedy sits 8–15% above optimum and degrades with scale |

At 128 tasks on the harder instance family (10 seeds, 95% CIs, every instance proven
optimal): the exact solver takes **12.3 ± 10.3 s**, Track C takes **0.106 ± 0.020 s** at
**3.03 ± 1.62%** above optimum.

**The defensible claim is predictability, not a speed ratio.** The median speedup is 5×, not
the ~110× obtained by dividing mean by mean — the solver's mean is carried by a heavy tail.
What matters for a system that re-optimises in a loop is that Track C's runtime is bounded
and near-constant while the exact solver's is highly variable and, without an imposed limit,
unbounded on its worst cases: a statistics run had to be killed after an hour on a single
instance. **An allocator that sometimes never returns cannot go in a control loop; one that
always returns in 0.1 s can.**

Track C's gap also improves with scale — 16.7% at 16 tasks to 3.0% at 128 — because rounding
error amortises over more tasks.

**Track A does not earn its complexity.** Track B produces the best bound in the project —
paired, it sits **12.6 percentage points [9.5, 15.6]** closer to the optimum than the LP
bound — but is ~100× slower than the exact solver as an allocator, so its role is as an
optimality certificate rather than as a candidate allocator.

---

## 3. The result that matters most, which the PoC was not designed to produce

The four questions are about the optimizer. The project's contribution is not the optimizer —
the allocation problem is textbook modular capacitated facility location, and the architecture
says so. The contribution is the **closed loop**: profiles measured rather than declared,
drift detected, allocation revised.

That loop was built and run end to end on the real Zookeeper batch. Both a static allocator
and the adaptive loop were started **correct** — declared reliability equal to true
reliability — and then reality drifted below the floor mid-run.

| | delivered reliability | cost |
|---|---|---|
| Static (Murakkab-like) | **0.542** | 400 |
| Adaptive (this project) | **0.938** | 1013 |

**The point is not the cost — it is that the static system never finds out.** Through every
post-drift round it reports the same plan, the same cost, and a satisfied 0.95 reliability
floor while delivering 0.54. Every number it can show you is unchanged. It has no measurement
path, so it cannot detect its own failure.

The cost comparison is **not** like-for-like and must not be presented as one: the static
system is not meeting its requirement at all, so its cheaper plan is cheaper *because it has
silently stopped working*.

This is the answer to the advisor's guidance that the goal is to keep reliability as good as
not using the system, and to maximise what distinguishes us. Those are the same claim, and
this measures it.

---

## 4. What we do not know

Stated at the same prominence as the results, because several of these bound how the results
may be read.

**The GPU budget is nearly inert in our instances.** Both instance generators set
`price = gpus × constant`, so minimising cost is nearly the same objective as minimising
GPUs. Consequently the budget does not change the optimal cost in **40 of 41** instances. It
constrains *feasibility*, not *choice*. **This is a property of our generators, not of the
problem, and O13 — is `price(m)` independent of `gpu(m)`? — is now answered against them
(F31).** Murakkab reports GPU count, energy and dollar cost as three separate numbers on one
matched workload, and they move by three different factors (÷2.82, ÷3.72, ÷4.33), so cost per
GPU falls to 0.65×. Price is *not* a multiple of GPU count: they trade A100s for H100s
precisely because price per GPU differs by hardware type. Our generators assume a homogeneous
fleet, which contradicts this project's own premise of routing across *heterogeneous*
profiles. So **T3's region and T1's arm comparison were both measured where (C3) barely binds
— the weakest possible test of them — and remain provisional.** The generator that would
settle it, with price decorrelated from GPU count, **is now built** —
`heterogeneous_generator.py`, corr(price, gpus) **+0.024** against +0.959 and +0.999. On it,
**(C3) changes the optimal cost in 24 of 25 instances** rather than 0 of 25, at a median 15.4%
cost penalty (**F33**). So the budget is not nearly inert in the problem; it was nearly inert
in our instances, and changing the price structure alone reverses the result. T3's operating
region is now measurable; **T1's arm comparison still needs re-running on it.**

**Nothing about real workloads.** Two synthetic generators, deliberately different in
structure, both written by the same author as the tracks and the metrics. Real profile
measurement is the only full answer and is Semester 2 work.

**Nothing about real execution.** The loop's execution stage is simulated: profiles carry
hidden true parameters and the executor samples from them. This tests the loop's *logic*, not
any executor's behaviour.

**Statistics were audited, and three claims did not survive.** Every headline was
re-measured as a paired per-instance difference with 95% intervals (F29, F30):

| claim | outcome |
|---|---|
| "~110× faster than exact" | **retracted** — mean over mean; median speedup is 5× |
| "bound 3–6× tighter than LP" | **ratio inflated** — median 2.0–2.5×; the paired difference of 12.6 pp [9.5, 15.6] is what holds |
| "consolidation halves the gap" | **median improvement is 0.00%** — real but tail-carried; it fixes a rare severe failure |
| the adaptive loop holds reliability | **holds strongly** — +0.424 [0.405, 0.442], n=20 |
| optimistic eligibility removes the overpayment | **holds strongly** — saving 128 [74, 182], zero variance |

The lesson generalises: **never divide two means.** All three failures were the same
construction. Treat any bare ratio in this project as unverified unless an interval is
attached to it.

**No claim of the form "our approach reduces cost by X%" is supported.**

---

## 5. What the PoC changed about the design

Nine design defects were found by measurement rather than review. The most consequential:

| | defect | consequence |
|---|---|---|
| §6.4 | The budget anchor made 0–16 of 25 instances solvable | T3 could not sweep at all. Anchor replaced |
| §4.5 | "EMA update per observation" applied to reliability | A binary signal under an EMA reports **0.70 after 99 successes and one failure** — and that value filters `C(t)`. One failed call would have collapsed the pools |
| §3.3 | J9 re-optimises "affected workflows only" | Vacuous: a drifted profile is used by **84–100%** of workflows. Scoping removed |
| §1.6 | Eligibility filtered on a point estimate | Costs up to **25% permanently** even with no drift. Filtering on an upper confidence bound recovers the optimum exactly with no loss of drift sensitivity |
| §1.3 | `R_min(t)` was never defined | Under the advisor's guidance it must be anchored to baseline-delivered reliability, or the optimiser legally trades reliability for cost |

Each was cheaper to find now than in February.

---

## 6. What we recommend for Semester 2

1. **Adopt confidence-bound eligibility.** One comparison changed; removes a 25% cost penalty.
2. **Cut Track A; keep its feasibility lookahead** in the shared decision rule.
3. **Track B is a bound generator**, not an allocator.
4. **Do not build scoped re-optimisation.** Re-optimise globally.
5. **Settle O13** before any budget-related result is quoted.
6. **Build the Execution Engine and Measurement Interceptor.** Everything about real
   behaviour is currently unknown, and the loop is the project's contribution.

---

## 7. Reproducing everything here

```bash
python -m venv venv && venv/Scripts/activate
pip install -r requirements.txt
pytest poc/tests prototype/tests      # 573 tests
python -m poc.harness.runner          # the comparison table
```

Verified from a clean clone: fresh virtualenv, install from `requirements.txt`, 573 tests
pass, and every figure above reproduces byte-for-byte.

Full chronological evidence is in `poc_findings.md` (24 findings, including superseded ones);
`poc_findings_summary.md` states current beliefs with confidence levels and a list of numbers
that were corrected and must not be quoted.
