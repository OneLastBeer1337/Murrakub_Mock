# Handoff — turning this work into the proposal

**Written 3 September 2026, at the end of a long working session.** The next session's job is
to make everything here the **core of the proposal** — not just T0, but Chapters 1 through 4,
the novelty argument, and the M1 presentation.

**If you want the ordered sequence rather than the reference material, read
[`PLAN.md`](PLAN.md) instead — eight steps, in order, ending at the presentation.** This
document is the detail behind those steps.

---

## 1. Where things stand in one paragraph

The proof-of-concept is complete: all four tests answered against the plan's *methods*, not
just its deliverables. 593 tests pass, reproducible from a clean clone. The optimizer works
and Track C is the result. Beyond the PoC, the closed loop was built and run end to end, and
it produced the project's strongest claim. Thirty-five findings are recorded, of which several
correct earlier ones — **the corrections are as important as the results, and three headline
numbers were retracted after a statistical audit.**

**The two branches were merged on 3 September** (step 1 of `PLAN.md`). `mickie`'s F20–F22 kept
their numbers; `main`'s F20–F27 became F23–F30. `BRANCHES.md` is retained as the record of
what was decided and why.

---

## 2. What the proposal needs, and what exists for each part

### Chapter 1 — problem and objectives

**Have.** The formalisation in `System_Architecture_v2.md` §1, and the plain-language version
in `docs/T0_briefing.md` Part 1. Objectives 1.2.1–1.2.4 are stated and three of the four now
have evidence.

**Missing.** The problem statement still reads as an optimizer project. It should lead with
the loop — see `docs/proposal_narrative.md` §1.

### Chapter 2 — literature

**Have.** `docs/research_papers/` tracks the papers. §1.8 identifies the problem as modular
capacitated facility location, which gives a citable literature beyond the two LLM-serving
papers. §9 is the reference map. The `mickie` branch adds P12 (DSPy).

**Settled 3 Sep. O12 — the novelty argument — is answered: the closed loop is
sufficient.** The advisor confirmed it (relayed by the team, not in writing here). §1.8
concedes the allocation problem is textbook, so novelty is **not** claimed there;
`docs/proposal_narrative.md` §4 is now the ratified position rather than a proposal, and
Chapter 2 can be written against it. What is still weak is the chapter itself — the position
is agreed, the literature review supporting it is not written.

### Chapter 3 — design and methodology

**Have, and this is the strongest chapter.** The formulation, the three tracks, the harness,
and 30 findings. `docs/D11_poc_report.md` is written for the advisor and is the natural
skeleton. `docs/proposal_narrative.md` §6 proposes the section order — deliberately putting
the optimizer *inside* the contribution rather than as the contribution.

**Missing.** Nothing structural. The work is to write it, and to make sure every number
quoted survives §5 below.

### Chapter 4 — evaluation plan

**Have.** A working harness with matched conditions and bias guards, two generators, and a
measured operating region (T3: 0.8×–1.25× the reference).

**Known defects, both flagged, neither fixed.** T4's decision criteria ask an A-vs-C question
the data has moved past. And **the generators model a homogeneous fleet**: both tie price to
GPU count, so the GPU budget does not change the optimal cost in 40 of 41 instances. O13 is no
longer the open part — F31 answers it from Murakkab's own numbers, and the answer is that price
and GPU count are separate axes. What is open is that **no generator reflects that yet**, so
T3's region and T1's arm comparison were both measured where (C3) barely binds. State this in
Chapter 4 rather than waiting for it to be found.

### The Semester 2 story

R7 (monitoring), R8 (execution-time reliability) and R9 (framework integration) have **no
implementation** and are marked Absent in §8's traceability table. They come from the
advisor's brief, so the proposal must address them as planned scope rather than omit them.
`prototype/` is the honest answer for R4/R5: the loop exists and runs.

---

## 3. The claims the proposal can lead with

Ordered by how well they survive scrutiny.

| claim | evidence | strength |
|---|---|---|
| A static allocator silently violates its reliability floors under drift; the adaptive loop does not | paired **+0.424 [0.405, 0.442]**, n=20 | **Strongest in the project.** Mean equals median, tight interval |
| Filtering eligibility on a point estimate costs ~40% permanently; an upper confidence bound recovers the optimum exactly | paired saving **128 [74, 182]**, fixed condition has zero variance | Very strong |
| Track C returns within ~3% of optimal at 128 tasks with bounded, predictable runtime | 0.106 ±0.020 s vs the solver's 12.3 ±10.3 s | Strong — **argue predictability, not speed** |
| Greedy is defeated by aggregate coupling; neither multi-start nor relocate recovers it | hand-verified, brute-forced, both run | Exact, not statistical |
| The Lagrangian bound is tighter than the LP bound | paired **12.57 pp [9.49, 15.64]** | Strong as a difference, **not as a ratio** |

**The argument chain that ties them together** is in `docs/proposal_narrative.md` §2: profiles
drift → the whole batch must be re-optimised → the exact solver cannot sustain that → a fast
track makes the loop affordable. **The algorithm work exists because the loop demands it.**

---

## 4. Decisions taken, so they are not re-litigated

| | decision | who |
|---|---|---|
| O1 | No per-invocation cost term. Provisioning cost only | Closed |
| O10 | Reliability is a **floor**, anchored to baseline-delivered reliability. Not an objective | Advisor, 3 Sep |
| O9 | Scoped re-optimisation is **vacuous** — a drifted profile touches 84–100% of workflows. J9 re-optimises globally | Closed by F18 |
| §6.4 | Budget anchor replaced with a reference allocation | Accepted |
| §4.5 | EMA for latency, **decayed counting estimator for reliability** | Changed by F19 |
| Track A | **Split, and T0 decision 3 is written to match.** *Plain* A stays in the repo but is **not reported in results**; **`A+subset` is a live contender** — never worse than plain greedy on 72 paired instances (F32), and it recovers the fixture's 280. Its gap does grow with scale | Your call, T0 |
| Track B | Keeps both roles — bound generator **and** allocator, with the 100× caveat attached | Your call, this session |
| O13 | **Price is not a multiple of GPU count.** Murakkab's basis is the working default until the deployment target is fixed | Advisor + F31, 3 Sep |
| STATIC | **Keep it as a live comparator, not a strawman.** If the adaptive method underperforms on a workload, report that static wins there | Your call, 3 Sep |

---

## 5. What must not be quoted

Three headline numbers were retracted after a statistical audit (F29, F30). **All three failed
the same way — a ratio of two means, which is not a typical ratio when either distribution has
a tail.** A **fourth** was found on 4 Sep, in `mickie`-origin documents the audit never covered.

| do not say | say instead |
|---|---|
| "~110× faster than the exact solver" | median speedup is **5×**; argue **bounded latency** — 0.106 ±0.020 s vs 12.3 ±10.3 s |
| "the bound is 3–6× tighter than the LP" | paired difference **12.6 pp [9.5, 15.6]**; median ratio ~2–2.5×. The advantage itself is solid — **53/53 across three generators wherever Track B has an incumbent** (F35). What is weak is Track B's *feasibility*, 7 of 17 on heterogeneous |
| "consolidation halves Track C's gap" | **median improvement is 0.00%** — it fixes a rare, severe failure |
| "subset consolidation is a **twenty-fold** improvement" (F20, slides) | **it was never worse — 0 of 72 paired instances**, better on 54. Paired difference **11.46 pp [6.68, 17.24]** structured, **9.30 pp [6.69, 12.42]** uniform; median per-instance ratio **1.53×** / **1.95×** (F32) |
| "A+subset holds the gap **<2% at all scales**" (chapter3) | **withdrawn.** The gap *grows* with scale — 2.35% at 8t to 14.30% at 64t structured. `chapter3_benchmark_results.md`'s own tables already said so; six of its eight cells are above 2% (F32) |

**The fourth was audited on 4 Sep (F32) and it behaved differently from the other three.**
They shrank by a roughly fixed factor. This one *moved by an order of magnitude* when the
instance set changed — 20.6× originally, 2.41× on a set with twice the seeds. A ratio of means
is not just inflated, it is unstable. What replaces it is stronger than a fold-change anyway:
**A+subset is never worse than plain greedy**, on any of 72 paired instances across two
generators with deliberately opposite structure.

**The lesson worth carrying:** F20 came from `mickie` in the step-1 merge and therefore
*predates nothing* — the F29/F30 audit ran before it existed here. Anything merged from a
branch is unaudited regardless of its finding number. Both of these sat in slide and chapter
material for a week.

Full list in `docs/poc_findings_summary.md` under *"numbers that were corrected"*. **The rule:
never divide two means.** Report the paired difference and its interval.

This matters beyond honesty — **`mickie`'s slides and benchmark tables were generated before
the audit** and may carry the same defect.

---

## 6. The open questions, and who owns them

| # | question | owner | blocks |
|---|---|---|---|
| ~~**O13**~~ | ~~Is `price(m)` independent of `gpu(m)`?~~ | **Fully closed 4 Sep.** Yes, on Murakkab's basis (F31); deployment target decided **local first**, so price is amortised hardware plus energy over an owned heterogeneous fleet | T3's region and T1's arm comparison were provisional pending a decorrelated generator. **It is being built** rather than parked for Semester 2 |
| ~~**O12**~~ | ~~Is the closed loop a sufficient novelty claim?~~ | **Answered 3 Sep** — yes, the loop is sufficient for M1. Novelty is **not** claimed in the optimisation | Unblocks Chapter 2 and the framing of everything |
| **D1** | Formulation ratification, due 8 Sep | Team | Nominally everything, though §1 has not needed to change |
| — | ~~Which duplicate implementation ships~~ | 035 / 075 | **Closed 3 Sep** — `mickie`'s ship; `main`'s stay registered as `B-C3-alt`, `A+rel` |
| — | ~~Finding renumbering~~ | Team | **Closed 3 Sep** — `main`'s F20–F27 → F23–F30 |
| — | Reconcile the `[PROPOSED]` compatibility score with Hatherley (2025) | 077 | Any drift-detection number |

**No advisor question is outstanding.** O12 is answered — the loop is sufficient. O13 turned
out not to need asking: the advisor's guidance was to take Murakkab as the base, and
Murakkab's published GPU/energy/cost triples answer it directly (F31). The pattern held —
O10, O12 and O13 were each answered in about a sentence and each materially changed what gets
written. What remains open is **team**-owned, not advisor-owned: the deployment target, D1,
and the Hatherley reconciliation.

---

## 7. Suggested order for the next session

1. ~~**Ask the advisor O12 and O13.**~~ **Done — both answered 3 Sep**, O12 by the advisor,
   O13 from Murakkab's own numbers (F31). Nothing is waiting on a reply.
2. ~~**Reconcile the branches**~~ **Done 3 Sep** — one branch, 15 conditions, 593 pass.
3. **Draft Chapter 3 from `D11_poc_report.md`**, restructured per `proposal_narrative.md` §6 so
   the loop leads and the optimizer serves it.
4. **Audit `mickie`'s slides and benchmark tables** against §5 above.
5. **Write the Semester 2 section** covering R7/R8/R9 as planned scope, with `prototype/` as
   evidence that R4/R5 are already de-risked.

---

## 8. Verifying the state yourself

```bash
python -m venv venv && venv/Scripts/activate
pip install -r requirements.txt
pytest poc/tests prototype/tests      # 643 pass, 4 skip
python -m poc.harness.runner          # the comparison table
```

Verified from a clean clone: fresh virtualenv, every figure reproduces byte-for-byte.

---

## 9. One thing worth carrying forward

Across this session, **every claim that broke was a bare ratio, and every claim that survived
had a mechanism behind it** — the fixture's arithmetic, the LP pricing by rate rather than by
whole instances, the loop holding reliability because it measures.

Three of the corrections came from someone asking a short sceptical question about a result
already presented as settled. That is worth saying in the presentation itself: an examiner who
sees the team volunteer what it got wrong will trust the rest considerably more.
