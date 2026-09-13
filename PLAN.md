# The plan — one line, from here to 30 September

**No options, no branches, no parallel tracks.** Eight steps in order. Finish one, start the
next. At the end you have a proposal and a presentation you can defend.

The end state: **a written proposal and an M1 presentation, both backed by evidence in this
repo.** Everything below exists to get there.

```
  1  merge          2  ask advisor      3  fix numbers     4  T0 session
  |                    |                   |                  |
  +--------------------+-------------------+------------------+
                       |
  5  write Ch3      6  write Ch1,2,4    7  build slides    8  rehearse
  |                    |                   |                  |
  +--------------------+-------------------+------------------+
                       |
                  30 Sep — M1
```

---

## 1 · Merge the two branches — by 4 Sep — **DONE 3 Sep**

**Why first:** there are currently two versions of the truth. Nothing after this is reliable
until there is one.

**Do:** follow `BRANCHES.md`. Three decisions, all small:
- renumber `main`'s findings so they don't collide with `mickie`'s F20
- keep `mickie`'s implementations where they duplicate `main`'s
- resolve the five conflicting files by hand

**Done when:** one branch, tests pass, `python -m poc.harness.runner` runs.

**Done.** One branch at `e87208e`, 15 conditions in the registry, 593 pass / 4 skip. `mickie`'s
implementations ship; `main`'s equivalents stay registered as `B-C3-alt` and `A+rel` so the
alternative is reproducible rather than merely asserted.

---

## 2 · Send the advisor two questions — same day, 30 minutes — **DONE 3 Sep**

**Why now:** both shape what you write, and writing before the answers means rewriting.

> 1. Our allocation problem is textbook capacitated facility location. Our novelty claim is
>    the closed loop — measured profiles, drift detection, re-optimisation — which neither
>    Murakkab nor Cheng & Nguyen does. Is that sufficient? *(O12)*
> 2. Is `price(m)` independent of `gpu(m)`, or is price essentially GPU-hours? It determines
>    whether the GPU budget constraint does anything. *(O13)*

**Both answered 3 Sep, and neither needed a second exchange.**

- **O12 — yes, the closed loop is sufficient** as the M1 contribution (advisor). Novelty is
  claimed in the loop, **not** in the optimisation: §1.8's concession stands and Chapter 2
  presents the formulation as adopted. `docs/proposal_narrative.md` §4 is now ratified rather
  than proposed.
- **O13 — answered without asking.** The advisor's guidance was to take Murakkab as the base;
  Murakkab's own GPU/energy/cost triples move by three different factors on one workload, so
  `price(m)` is **not** a multiple of `gpu(m)` (**F31**). Our generators assume it is, so every
  budget result was measured where (C3) barely binds. **The decorrelated generator is now
  built** (`heterogeneous_generator.py`, F33) rather than parked: on it (C3) changes the
  optimum in 24 of 25 instances instead of 0 of 25.

**Done.** Nothing is waiting on a reply.

---

## 3 · Fix every number — by 6 Sep

**Why:** three headline claims were retracted after a statistical audit, and the slides on
`mickie` were written before it.

**Do:** take the "numbers that were corrected" table in `docs/poc_findings_summary.md` and
grep the merged repo for each. Fix every occurrence. **The rule: never divide two means.**

**Done when:** no bare `N×` claim survives anywhere without a confidence interval beside it.

---

## 4 · T0 session — 8 September

**Why:** it is the one hard deadline before the presentation, and it is a deliverable (D1).

**Do:** run `docs/T0_briefing.md`. It is built as confirm-or-object with a default for every
item, so it should take about an hour. Fill in the template at the end.

**Done when:** the template is filled in and five people have signed off their part.

---

## 5 · Write Chapter 3 — 8 to 15 Sep

**Why:** it is your strongest chapter and everything else is written around it.

**Do:** start from `docs/D11_poc_report.md`. Restructure it in the order given in
`docs/proposal_narrative.md` §6 — **the loop leads, the optimizer serves it.** Do not lead
with the algorithm comparison.

**Done when:** Chapter 3 is drafted and every number in it appears in
`poc_findings_summary.md` with an interval.

---

## 6 · Write Chapters 1, 2 and 4 — 15 to 22 Sep

**Why:** they are shorter and they frame Chapter 3.

- **Ch 1** — problem and objectives. Lead with the loop, not the optimizer.
- **Ch 2** — literature. The weakest chapter. Use the advisor's answer to O12 and the
  positioning table in `docs/proposal_narrative.md` §4.
- **Ch 4** — evaluation plan, plus Semester 2 scope covering R7, R8 and R9, which have no
  implementation and must be presented as planned work rather than omitted.

**Done when:** all four chapters drafted.

---

## 7 · Build the slides from the chapters — 22 to 27 Sep

**Why this order:** slides built from written chapters stay consistent with them. Slides
written first drift.

**Do:** start from `mickie`'s existing slides, cut anything not backed by a chapter, and
recheck every figure against step 3.

**Done when:** every slide traces to a chapter section.

---

## 8 · Rehearse — 27 to 30 Sep

**Do:** each person works `docs/study_guide.md` — the six core choices, roughly two to three
hours, not the full nine steps. Then rehearse the hard questions in its step 9.

**One rule for the room:** volunteer the limitations before you are asked. An examiner who
has to extract a weakness trusts you less than one you hand it to. You have unusually good
material for this — three headline numbers were found wrong by your own audit.

**Done when:** every member can answer, unprompted: what `x` and `n` are, which constraint
couples workflows, and one thing the team got wrong and fixed.

---

## If something slips

Cut from the end, never the front. Steps 1–4 are load-bearing; 7 and 8 compress. **Never skip
step 3** — a wrong number in front of an examiner costs more than a missing slide.

## When you find something interesting mid-plan

**Follow it.** Every correction that mattered in this project came from someone noticing
something looked wrong and pulling on it — the EMA that would have collapsed eligibility, the
budget anchor that made T3 unsweepable, three headline numbers that were ratios of means.
Refusing to look would have cost far more than the detour did.

The failure mode is not exploring. It is **exploring and not coming back.** So when something
surfaces, spend one minute classifying it before you dig:

| kind | what to do | example from this project |
|---|---|---|
| **It breaks something already written** | **Chase it now.** It is not a detour, it is step 3 arriving early | The 110× speedup was a ratio of means. Everything quoting it was wrong |
| **It blocks the step you are on** | Fix it as part of that step | The solver had no time limit, so the statistics run could not finish |
| **It is a new capability** | **Write one line in `PLAN.md` under Semester 2 and stop.** Do not build it | Subset-move neighbourhood, confidence-bound eligibility, real execution |

The first two are the plan, not interruptions to it. Only the third is a detour, and it is the
one that consumed the most time here.

**Then say out loud which step you are returning to.** That single sentence is what was
missing: several excursions in this session were correct and never explicitly ended, so the
next thing started from the excursion rather than from the plan.

### Discoveries parked for Semester 2

Add to this list rather than building. Nothing here blocks the presentation.

- Confidence-bound eligibility (built, measured, off by default — needs 077's sign-off)
- ~~Subset-move neighbourhood~~ — **already built on `mickie`, shipped in the step-1 merge**
  as `A+subset` / `A+M1+subset`. It recovers the fixture's optimum of 280. Chapter 3 can
  report it rather than promise it
- Generator with **price decorrelated from GPU count** — F31 shows Murakkab prices a
  heterogeneous fleet and our generators do not, so every budget result is measured where
  (C3) barely binds. Identified, not closed
- Real execution to replace `prototype/simulator.py`
- Profiling Track B's knapsack subproblem before its runtime finding is treated as settled
- More seeds and intervals on the findings that still lack them

---

## What you do not need to do

The technical work is finished. The confidence-bound fix, real execution and more statistics
are all Semester 2. **Nothing in the eight steps above requires writing new code.**
