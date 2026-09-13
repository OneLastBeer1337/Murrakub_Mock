# Proposal narrative — what this project's contribution actually is

**Purpose.** The evidence produced so far is lopsided: ~3,900 lines and nineteen findings on
the optimizer, ~800 lines and two on profiling. Read cold, the repo looks like a comparative
study of heuristics for capacitated facility location. The project is not that. This page
fixes the emphasis, and it is an argument about *framing*, not a request for more work — every
claim below is already evidenced.

Written as input to Chapter 3 and to D11. Nothing here is team-agreed.

---

## 1. The contribution, in one paragraph

Multi-workflow resource orchestration in which the profiles that drive allocation are
**measured and kept current**, and the system **re-allocates when they drift**. The optimizer
is the engine that makes that loop affordable, not the contribution itself.

---

## 2. Why the optimizer work is necessary — the argument chain

This is the part that has been missing, and it is what turns nineteen scattered findings into
one story. Each link is evidenced, and each link forces the next.

**Step 1 — Profiles drift, so allocation cannot be decided once.**
Principle P6: profiles are measured, not declared. Measured values move. R4 and R5.

**Step 2 — When drift is detected, the whole batch must be re-optimised.**
This is not an assumption; it is finding **F18**. §3.3 proposed re-optimising "affected
workflows only", and that turns out to be vacuous: drift is detected on a *profile*, and
under (C2) a shared profile is used by **84–100% of workflows** even at twelve. Scoping
correctly does the same work as a global run; scoping narrower costs a mean 22%. So every
drift signal implies a **global** re-optimisation.

**Step 3 — Global re-optimisation with an exact solver does not scale.**
Finding **F13**: the MILP reaches **21 s** at 128 tasks on the harder instance family, with a
worst case of 55 s. A system that re-solves on every drift signal cannot pay that.

**Step 4 — A fast track makes the loop viable.**
Finding **F29**, which audited F16 and replaced its headline: at 128 tasks Track C returns an
allocation in **0.106 ± 0.020 s** against the exact solver's **12.3 ± 10.3 s**, at
**3.03 ± 1.62%** above optimum, with runtime essentially flat across a 16× increase in tasks.
The **median** speedup is 5×; the "~110×" once quoted here was a ratio of means and is
retracted.

**Therefore:** the algorithmic work exists *because the loop demands it*. What carries the
chain is not a speed ratio but a **bounded** one — read the intervals, not the means: Track C's
runtime is near-constant, while the solver's is carried by a heavy tail that ran unbounded
until a time limit was imposed. **An allocator that usually takes 12 s and occasionally never
returns cannot go in a control loop at all; one that always takes 0.1 s can.** That is the
reason continuous re-optimisation is possible, and it is a *stronger* claim than the ratio it
replaces, because it does not depend on which average you pick. Without step 4, steps 1–3
describe a system that cannot run.

That chain is the spine of Chapter 3.

---

## 3. Where each finding lands in that story

Findings stop being a list and become evidence for specific links.

| Link in the argument | Findings |
|---|---|
| The loop must be global, not scoped | **F18** |
| The exact solver cannot sustain it | **F13**, **F9** (what no optimisation costs) |
| A fast track can | **F16**, **F14** |
| The fast track is trustworthy | **F7** (valid bounds), **F17** (worst case diagnosed and fixed), invariants I1–I5 on every result |
| The problem is genuinely hard | **F1** (greedy defeated), **F3** (mechanism), **F5** (15% integrality gap) |
| The evaluation is honest | **F2**, **F11**, **F12**, **F15** — four cases where measurement corrected our own claims |
| The loop works end to end | `prototype/tests/test_profiling.py::test_the_full_profiling_loop_changes_an_allocation` |

Findings that do **not** support the contribution, and should be reported as negative results
rather than featured: **F10** (Track B dominates — true only at 8 tasks), **F4** (A vs C — 
superseded), **F8** (M1 lookahead — a Track A improvement, and Track A is being cut).

---

## 4. The novelty position (O12)

O12 — novelty versus Cheng & Nguyen — is **answered (3 Sep): the closed loop is sufficient
as the M1 contribution.** The framing above is what made it answerable, and it is now the
ratified position rather than a proposal. Note what it does not license: novelty is claimed
in the **loop**, not in the optimisation, which §1.8 concedes is textbook and which this
document presents as adopted.

| | allocation | profiles | re-optimisation |
|---|---|---|---|
| Murakkab (Chaudhry et al., 2026) | exact MILP | static inputs | none |
| Cheng & Nguyen (2026) | greedy activation-cost ranking | static inputs | none |
| **This project** | fast enough to re-run continuously | **measured, EMA/counting, drift-detected** | **global, on every drift signal** |

**The honest novelty claim is the closed loop, not the algorithm.** §1.8 says plainly that the
allocation problem is textbook modular capacitated facility location — which is a strength for
rigour and a weakness for novelty. Claiming algorithmic novelty invites exactly the comparison
the project loses. Claiming the loop is defensible: neither source paper closes it, and F18
shows closing it properly forces the global re-optimisation that makes the speed requirement
real.

**What this costs us:** it means the project must actually deliver the loop in Semester 2. The
narrative cannot lead with profiling and then ship only an optimizer.

---

## 5. Demonstrated vs claimed — the line to hold

**Demonstrated, with code and tests:**
- The allocation problem, formalised, with an exact reference validated against brute force
- Three tracks with valid bounds and no invariant violation across ~700 measured allocations
- Track C at **0.106 ± 0.020 s** against the exact solver's **12.3 ± 10.3 s** at 128 tasks, for
  **3.03 ± 1.62%** extra cost — bounded runtime, median speedup 5× (**not** the retracted ~110×)
- Profiles updating from observations; drift changing pools; re-optimisation moving a task

**Claimed but not demonstrated:**
- Anything on real workloads. Two synthetic generators, both written by one author.
- Anything statistical. Scale runs are 3 seeds.
- Drift on *real* profile movement. Observations are injected, not measured from execution.
- The compatibility score is **[PROPOSED]** and unreconciled with Hatherley (2025).
- R7 monitoring, R8 execution-time reliability, R9 framework integration: absent.

**No claim of the form "our approach reduces cost by X%" is supported**, and the proposal must
not make one.

---

## 6. Suggested Chapter 3 structure

Ordered so the optimizer appears as machinery inside the contribution rather than as the
contribution.

1. **The problem** — §1's formulation, and §1.8's identification as capacitated facility
   location. State plainly that the allocation problem is known; the novelty is elsewhere.
2. **Why allocation cannot be decided once** — measured profiles drift (R4/R5).
3. **Why re-optimisation must be global** — F18. This is the project's own negative result and
   it is more interesting than a positive one.
4. **The cost that imposes** — F13: exact solving is 21 s at 128 tasks.
5. **The tracks** — as the response to that cost. T1/T2/T4 sit here, including the negative
   results: Track A does not earn its complexity, Track B is a bound generator not an
   allocator.
6. **Result** — F29: **bounded** runtime, 0.106 ± 0.020 s against 12.3 ± 10.3 s for 3.03 ± 1.62%
   extra, which is what makes the loop affordable. Quote the intervals, never the ratio.
7. **The loop, end to end** — the prototype demonstration.
8. **Threats to validity** — §5 above, in full. The four self-corrections are evidence of
   method, not embarrassment; say so explicitly.

---

## 7. What is missing before this can be defended

| | Owner |
|---|---|
| T0 — ratify §1. Everything above assumes it | All, **8 Sep** |
| ~~The advisor's answer on O10~~ — **answered 3 Sep: a floor**, not an objective. §1.9 stands | — |
| ~~The advisor's answer on O12~~ — **answered 3 Sep: yes, the loop is sufficient** | — |
| Reconcile the compatibility score with Hatherley (2025) | 077 |
| More seeds on the scale results before they are quoted | 089 |
| A team member who can defend each finding — currently none have reviewed them | All |

The last row is the largest risk in the table. Work that cannot be explained by the person
presenting it is a liability at a defence, regardless of whether it is correct.
