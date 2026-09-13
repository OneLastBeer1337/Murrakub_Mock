# PoC Findings — standing summary

**Read this instead of `poc_findings.md` unless you need the history.** As of the 3 September
2026 branch merge, that log runs to **thirty-one** findings, several of which correct earlier ones
— F14 was corrected by F15 and again by F16; F6 was refined by F17; F7's headline number was
amended by F12 and again by F30. The history is deliberate and worth keeping, but it is
archaeology. This page states what we believe *now*.

**Numbering note.** F1–F19 predate the branch split. **F20–F22 are `mickie`'s** (subset move,
the (C3) arm, the T3 sweep above reference) and keep their original numbers, because the M1
slides and `PROGRESS.md` already cite them. **F23–F31 are `main`'s**, renumbered from F20–F27
in the merge. Any document written before 3 September that cites F20–F27 means `main`'s
originals — add 3.

Every row carries what would overturn it, because most of these have been overturned at
least once already.

**For what these findings are *for*, read [`proposal_narrative.md`](../proposal/proposal_narrative.md)
first.** This page says what is true; that one says which links in the project's argument
each finding supports, and which findings are negative results that should not be featured.

---

## The four questions

### T1 — Does the Lagrangian relaxation decompose, and along what axis?

**Answered in full.** Both branches built the (C3) arm independently and reached opposite
conclusions about whether it decomposes. **Both are correct; they relax different things.**

| relaxed | decomposes into | uniform bound gap | structured bound gap |
|---|---|---|---|
| **(C1) assignment** | one knapsack **per profile** | **3.02%** | **4.63%** |
| (C2) capacity | one choice **per task** | 12.68% | 26.85% |
| (C3) budget, `n` integral (`track_b_budget.py`) | **does not decompose** — each iteration is a full exact solve | 0.00% \* | 0.00% \* |
| (C3) budget, `n` continuous (`track_b_c3.py`, ships as `B-C3`) | one choice **per task**, 1-D concave dual solved by bisection in < 1 ms | = LP bound † | = LP bound † |
| LP relaxation | — | 12.16% | 24.61% |

\* only because the budget does not bind on our instances — see F26. Not a real result.

† **checked paired, per instance**, 6 tasks / 3 profiles at tightness 1.0: 24 uniform and 25
structured instances, `B-C3` and the LP agree to within **2e-5** with differences of *both*
signs — solver and bisection tolerance, not a systematic gap. The 15.22% vs 15.21% in the
pooled harness table is aggregation, not a difference in the bounds themselves.

**The reconciliation.** Relaxing (C3) alone leaves (C1) coupling every profile through the
tasks, so the subproblem is still capacitated facility location — `main`'s F28 is right that
it does not decompose. `mickie`'s F21 additionally relaxes the **integrality of `n[m]`**,
which is what buys the per-task decomposition: each task independently picks the profile
minimising the effective rate `(price + μ·gpu) / thr`. That is also why its dual bound
**matches** the LP rather than beating it — with the integrality property restored in the
subproblem, Lagrangian duality guarantees no more than the LP, and the paired check above
confirms it. It is the LP bound reached by a cheaper route, not a tighter one.

**None of the arms is per workflow** — no constraint is indexed by workflow, so the earlier
design's claim could never have held. §5.3's "cut it" criterion fires for the (C2) arm and
for the continuous (C3) arm, which vindicates the (C1) choice rather than undermining it.

The sub-question O3 is answered cleanly: **the Lagrangian bound from the (C1) arm is
consistently tighter than the LP bound** — strictly tighter on 30 of 30 instances, 0 invalid
bounds, and tight on the hand-verified fixture. §5.3's "if the bounds match, cut Track B"
outcome **did not fire** for the arm that ships.

**Conclusion:** Relaxing (C1) provides the superior dual bound; relaxing (C3) provides an ultra-fast alternative whose bound matches the LP bound.

### T2 — Does greedy construction survive aggregate coupling?

**No, but multi-move subset consolidation recovers it.** On the hand-verified fixture, plain greedy returns 300 against an optimum of 280, and neither multi-start nor single-move relocate recovers it.

**The resolution:** `core/consolidation.py` now implements `consolidate_subsets` (condition `A+subset` in `tracks/track_a_subset.py`). By evaluating joint k-subset moves, it moves {t1, t2} to m2 together while keeping t3 on m1, **recovering the exact global optimum of 280** (findings F20).


### T3 — Over what budget range does the problem have interesting structure?

**Answered, but the experimental design is defective.** Solvability rises from 1/25 to 25/25
as tightness goes 0.5 → 1.0, so a binding region exists and is wide.

**Answered (F27).** The sweep now spans both sides of the reference. The operating region is
**0.8× to 1.25×**: below 0.8 most instances are infeasible, above 1.25 every number freezes
because the budget stops constraining anything. Two distinct transitions sit inside it —
feasibility (0.6–1.0) and *heuristic* feasibility (1.0–1.5), which happens later.

Counter-intuitively the gaps get **worse** as the budget loosens (Track C 10.3% → 21.8%): a
tight budget does the heuristic's job for it by leaving nowhere to stray. **A heuristic
evaluated only at tight budgets looks better than it is.**

**Still provisional, but the reason has changed (F31).** Per F26 the budget affects
feasibility but almost never the optimal cost, because both generators tie price to GPU count.
**O13 is now answered on Murakkab's basis: price is *not* a multiple of GPU count** — their own
results move GPUs 2.82×, energy 3.72× and cost 4.33× on one workload, and their gains come from
trading A100s for H100s. So "the budget is nearly inert" is a property of *our generators*, not
of the problem, and this region was measured on instances where (C3) barely binds.

### T4 — Is Track A worth its complexity relative to Track C?

**No, and the honest answer is regime-dependent.**

| regime | verdict |
|---|---|
| ≤ 8 tasks | **No heuristic is justified at all.** The MILP is optimal in 32 ms |
| 16–128 tasks | **Track C, decisively.** Greedy sits 8–15% off and degrades with scale |

At 128 tasks on the instance family where the MILP is actually expensive, **Track C's runtime
is bounded and the exact solver's is not**: **0.106 ± 0.020 s** against **12.3 ± 10.3 s**, at
**3.03 ± 1.62%** above optimum (F29, 10 seeds). The **median** speedup is 5× on uniform and 2×
on structured — *not* the ~110× that dividing one mean by another once suggested, which is
retracted and sits in the do-not-quote table below.

What answers Objective 1.2.2 is the predictability, not the ratio. Look at the intervals: the
solver's mean is carried by a heavy tail that, before a time limit was imposed, ran unbounded.
**An allocator that usually takes 12 s and occasionally never returns cannot go in a control
loop at all; one that always takes 0.1 s can.**

---

## What we believe, and what would overturn it

| # | Belief | Confidence | Evidence | Overturned by |
|---|---|---|---|---|
| 1 | Greedy is defeated by aggregate coupling; multi-start and single-move relocate cannot recover | **High** | Hand-verified fixture, re-derived by exhaustive enumeration in tests | Nothing short of an arithmetic error in the fixture |
| 2 | Track C returns within ~3% of optimal at 128 tasks with **bounded, predictable** runtime (0.106 ±0.020 s) where the exact solver is 12.3 ±10.3 s and unbounded without a limit | **Medium-high** | F29, 10 seeds, 95% CIs, all 80 instances proven optimal | A generator where the MILP is uniformly fast — on structured it already is |
| 3 | The Lagrangian bound is tighter than the LP bound **wherever Track B has a feasible incumbent** — on every generator | **High** (F34 downgraded this in error; **F35 restores it**) | **53/53** — uniform +5.22 pp [4.36, 6.05] on 24/24, structured +13.46 pp [10.32, 16.71] on 22/22, heterogeneous +5.84 pp [3.86, 7.64] on 7/7 | An instance class where they converge. Note the *bound* is not the weak point — **Track B's feasibility is**, 7 of 17 heterogeneous |
| 4 | Track B is not viable as an allocator — ~100× slower than the exact method it replaces | **Medium** | F13, timings at 8/16/24/32 tasks | **A profiled implementation.** The knapsack DP is pure Python and could plausibly gain an order of magnitude |
| 5 | The LP prices profiles by *rate*, so it cannot see that a large profile's integer instance will sit mostly empty | **High** | F17, fully diagnosed on a specific instance; the fix fixes a rare severe failure in Track C — median paired improvement 0.00%, mean 5.31% [0.56, 10.07] (F30) | Nothing — the mechanism is arithmetic |
| 6 | The shared decision rule ignores `extra_gpus`, which causes infeasibility | **High** (mechanism) / **Low** (rate) | §5.2.1 by inspection; but the 42% rate is an anchor artefact | The mechanism is in the spec. The *rate* should never be quoted |
| 7 | A feasibility lookahead (A+M1) substantially cuts greedy's failures at no runtime cost | **Medium-high** | 27→17 uniform, 29→2 structured | Scale — untested past 32 tasks |
| 8 | Optimisation beats no-optimisation by a wide margin | **High** | STATIC 23–25% off, fails 58% of instances | Nothing plausible |
| 9 | The exact MILP becomes expensive around 128 tasks — but only on some instance families | **Medium** | 21 s uniform vs 1.9 s structured at 128 | More families; a better solver or formulation |
| 10 | Instance *structure* drives solver cost more than instance *size* | **Medium** | Structured was harder at 8 tasks, 11× cheaper at 128 | Only two generators exist |
| 11 | Scoped re-optimisation is well-defined but **vacuous**: a drifted profile is used by 84-100% of workflows, so the affected set is almost the whole batch. Scoped narrower than reality it costs a mean 22%. Either way, do not build it | **Medium-high** | F18, corrected; 60 instances, workflow counts 2-12 | Global re-optimisation becoming expensive at scale |
| 13 | The closed loop runs without thrashing and catches real degradation, but abandons within-floor profiles on noise and can never re-test them - measurement drives eligibility, eligibility drives routing, routing drives measurement | **Medium-high** | F23, 10 seeded end-to-end runs on the real batch | An exploration or confidence-bound policy, which does not exist |
| 14 | A static allocator silently violates its reliability floors under drift - 0.542 delivered against a 0.95 floor, reporting no change - while the adaptive loop holds 0.938. This is the project's differentiator | **Medium-high** | F24, 8 seeds, both systems starting correct, identical drift schedule | Real execution behaving unlike the simulation; a subtler drift |
| 15 | Filtering eligibility on a point estimate costs up to 25% permanently even with no drift. Filtering on an UPPER confidence bound recovers the optimum exactly and loses no drift sensitivity | **Medium-high** | F25, 8 seeds, 80 rounds, three floor levels | A workload where thin-evidence optimism is dangerous |
| 16 | Murakkab prices a **heterogeneous** fleet: cost per GPU moves 0.65–0.76× between configurations of one workload, so price is not a multiple of GPU count. Our generators assume the opposite, so every budget result is measured where (C3) barely binds | **Medium-high** | F31, arithmetic on Murakkab's reported GPU/energy/cost triples | The figures being misrecorded in our reference database — check the PDF |
| 12 | Section 4.5's EMA is wrong for reliability: a binary signal under an EMA reports 0.70 after 99 successes and one failure, and that value filters C(t) | **High** | F19, arithmetic, reproduced in tests | Nothing - the mechanism is arithmetic |
| 17 | Subset consolidation (`A+subset`) is **never worse** than plain greedy — 0 of 72 paired instances across both generators, better on 54 — for a paired gain of 11.46 pp [6.68, 17.24] structured | **High** | F32, 72 paired instances, scales 8–64, seeds 0–9, bootstrap CIs | An instance class where the k≤2 neighbourhood misleads; none seen |
| 19 | The GPU budget (C3) **binds wherever price per GPU is not constant** — it changes the optimal cost in 24 of 25 heterogeneous instances (median penalty 15.4%, max 52%) against 0–4 of 25 where price is a fixed multiple of GPU count | **High** | F33, one input varied in isolation — same tasks, same profiles, only B moves | A pricing regime where cost per GPU really is flat; hourly rental is the plausible one |
| 20 | Our first two generators model a **homogeneous rented fleet**, which contradicts the project's own premise of routing across heterogeneous profiles. Every result measured only on them inherits that | **High** | F31, F33; corr(price, gpus) +0.959 and +0.999 against +0.024 | Nothing — it is a property of the code that draws them |
| 18 | `A+subset`'s optimality gap **grows with scale** — 2.35% at 8 tasks to 14.30% at 64 on structured. It dismantles aggregate coupling; it does not hold a small gap at size | **Medium-high** | F32, and `chapter3_benchmark_results.md`'s own tables, which the file's summary contradicted | A larger k, or a scale run past 64 tasks showing it flatten |

---

## Numbers that were corrected — do not quote the originals

| Stale claim | Where it came from | Current status |
|---|---|---|
| "Lagrangian bound is **6×** tighter" | F7, uniform generator only | **3–6×**, generator-dependent (F12) |
| "Both heuristics fail on **42%** of instances" | F3 | Mechanism real; the *rate* is an artefact of the budget anchor |
| "The greedy tracks **collapse at scale**" | F14 | **Wrong.** A cliff at exactly the anchor budget; 25% more budget restores 5/5 (F15) |
| "Track C's gap **improves monotonically** with size" | F14 | Also a cliff artefact. It sits in a 2–5% band with no clean trend (F16) |
| "Track C is the **weakest** of the three tracks" | F11, and an amendment I made to §5.9 | **Withdrawn.** True at 8 tasks, false at scale, where it is the only heuristic that works |
| "**Track B dominates**" | F10 | True on quality at 8 tasks; false in practice — it is ~100× slower than exact (F13) |
| "Rounding the routing is **nearly free**" | F6 | Mechanically true, but the integral routing can still be badly wrong (F17) |
| "Track B's bound is **3–6× tighter**" | F7, F12 | **Ratio of means.** Median per-instance ratio is 2.0–2.5×. The paired difference — 12.6 pp [9.5, 15.6] — is what holds (F30) |
| "Consolidation **halves** Track C's gap" | F17 | **Median improvement is 0.00%.** Real but tail-carried; it fixes a rare severe failure (F30) |
| "Track C is **~110x faster** than exact for <5%" | F16, and D11's first draft | **Mean over mean, and outlier-driven.** The MEDIAN speedup is 5x on uniform and 2x on structured. What survives is predictability: 0.106 +-0.020 s against 12.3 +-10.3 s (F29) |
| "The GPU budget is **nearly inert**" | F26 | **Now demonstrated, not just suspected.** True of the two per-GPU-price generators; **false in general.** Built a third generator with price decorrelated from GPU count and changed nothing else: (C3) goes from 0–4 of 25 instances binding to **24 of 25**, median cost penalty 15.4% (F33). Quote F26 as a fact about those instances only |
| "Subset consolidation is a **twenty-fold** improvement" | F20 (`mickie`), the M1 slides, PROGRESS | **Ratio of means — and an unstable one.** Audited in F32: the median per-instance ratio is **1.53×** structured, **1.95×** uniform, and the ratio of means itself moved from 20.6× to 2.41× when the instance set changed. Say instead: **A+subset was never worse on any of 72 paired instances** (better on 54, identical on 18), paired difference **11.46 pp [6.68, 17.24]** structured |
| "A+subset holds the gap **<2% at all scales**" | `chapter3_benchmark_results.md` §1 | **Withdrawn — the file's own tables refute it.** Six of its eight cells exceed 2% (structured 32t 13.03%, 64t 13.92%). The gap **grows with scale**: 2.35% at 8t to 14.30% at 64t (F32) |
| "Track B's bound advantage **does not survive** on heterogeneous instances" | **F34 — my own error, corrected by F35 the same day** | **A confound.** F34 pooled instances where Track B found a primal with those where it did not. Split, the advantage holds **53/53** across all three generators (+5.84 pp [3.86, 7.64] on heterogeneous alone). What fails is Track B's *feasibility* — 7 of 17 — not its bound |
| "`B-C3`'s bound **matches the LP to 2e-5**" | The step-1 merge's T1 note | **Partly an artefact of (C3) being inert.** Where the budget binds they agree on 14 of 17, max relative difference 8.5e-02. The structural explanation still stands; the pristine agreement does not (F34) |
| "Filter C(t) on a **lower** confidence bound" | F23, and component_reference | **Backwards.** It must be the UPPER bound — a lower bound is low when evidence is thin and excludes faster (F25) |
| "Scoped re-optimisation is **worse ~50% of the time**" | F18, first version | Measured an arbitrary affected workflow rather than the drifted profile's. Correctly scoped it is **identical to global**, because the affected set is 84-100% of workflows |

---

## What none of this establishes

- **Nothing about real workloads.** Two synthetic generators, both written by the same author
  as the tracks and the metrics. Real data is out of PoC scope by §5.1.
- **Nothing statistical.** Scale runs are 3 seeds; tightness sweeps are 25. No confidence
  intervals, no significance testing.
- **Nothing about Track B's real ceiling.** Its runtime finding may be implementation, not
  method.
- **Nothing about execution.** J5/J6 are simulated: profiles have hidden true parameters and
  the executor samples from them. That tests the loop's LOGIC, not any real executor's
  behaviour. R7/R8/R9 have no implementation.
- **The domain data is used only for structure.** The real Zookeeper batch supplies workflow
  shape and task types; load and floors are invented, because the manifest carries neither.
- **Profiling and drift exist only as a prototype.** `prototype/` implements the Profile
  Store, Drift Detector and J9 outside PoC scope, fed synthetic observations. The
  compatibility score there is **[PROPOSED]** and not the source paper's, so no number from
  it should be quoted until 077 reconciles it.
- **Nothing about a heterogeneous fleet.** Both generators tie price to GPU count with
  corr ≈ 0.95–1.0, i.e. they assume every GPU costs the same. Murakkab does not, and neither
  will we (F31). A generator with price decorrelated from GPU count is not built, so every
  result involving the budget is measured in the easy regime.
- **No claim of the form "our approach reduces cost by X%"** is supported.

---

## Outstanding, in priority order

| # | Item | Owner | Status / Due |
|---|---|---|---|
| 1 | **T0 / D1 — ratify the formulation.** Everything above rests on §1 being right | All | **8 Sep** |
| 2 | Extend T3's sweep *above* the reference (`runner.py`) | 089 | **Done** (F22) |
| 3 | Ask the advisor what "improve reliability" means — floor, or objective? One reading changes §1 | Advisor | before T0 |
| 4 | Build the (C3) relaxation arm so T1 is actually answered (`track_b_c3.py`) | 075 | **Done** (F21) |
| 5 | Profile Track B's knapsack subproblem before its runtime finding is treated as settled | 075 | — |
| 6 | Subset-move neighbourhood — closing both T2's fixture and F17 (`track_a_subset.py`) | 035 | **Done** (F20) |
| 7 | Reconcile `track_a_m1.py` against Cheng & Nguyen's actual M1 (Paper P3, C_FEASFIRST) | 035 | **Done** |
| 8 | More seeds before anything reaches Chapter 3 | 089 | before D11 |
| 9 | **Drop scoped re-optimisation from Semester 2.** F18 answers O9: it works but is not worth building | 077 | - |
| 10 | Reconcile the [PROPOSED] compatibility score against Hatherley (2025) | 077 | - |
| 11 | **Amend section 4.5**: EMA for latency, decayed counting estimator for reliability (F19) | 077 | - |
| 12 | ~~Paired per-instance check that `B-C3`'s bound equals the LP bound~~ | 075 | **Done** — agrees to 2e-5 on both generators, differences of both signs |
| 13 | **Decide the deployment target — local, GCP, or both.** O13's exact answer follows from it; Murakkab's basis is the working default until then | Team | before Ch4 |
| 14 | Check F31's Murakkab figures against the paper's own tables before any of them reach a chapter | 083 | before Ch2 |
| 15 | Generator with price decorrelated from GPU count — **Semester 2**, but every budget result stays provisional until it exists | 083 | S2 |

---

## How to reproduce anything here

```bash
pytest poc/tests prototype/tests   # 643 pass, 4 skip (third generator added)
python -m poc.harness.runner       # the tightness sweep, 15 conditions
```

```python
from poc.harness.runner import sweep, scale_sweep      # scale_sweep for the size axis
from poc.harness import metrics
from poc.instances import structured_generator          # pass generator=... to either
```

Always read `infeas` beside `mean gap%`. A condition that only solves the easy instances
posts the best-looking gap in the table — `metrics.summarise` counts failures rather than
averaging over them precisely to make that visible, and the first scale scripts got this
wrong by bypassing it.
