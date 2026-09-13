# PoC Findings — running log

> **Start with [`poc_findings_summary.md`](poc_findings_summary.md).** This file is the
> chronological record, and several findings here are corrected by later ones — F14 by F15
> and F16, F6 by F17, F7's headline by F12. The history is kept deliberately, but the
> summary states what is currently believed. Do not quote a number from this log without
> checking the summary's "corrected" table first.

**Status: preliminary.** Recorded 2 September 2026, in Week 1 of the §5.4 schedule. These
are early readings from the harness, not the deliverables. D5/D6 are due 15 Sep, D9 22 Sep,
D10 26 Sep, and the consolidated report D11 on 29 Sep.

Nothing here has been reviewed by the team. Several items contradict assumptions in
`System_Architecture_v2.md`, which is the point of running the tests early — but a
contradiction found by one person on one afternoon is a prompt for discussion, not a
settled result.

## Reproducing these numbers

```bash
python -m poc.harness.runner        # or, in a REPL:
```

```python
from poc.harness.runner import sweep
from poc.harness import metrics
records = sweep(n_tasks=8, n_profiles=4,
                tightness_values=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0], seeds=range(25))
print(metrics.format_table(metrics.summarise(records)))
print(metrics.solvability(records))
```

Everything below is 8 tasks, 4 profiles, seeds 0–24, six tightness levels — 150 instances,
64 of which the exact solver could solve.

### The full table

```
cond    inst  feas  infeas  =opt  mean gap%  max gap%  bound gap%   time s
--------------------------------------------------------------------------
MILP      64    64       0    64       0.00      0.00        0.00    0.032
STATIC    64    27      37     7      23.06     46.55           -    0.000
A         64    37      27    23      10.28     40.43           -    0.000
A+M1      64    47      17    29       9.39     40.43           -    0.000
B         64    59       5    55       0.93     16.96        2.40    0.954
C         64    37      27    16      14.58     70.49       15.21    0.029
C2        64    43      21    20      13.16     70.49       15.46    0.025
```

`infeas` counts instances the exact solver could solve but the condition could not. Read it
alongside `mean gap%`, which is over feasible runs only — a condition that solves just the
easy instances posts a flattering gap.

---

## F1 — T2 is confirmed on the fixture: greedy is defeated by aggregate coupling

`instances/fixtures/adversarial_3t2p.py`, hand-verified and now re-verified by exhaustive
enumeration in the test suite:

| Condition | Cost | Routing |
|---|---|---|
| Exact MILP | **280** | `t1→m2, t2→m2, t3→m1` |
| Track C | **280** | same |
| Track A (plain greedy) | **300** | everything on `m1` |

Greedy's myopia costs 20 (7.1%). The fixture also records, by enumeration, that neither
multi-start (all six orderings return 300) nor single-move relocate recovers it — the
improving move is `t1` and `t2` *together*.

**Consequence, per §5.3's T2 table:** the outcome is "greedy fails, relocate does not
recover", which is off the bottom of that table. It points at a multi-move neighbourhood
or a consolidation step, not at relocate. This is evidence for §3.1.7 needing a
sub-module it does not currently specify.

**Caveat.** One hand-built instance, constructed to defeat greedy. F4 is what happens on
instances not built for that purpose, and it does not agree.

---

## F2 — §6.4's budget anchor did not work, and T3 could not sweep against it [FIXED, SIGNED OFF]

§6.4 anchors the budget to "a naive one-instance-per-profile solution", `Σ_m gpu(m)`.
Implemented literally, then measured — solvable = the exact MILP found any allocation, out
of 25 seeds:

| tightness | 0.3 | 0.4 | 0.5 | 0.6 | 0.75 | 1.0 |
|---|---|---|---|---|---|---|
| solvable | 0 | 0 | 3 | 6 | 12 | 16 |

The anchor does not depend on the tasks at all, so 8 tasks routinely need more instances
than one-per-profile. The budget landed below feasibility nearly everywhere, and **T3's
primary axis had no room to move even at its loosest setting.**

The anchor is now a concrete, always-achievable reference allocation — every task to its
most GPU-efficient eligible profile, instance counts derived from routed load. Being a real
allocation rather than a bound, a budget equal to it always admits a solution:

| tightness | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 |
|---|---|---|---|---|---|---|---|
| solvable | 0 | 1 | 3 | 6 | 13 | 16 | 25 |

`budget_tightness` keeps its §6.4 meaning — a fraction of an anchor — so the sweep reads
the same way. Only the anchor changed.

**Signed off 2 September 2026**, and §6.4 in `System_Architecture_v2.md` has been amended
to match, with the measurements that forced it. A separate wrinkle left alone: the parameter name runs backwards against its
value, since 1.0 is the *loosest* budget. That inversion is §6.4's.

---

## F3 — Both heuristics are infeasible on a third to a half of solvable instances

This is the largest problem currently visible, and it is not the one the plan expected to
be largest.

| tightness | solvable | A infeasible | C infeasible |
|---|---|---|---|
| 0.5 | 1 | 1 | 1 |
| 0.6 | 3 | 2 | 3 |
| 0.7 | 6 | 3 | 2 |
| 0.8 | 13 | 7 | 6 |
| 0.9 | 16 | 7 | 6 |
| 1.0 | 25 | **7** | **3** |

Track A fails 27 of 64, Track C 21 of 64. Note the last row: **both tracks fail at the
loosest budget the generator produces**, where a feasible allocation is guaranteed to exist
by construction.

17 of those failures are shared; 10 are Track A only and 4 are Track C only. So it is
mostly a property of the instances and of the shared decision rule, not of either track's
own logic.

**Why.** `select_profile` ranks on `admit.extra_cost` — price — and never looks at
`extra_gpus`. Both tracks therefore buy cheap-but-GPU-hungry profiles early, exhaust the
budget, and strand later tasks with no admissible option. The GPU-efficient allocation is
affordable the whole time; neither track aims at it. Track C inherits this because §5.2.1
gives its repair pass the same cost-only `costAdjust`.

**This is per spec, not a bug.** §5.2.1 defines Track A's `costAdjust` as `extraCost` and
Track C's repair identically. So the finding is about the shared decision rule, not the
implementation of it.

**The RATE is partly an artefact of the anchor, and should not be quoted.** F2 sets the
budget to the GPUs used by the *most GPU-efficient* allocation — that is, in terms of
exactly the quantity this finding says the tracks ignore. A track that does not optimise
GPU-efficiency is therefore pushed toward overshooting almost by construction. The
mechanism is real and independent of the generator; the 42% is not. Evidence that the
anchor is an amplifier rather than the whole story: at tightness 1.0, plain greedy fails on
28% rather than nearly all, and Track B — whose repair is equally cost-only — fails on just
1 of 25 (F11). Cost-blind ranking is a handicap, not a death sentence.

**Consequence, per §5.3's T4 table:** this is the third outcome — "greedy frequently
infeasible → the construction needs the M1 analogue (O2) before it is viable" — arriving
three weeks earlier than T4 was scheduled. Whatever the M1 analogue turns out to be, it has
to make the ranking budget-aware. **Deliberately not implemented**: that is the machinery
T4 exists to evaluate, and building it now would prejudge the test. 035's call.

---

## F4 — Preliminary T4 signal on A vs C *(superseded by F10)*

Over solvable instances, cost gap above the exact optimum, feasible runs only:

| tightness | A mean gap% | C mean gap% | LP bound gap% |
|---|---|---|---|
| 0.7 | 10.87 | 11.14 | 13.72 |
| 0.8 | 8.26 | 8.79 | 15.79 |
| 0.9 | 10.00 | 10.22 | 14.90 |
| 1.0 | 11.56 | 16.25 | 15.92 |

Head-to-head on the 33 instances where both produced a feasible answer:

| | count |
|---|---|
| Track A strictly cheaper | 7 |
| Track C strictly cheaper | 2 |
| tied | 24 |

**Plain greedy is not losing to LP-rounding — it is marginally ahead on cost.** On the
fixture built to defeat it, greedy loses by 7%; on instances not built for that purpose it
wins or ties 31 times out of 33.

Where Track C is clearly better is **feasibility**: it fails 21 times to Track A's 27, and
only 3 times at the loosest budget against Track A's 7.

**Consequence, per §5.3's T4 table:** the first outcome — "greedy within a few percent of
LP-rounding → the full AGH machinery likely does not pay; simplify or cut Track A". Note
what this does and does not say. It does not say greedy is good; both tracks sit 8–16%
above optimum and fail often. It says the *elaborate* Track A is hard to justify on cost
when the plain version already matches a solver call — while the solver call is the more
reliable of the two at actually returning an answer.

**Caveat, since resolved.** At the time of writing Track C got two realisation attempts to
Track A's one. That has been equalised — `C` is now single-shot and `C2` carries the extra
attempt as its own condition. **F10 is the current T4 picture**; this finding is kept for
the record of how it looked before Track B and A+M1 existed.

---

## F5 — The LP integrality gap is large, as §1.7 predicts

Mean gap between the LP bound and the true optimum: **~15%**, stable across tightness
(13.7 / 15.8 / 14.9 / 15.9).

§1.7 says the integrality gap lives in (C2), because `n[m]` must cover a ceiling of
aggregate load over throughput and the LP returns fractional instance counts. A 15% gap is
consistent with that and is worth stating in Ch.2: it is the room an integer-aware method
has to beat the LP.

**This is the number T1 cares about.** Track B earns its place only if its bound closes
some of that 15%. If Track B's bound lands at the LP bound, §5.3's T1 table fires its last
row and the track should be cut or rejustified. That test is now cheap to run — the harness
records `bound_gap` for any track that reports a bound.

---

## F6 — The LP returns an integral routing. O6 is largely a non-question.

O6 asks for "the LP rounding policy". Two alternative policies were built to answer it —
one restricting to profiles the LP had opened (`n[m] > 0`), one taking the most
GPU-efficient profile among those with LP weight. Both were **deleted**, because across 76
instances they produced routings byte-identical to plain argmax, every single time.

The reason is structural. Measured over 80 LP solutions at 8 tasks / 4 profiles:

| quantity | value |
|---|---|
| `x[t][m]` values integral (0 or 1) | **99.5%** |
| LP solutions with fully integral `x` | **96%** (77 of 80) |
| `n[m]` values fractional | 53.4% |

The LP has no reason to split a task. `n[m]` is continuous in the relaxation, so it can buy
exactly the capacity a whole task needs. **All the fractionality — and therefore the entire
integrality gap — sits in `n[m]`**, exactly where §1.7 predicts it.

**Consequence for 075:** effort spent designing a rounding policy for the routing is close
to wasted. What determines Track C's cost is the **repair pass** that runs when the LP's
integral routing stops fitting once `n[m]` must be a whole number and (C3) binds. That is
the piece worth designing, and O6 should probably be reworded to say so.

**What did help.** Realising each candidate routing in two task orders — large-first and
small-first — cut infeasibility from 27 of 64 to 21, and mean gap from 14.6% to 13.2%. The
entire gain came from the second *order*, not from any policy. That is also what creates
the fairness wrinkle noted in F4: Track C now gets two attempts, Track A one.


---

## F7 — T1: the Lagrangian bound is consistently tighter than the LP bound

**The bound result is clean. The cost and feasibility results are confounded — read both
halves of this finding.**

Track B was built relaxing **(C1)**, the assignment constraints, because that is what §1.8
predicts for capacitated facility location. That choice is *an assumption adopted so T1 had
something to measure*, not a result. Relaxing (C3) has not been implemented, so T1's
decomposition question is answered only in the sense that (C1) does decompose per profile,
as predicted. v1's per-workflow claim is contradicted either way.

### The bound — clean, and decisive for O3

The bound comes out of the relaxation. It does not touch the primal heuristic, so nothing
below contaminates it.

| | Track B | Track C |
|---|---|---|
| mean bound gap below the true optimum | **2.40%** | 15.21% |
| invalid bounds (above the optimum) | **0** | 0 |

*The multiplier here is **ratio of means and inflated** — the same construction that broke
the 110× claim. Audited with paired per-instance statistics (F27): the median ratio is
**2.53× uniform, 2.00× structured**, not 6×. What survives, and survives strongly, is the
paired difference: the LP bound sits **12.6 [9.5, 15.6] percentage points** further from the
optimum than the Lagrangian bound, and the interval excludes zero. Quote the difference,
not the ratio.*

Over a separate 30-instance check, the Lagrangian bound was **strictly tighter than the LP
bound on 30 of 30**, never looser, never equal. On the hand-verified fixture it reaches
**280 — the exact optimum** — against the LP's 190.8.

**Consequence, per §5.3's T1 table:** the row to watch was *"Lagrangian bound = LP bound
consistently → Track B provides nothing Track C does not; cut it or rejustify"*. **That row
does not fire.** On this evidence Track B earns its place and §5.2.3 stands.

Two implementation choices protect this number, and both err against Track B: (C3) is
dropped rather than relaxed, which weakens the bound but keeps it valid; and the knapsack
scales float loads in the permissive direction — weights down, capacity up — which can only
*understate* the bound. So the result is not an artefact of favourable rounding.

### The cost and feasibility — confound checked, and it does not bind

Track B's subgradient step rule takes its incumbent upper bound from plain greedy. That
looked disqualifying: it would mean Track B could never be worse than Track A and never
fail where Track A succeeded, by construction rather than by merit.

So the identical relaxation was re-run with the warm start disabled (`B-cold`). The two are
**identical on every column**:

| | B (warm) | B-cold |
|---|---|---|
| feasible, of 64 solvable | 59 | 59 |
| matched the exact optimum | 55 | 55 |
| mean gap | 0.93% | 0.93% |
| bound gap | 2.40% | 2.40% |

**The warm start is inert.** Track B's own primal repair independently finds solutions at
least as good as greedy's on every instance measured, so the confound does not bind and the
cost column may be quoted.

That "identical" is only meaningful if the flag changes what runs, so it is verified rather
than assumed: warm-started Track B calls greedy exactly once, `B-cold` calls it zero times
(`test_warm_start_flag_actually_takes_effect`). Both facts are locked in by tests — if the
warm start ever stops being inert, the T4 comparison becomes circular again and only the
`B-cold` row may be used.

Against plain Track A, independently:

| | count |
|---|---|
| B-cold fails where A succeeded | **0** |
| B-cold strictly cheaper (of 37 both-feasible) | **11** |
| A strictly cheaper | **0** |
| tied | 26 |

### The runtime, which is the real trade

Track B costs **~0.95 s per instance** against Track C's 29 ms and Track A's under a
millisecond — roughly 30× Track C at 8 tasks. The subproblem is an exact knapsack DP per
profile per iteration, up to 120 iterations. Irrelevant at PoC scale; the first thing to
break if instances grow, and precisely the trade T4 should be pricing.

**Other caveats.** Step-size schedule, tolerance and iteration cap (O5) are untuned
defaults, not fitted and not justified by experiment.

---

## F8 — The M1 lookahead works, and it is free

Decision 2 asked for the M1 analogue as a separate condition so T4 could price it rather
than assume it. Priced:

| | A (plain greedy) | A+M1 (feasibility lookahead) |
|---|---|---|
| infeasible, of 64 solvable | 27 | **17** |
| matched the exact optimum | 23 | **29** |
| mean gap | 10.28% | **9.39%** |
| runtime | <1 ms | <1 ms |

**A 37% reduction in failures, and it also got slightly cheaper, at no measurable runtime
cost** at this scale. The lookahead has no tuning parameter — it is a feasibility test, not
a re-weighting — so it cannot have been fitted to these instances.

It does not eliminate the failure mode: 17 instances still strand a task. The lookahead is
one step and checks each remaining task in isolation, so it cannot see that two of them
need the same last GPU.

**Consequence:** F3's diagnosis is confirmed by construction. The failures were caused by
the shared rule ignoring `extra_gpus`, and making the construction feasibility-aware fixes
a large share of them. **035 still needs to reconcile `track_a_m1.py` against Cheng &
Nguyen's real M1** — this is an analogue built from the observed failure, not their
algorithm.

The complexity price is asymptotic, not wall-clock: O(|T|²·|C|²) against plain greedy's
O(|T|·|C|). Invisible at 8 tasks; the thing to watch if instances grow.

---

## F9 — The no-optimisation baseline is much worse, which is the point

| | STATIC | best heuristic |
|---|---|---|
| infeasible, of 64 solvable | **37** | 5 (B) |
| matched the optimum | 7 | 55 (B) |
| mean gap | **23.06%** | 0.93% (B) |

STATIC routes every task to its cheapest eligible profile independently — no coupling
awareness, no budget awareness. It fails on 58% of solvable instances and sits 23% above
optimum when it does succeed.

This is the sanity check the evaluation needed: the optimisation is doing real work.
Without this row, "Track A is 10% above optimum" has no scale to be read against.


---

## F10 — T4, consolidated: Track B dominates, and the question has changed shape

All conditions, 64 solvable instances, ordered by mean gap:

| condition | infeasible | matched optimum | mean gap | runtime |
|---|---|---|---|---|
| MILP (exact / Murakkab) | 0 | 64 | 0.00% | 32 ms |
| **B** (Lagrangian) | **5** | **55** | **0.93%** | 954 ms |
| A+M1 (greedy + lookahead) | 17 | 29 | 9.39% | <1 ms |
| A (plain greedy) | 27 | 23 | 10.28% | <1 ms |
| C2 (LP + 2 attempts) | 21 | 20 | 13.16% | 25 ms |
| C (LP + rounding) | 27 | 16 | 14.58% | 29 ms |
| STATIC (no optimisation) | 37 | 7 | 23.06% | <1 ms |

### T4 as originally asked

*"Is Track A worth its cost relative to Track C? Track A has six sub-modules and produces
no bound; Track C is a solver call plus rounding."*

On equal terms — one attempt each — **plain greedy beats LP-rounding**: 10.28% against
14.58%, identical feasibility (27 failures each), and it does so roughly 30× faster. Give
Track C its second attempt (C2) and it closes to 13.16% with 21 failures, still behind on
cost while ahead on feasibility.

So the answer to T4 as written is **neither track earns much over the other**, and per
§5.3's first outcome the elaborate Track A machinery is hard to justify against Track C —
because the *plain* version already matches it.

### But that is no longer the interesting question

Track B is at **0.93% mean gap with 5 failures**, against every heuristic's 9–15% and 17–27
failures. It matches the exact optimum on 55 of 64 instances. Its bound gap is 2.40%
against Track C's 15.21%.

The real T4 trade is no longer A versus C. It is **Track B's quality against its runtime**:
954 ms per instance versus under a millisecond for greedy, at 8 tasks and 4 profiles. That
ratio is the thing to measure as instances grow, and it is not measured here — §5.7 stands,
nothing in this PoC says anything about scale.

### What the team should take from this

1. **A+M1 over plain A, on this evidence.** Same runtime, 37% fewer failures, lower gap.
2. **Track C is the weakest of the three tracks** on both cost and feasibility, and is only
   worth keeping for its bound — which Track B beats by 6×. Its own §5.9 status of "stable,
   least affected" is no longer the whole story.
3. **T4's decision criteria need rewriting** before D10. They ask an A-versus-C question
   that the data has moved past.


---

## F11 — The pooled table oversamples loose budgets. Broken out, the picture mostly holds.

The aggregate table in every finding above pools all tightness levels, and the sample is
badly skewed toward the loosest: of 64 solvable instances, **25 come from tightness 1.0 and
41 from the two loosest levels**. T3's whole premise is that the evaluation has signal only
where the budget binds, so a pooled mean is weighted toward the region the plan says shows
least. That is a defect in how the results were presented, not merely a caveat.

Broken out — `inf` = infeasible, `=opt` = matched the exact optimum:

```
 tight  solv |         A          |       A+M1         |         B          |         C
             | inf  gap%   =opt   | inf  gap%   =opt   | inf  gap%   =opt   | inf  gap%   =opt
   0.6     3 |   2   0.0      1   |   1   0.0      2   |   1   0.0      2   |   3     -      0
   0.7     6 |   3  10.9      2   |   3  10.9      2   |   1   0.0      5   |   3  14.9      1
   0.8    13 |   7   8.3      4   |   5   6.2      6   |   1   1.4     11   |   7  10.3      3
   0.9    16 |   7  10.0      6   |   5  10.9      6   |   1   1.1     14   |   8  10.0      4
   1.0    25 |   7  11.6     10   |   3  10.8     12   |   1   0.9     22   |   5  17.7      8
```

**Track B's dominance is not a pooling artefact.** It leads at every tightness level, and
its failure count is **exactly 1 at every level** — the same instance, regardless of how
many are solvable. Where the budget binds hardest (0.7–0.8), the separation is at its
widest: B is at 0.0–1.4% gap against A's 8.3–10.9% and C's 10.3–14.9%.

**Track C is worst where the budget binds.** At tightness 0.6 it fails on all three solvable
instances. Its `§5.9` billing as "stable, least affected" does not survive contact with the
binding region.

**A+M1's advantage narrows under pressure.** It halves failures at 1.0 (7→3) but barely
helps at 0.7 (3→3). The lookahead is one step, and one step is not enough when almost
nothing fits.

### What this does and does not rescue

It answers the sampling objection. It does **not** answer the scale objection, and the two
are easy to confuse. Every row here is 8 tasks and 4 profiles.

Note what Track B actually is at this size: its subproblem is an exact knapsack, and at 8
tasks that knapsack is trivial to solve exactly. So Track B is close to an exact method
wearing a heuristic's clothes. The plausible failure mode is not that it is wrong, but that
**everything making it good here is what scale erodes** — knapsack DP cost, iteration count,
and the duality gap all grow together. Until that is measured, "Track B dominates" is a
claim about 8-task instances and nothing more.


---

## F12 — Re-run on a second, structurally different generator: most findings survive

The standing objection to everything above was that it all came from one generator written
by the same hand as the tracks and the metrics. `instances/structured_generator.py` was
built to disagree wherever it plausibly could — sublinear throughput against linear price
(so large profiles are bad value per GPU, inverting the original's near-neutrality),
lognormal loads instead of uniform, GPU tiers {1,2,4,8}, floors clustered on a minority of
tasks. Measured difference: loads 7× more heavy-tailed, pool sizes skewed the opposite way.

Same conditions, same harness, same anchor. 8 tasks, 4 profiles, seeds 0–24, tightness
0.6–1.0.

```
                UNIFORM (63 solvable)          STRUCTURED (75 solvable)
cond      infeas  =opt   gap%   bound%   infeas  =opt   gap%   bound%
STATIC        36     7  23.06        -       44     7  25.48        -
A             26    23  10.28        -       29    23  14.78        -
A+M1          17    28   9.59        -        2    42  11.34        -
B              5    54   0.95     2.44        1    65   1.76     8.39
C             26    16  14.58    15.21       22    18  18.69    23.47
```

Zero invariant violations on either generator.

### What survived

**Track B's dominance (F10/F11).** 1 infeasible of 75, 65 exact optima, 1.76% mean gap. It
still beats every heuristic on both cost and feasibility, on instances built to be
structurally hostile to the first generator's assumptions. This is the strongest evidence
in the whole log, and it is the finding I most expected to break.

**The Lagrangian bound beats the LP bound (F7).** Still true everywhere — but see the
correction below.

**STATIC is much worse (F9).** 25.48% gap, 44 of 75 infeasible. Optimisation is doing real
work under both structures.

**Neither A nor C clearly wins (F4).** Greedy is cheaper (14.78% vs 18.69%), Track C is more
often feasible (22 failures vs 29). The same inconclusive split as before, for the same
reason: they are differently bad rather than one being better.

### The correction: "6× tighter" was a generator-specific number

F7's headline said the Lagrangian bound is **6× tighter** than the LP bound. That is the
uniform generator's number (2.44% against 15.21%). On the structured generator the ratio is
**2.8×** (8.39% against 23.47%).

Both bounds loosen on the harder instances, and Track B's loosens proportionally more. The
robust claim is **"consistently tighter, by a factor between roughly 3 and 6 depending on
instance structure"** — not "6×". T1's conclusion is unaffected: the "cut Track B" outcome
still does not fire, because the bounds never converge. But the multiplier should not be
quoted without the qualifier, and I had quoted it.

### The upgrade: A+M1 is far more valuable than the first generator suggested

| | uniform | structured |
|---|---|---|
| infeasible, A → A+M1 | 26 → 17 (−35%) | **29 → 2 (−93%)** |
| exact optima, A → A+M1 | 23 → 28 | **23 → 42** |

On instances with heavy-tailed loads and expensive large profiles, feasibility is far more
fragile — and the lookahead is worth much more. This also **overturns F11's caveat** that
A+M1's advantage narrows under pressure; that was a property of the uniform generator, not
of the mechanism. Still no measurable runtime cost.

### One thing that got worse — since diagnosed and fixed, see F17

Track C's **maximum** gap on structured instances is **100.85%** — a solution costing twice
the optimum. The cause turned out not to be the repair pass but the LP itself: it prices
profiles by rate and cannot see that a large profile's integer instance will sit mostly
empty. F17 has the full diagnosis and a fix that halves Track C's mean gap.

### What this still does not answer

The scale objection, untouched. Both generators run at 8 tasks and 4 profiles. Note that
the exact MILP's runtime already **doubled** on the structured instances (37 ms → 80 ms)
while Track B's fell slightly — the first hint that instance structure, not just size,
drives the solver cost that the whole heuristic premise depends on.


---

## F13 — Scale: the exact solver does break down, and Track B breaks down faster

This is the finding that changes the project's conclusions, and it goes against the track
the rest of this log has been praising.

### Does the exact MILP break down at all?

Objective 1.2.2 asks for *"non-exact alternatives to MILP"*. That premise requires the MILP
to become expensive somewhere. It does — but far later than expected, and only on one
instance family. Mean over 3 seeds, tightness 1.0:

| tasks / profiles | uniform | structured |
|---|---|---|
| 8 / 4 | 0.022 s | 0.058 s |
| 16 / 6 | 0.115 s | 0.170 s |
| 32 / 8 | 0.266 s | 0.256 s |
| 64 / 10 | 1.400 s | 0.300 s |
| **128 / 12** | **21.2 s** (max 55 s) | **1.9 s** |

**Instance structure matters more than instance size.** The uniform generator's profiles are
near-interchangeable, which gives CBC a large symmetric search space; the structured
generator's distinct GPU tiers and heavy-tailed loads break that symmetry and stay cheap.
Note this *reverses* with scale — structured instances were the harder ones at 8 tasks
(58 ms against 22 ms) and are 11× cheaper at 128.

**Consequence:** the premise holds, but only for a specific instance family, and "MILP is
too slow" cannot be asserted without saying on what. Any Chapter 3 claim needs to name the
family.

### Does Track B scale into the gap?

No. It is the opposite of what the 8-task results implied. Uniform generator, 2 seeds:

| tasks | MILP | Track B | B ÷ MILP | B gap |
|---|---|---|---|---|
| 8 | 0.031 s | 0.69 s | 22× | 0.00% |
| 16 | 0.053 s | 7.52 s | 142× | 1.51% |
| 24 | 0.115 s | 15.05 s | 131× | 0.00% |
| 32 | 0.321 s | **34.55 s** | **108×** | 0.04% |

**Track B is roughly 100× slower than the exact method it exists to replace, at every size
tested.** Its answers are excellent — 0–1.5% gap — but you would always have been better off
running the MILP, which is both faster and optimal. A heuristic that is slower than exact
has no reason to exist as a heuristic.

This is exactly the failure predicted when Track B's dominance was first questioned: its
subproblem is an exact knapsack, which is cheap at 8 tasks and is precisely what scale
erodes. Extrapolating its growth, Track B would need hundreds of seconds where the MILP
needs 21.

### The caveat that matters, and it is not small

**This may be my implementation rather than the method.** The subproblem is a pure-Python
0/1 knapsack DP with a full traceback table, O(n × capacity) per profile per iteration, run
for up to 120 iterations, with capacity scaled by 100. That is the obvious suspect, and a
vectorised DP, a coarser scale, a smarter iteration schedule, or early termination could all
move it by an order of magnitude or more.

What is *not* implementation-dependent is the shape: capacity grows with total load, so the
subproblem cost grows with the batch, and it is paid per profile per iteration. Lagrangian
relaxation here is inherently heavy. Whether it is 100× heavy or 10× heavy is an open
engineering question. **075 should not read this as "Track B is dead" — it should read as
"Track B's subproblem needs profiling before any scale claim is made."**

### What this does to T4

The T4 answer at 8 tasks and the T4 answer at 32 tasks are different answers.

At 8 tasks (F10): Track B dominates on quality, everything else is 9–18% above optimum.

At 32 tasks: the MILP solves in 0.32 s and is optimal. Track B takes 34 s to be 0.04% worse.
**Track C stays fast** — 0.092 s at 32 tasks — and its gap *improves* with scale (11.3% → 3.8%),
as does A+M1's (11.3% → 5.1%).

So the practical ordering inverts. Track B's value is not as an allocator but as a **bound
generator**, which is what §5.2.3 always said it was for and what T1 measures. Its cost as
an allocator is not competitive at any size measured.

### What is still not known

Where the crossover is. Track B was not run past 32 tasks because it takes 34 s per
instance there; the MILP does not become genuinely expensive until ~128 on uniform
instances. Whether a *profiled* Track B could win in that window is the open question, and
it is an engineering question, not a research one.


---

## F14 — At scale the ordering inverts: Track C wins, the greedy tracks collapse

5 seeds per row, tightness 1.0. `inf` counts instances the MILP solved and the condition
could not. Track B is absent past 32 tasks — at 34 s per instance it was not runnable here,
which is itself F13's finding.

**uniform**

| tasks/prof | MILP s | C s | C gap | C inf | A gap | A inf | A+M1 gap | M inf |
|---|---|---|---|---|---|---|---|---|
| 16 / 6 | 0.125 | 0.056 | 8.15% | 1 | 9.49% | 1 | 9.49% | 1 |
| 32 / 8 | 0.222 | 0.106 | 3.90% | 1 | 7.27% | 2 | 7.23% | 1 |
| 64 / 10 | 11.288 | 0.114 | **0.53%** | 3 | — | **5** | — | **5** |
| 128 / 12 | 10.997 | 0.110 | **1.16%** | 3 | — | **5** | — | **5** |

**structured**

| tasks/prof | MILP s | C s | C gap | C inf | A gap | A inf | A+M1 gap | M inf |
|---|---|---|---|---|---|---|---|---|
| 16 / 6 | 0.194 | 0.102 | 22.53% | **0** | 8.31% | 4 | 4.15% | 3 |
| 32 / 8 | 0.281 | 0.119 | 8.28% | **0** | — | 5 | — | 5 |
| 64 / 10 | 0.215 | 0.124 | 6.98% | 1 | — | 5 | — | 4 |
| 128 / 12 | 1.365 | 0.228 | **2.86%** | **0** | — | 5 | — | 5 |

### Track C is the only heuristic that works at scale

Its gap improves with size on both generators here — 8.15% → 1.16% on uniform, 22.53% →
2.86% on structured — while its runtime stays essentially flat, 0.06 s to 0.23 s across a
16× increase in tasks. *(The monotonicity is a tightness-1.0 artefact; off the knife edge
the gap sits in a 2–5% band without a clean trend. See F16.)*

At 64–128 tasks on uniform instances that is a **~100× speedup over the exact solver for
roughly 1% cost** (11 s → 0.11 s). That is exactly what Objective 1.2.2 asks a non-exact
alternative to deliver, and it is the first result in this log that delivers it.

The likely reason the gap shrinks: the integrality gap is a *rounding* penalty, and rounding
error amortises over more tasks. With 8 tasks one badly-rounded profile is a large fraction
of total cost; with 128 it is not.

### The greedy tracks fail here — but see F15 before believing why

Track A fails on **all 5 instances** at 64 and 128 tasks on uniform, and from 32 tasks
upward on structured. A+M1 delays it but does not prevent it.

**This is largely an artefact of the budget anchor and is corrected in F15.** The tracks
recover completely — 0 of 5 to 5 of 5 — with 25% more budget. Do not quote "the greedy
tracks collapse at scale" from this section.

### I have to withdraw a correction I made

Two commits ago I amended §5.9 of the PoC plan to say Track C was **"contradicted by
measurement — weakest of the three tracks"**, on the strength of the 8-task results. That
was wrong, and it was wrong in the most instructive way: it was a confident conclusion drawn
from the only regime that had been measured.

At scale Track C is the **strongest** heuristic — the only one that returns answers at all
past 32 tasks, at ~1–3% of optimum and near-constant runtime. §5.9 has been amended again,
and this time it names the regime.

### What T4's answer actually is

| regime | best heuristic | why |
|---|---|---|
| ≤ 8 tasks | Track B on quality | 0.9% gap — but the MILP is 32 ms and optimal, so no heuristic is needed |
| 16–32 tasks | Track C | greedy is failing, B costs 100× the MILP |
| 64+ tasks | **Track C, decisively** | greedy returns nothing; MILP costs 100× more for ~1% |

**No heuristic is justified below ~32 tasks** — the MILP is faster and optimal. Above it,
exactly one of the three tracks earns its place, and it is not the one the 8-task data
favoured.


---

## F15 — F14's collapse was a knife edge, not a scaling failure. Correcting my own finding.

F14 reported that Track A and A+M1 fail on every instance at 64 and 128 tasks and concluded
that greedy construction collapses at scale. That conclusion is wrong, and the way it is
wrong is the same trap flagged against F3.

Every scale row was run at `budget_tightness = 1.0` — meaning the budget is set to **exactly**
the GPUs used by the reference allocation, which is the *most GPU-efficient* routing. That
is a razor-thin margin: any method that does not reproduce the GPU-efficient routing almost
exactly will overshoot. And the chance of a cost-ranking method matching it by accident goes
to zero as tasks are added. So the anchor manufactures a failure that grows with instance
size, and it is easy to mistake for a scaling property.

Feasible out of 5, as the budget is loosened past the reference:

| tasks | ×1.00 | ×1.25 | ×1.50 | ×2.00 | ×3.00 |
|---|---|---|---|---|---|
| 64 — Track A | **0** | **5** | 5 | 5 | 5 |
| 64 — A+M1 | **0** | **5** | 5 | 5 | 5 |
| 64 — Track C | 2 | 5 | 5 | 5 | 5 |
| 128 — Track A | **0** | **5** | 5 | 5 | 5 |
| 128 — A+M1 | **0** | **5** | 5 | 5 | 5 |
| 128 — Track C | 2 | 5 | 5 | 5 | 5 |

**A 25% budget increase takes every track from near-total failure to complete success.** The
cliff is entirely at the anchor point. Track C is less exposed — it gets 2 of 5 where greedy
gets 0 — because the LP naturally lands near a GPU-efficient solution, but even it is mostly
failing at ×1.00.

### What survives from F14, and what does not

**Does not survive:** "the greedy tracks collapse at scale". They fail at one specific budget
that the generator happens to make the default, and recover fully just past it.

**Survives:** Track C's cost gap improving with size (8.15% → 1.16% uniform, 22.53% → 2.86%
structured), its near-flat runtime, and the MILP's blow-up on uniform instances at 128
tasks. Those are quality and runtime results, not feasibility results, and the anchor does
not drive them.

**Also survives, and is strengthened:** F13's finding on Track B. Its 100× runtime penalty
is a timing measurement, untouched by feasibility.

### The methodological lesson, since it has now happened three times

`budget_tightness = 1.0` is not a neutral default. It is the tightest budget at which
feasibility is still guaranteed, which makes it the single most adversarial setting in the
sweep — and it is the one every scale run used because it is the only one where instances
are reliably solvable at size.

Anything measured only at ×1.00 is measured on a cliff edge. **T3's sweep should extend
above the reference, not just below it.** That is a change to the experimental design, and
it belongs to 089.


---

## F16 — The scale comparison, off the knife edge. Track C earns Objective 1.2.2.

Re-run of F14 at **1.25× the reference budget**, where F15 showed every track can actually
compete. 3 seeds per row. `inf` is A/A+M1/C.

**uniform** — all tracks feasible on every instance, so the gap columns are comparable

| tasks | MILP s | C s | C gap | A gap | A+M1 gap | inf |
|---|---|---|---|---|---|---|
| 16 | 0.106 | 0.054 | 5.09% | 10.95% | 10.95% | 0/0/0 |
| 32 | 0.252 | 0.079 | 5.20% | 8.48% | 8.48% | 0/0/0 |
| 64 | 5.127 | 0.086 | **2.47%** | 12.79% | 12.79% | 0/0/0 |
| 128 | **17.750** | **0.162** | **4.58%** | 15.38% | 15.38% | 0/0/0 |

**structured** — greedy still fails here, so read the caveat below before comparing columns

| tasks | MILP s | C s | C gap | A gap | A+M1 gap | inf |
|---|---|---|---|---|---|---|
| 16 | 0.198 | 0.077 | 23.64% | 8.31% | 37.39% | 2/0/0 |
| 32 | 0.250 | 0.112 | 12.40% | 34.52% | 25.65% | 2/1/0 |
| 64 | 0.337 | 0.096 | 11.55% | 27.42% | 27.42% | 1/1/0 |
| 128 | 0.343 | 0.188 | **3.44%** | 17.96% | 17.96% | 1/1/0 |

### The result Objective 1.2.2 actually asked for

On uniform instances at 128 tasks: the exact solver takes **17.75 s**, Track C takes
**0.162 s** and lands **4.58%** above optimum. That is a **~110× speedup for under 5% cost**,
with every track feasible so the comparison is like-for-like.

That is the first clean statement in this log of the form the project's objective requires:
a non-exact alternative that is dramatically cheaper than the MILP at a bounded quality
cost. It holds on the instance family where the MILP is actually expensive — which is the
only family where the question matters.

**Track C beats greedy at every size, and the margin widens.** 5.09% against 10.95% at 16
tasks; 4.58% against 15.38% at 128. Greedy gets *worse* with scale (10.95% → 15.38%) while
Track C does not.

### Correcting F14 again: "improves monotonically" was also a tightness-1.0 artefact

F14 said Track C's gap improves monotonically with size. At 1.25× it does not — 5.09, 5.20,
2.47, 4.58 on uniform. The supportable claim is that **Track C's gap stays in a 2–5% band
and does not degrade with scale**, which is what matters and is weaker than what F14 said.

### A flaw in my own comparison script, on the structured rows

The structured gap columns average over **different subsets of instances**, because greedy
was infeasible on some and the ad-hoc script excluded failures per condition rather than
per instance. At 16 tasks, Track A's 8.31% is the average over the single instance it
solved, while A+M1's 37.39% is over all three. **A+M1 is not worse than A there** — it is
being scored on harder instances that A simply failed.

`harness/metrics.py` was written specifically to prevent this: it excludes unsolvable
instances from every aggregate and counts infeasible runs beside the gap rather than
averaging over them. The scale scripts bypassed it for speed and reintroduced the exact bias
the module exists to stop. **The structured rows should be re-run through the harness before
any of them is quoted.**

The uniform rows are unaffected — nothing was infeasible, so every condition is averaged
over the same three instances.

### Where this leaves the tracks

| | verdict |
|---|---|
| **Track C** | The result. ~110× faster than exact at 128 tasks for under 5%, flat runtime, feasible everywhere on uniform |
| **Track A / A+M1** | Fast but 8–15% off and worsening with scale. Cheap enough to keep as a warm start or fallback; not the answer |
| **Track B** | Best bound in the log (F7) and ~100× slower than exact as an allocator (F13). A bound generator, not an allocator |
| **MILP** | Optimal and cheap below ~32 tasks. The heuristics only justify themselves beyond that |


---

## F17 — Track C's worst case, diagnosed and fixed. The LP cannot see rounding waste.

F12 recorded a 100.85% maximum gap for Track C and left it undiagnosed. It is now
diagnosed, and the cause refines F6.

### The failure, in full

Structured generator, 8 tasks, seed 3, tightness 1.0:

```
optimum   395.2   n={m1:1, m2:1}   4 of 8 GPUs
track C   793.8   n={m2:2, m3:1}   8 of 8 GPUs
LP bound  303.5

m1: gpu=2  thr=15.57  price=199.20   price/thr=12.79
m3: gpu=4  thr=33.54  price=401.74   price/thr=11.98   <- better rate
```

Three tasks (`t5, t2, t6`, total load **7.88**) are ineligible for `m2`. The LP sent them to
`m3` because `m3` has the better price per unit throughput — 11.98 against 12.79. **In the
relaxation that is correct**: `n[m3] = 7.88/33.54 = 0.235` instances costs 94.4, cheaper
than `m1`'s 0.506 instances at 100.8.

Integrally it is a disaster. `m3` costs a whole 401.74 instance to carry 7.88 units,
**wasting 76% of it**, where `m1` would have cost 199.20.

**The LP prices profiles by rate; an integer allocation pays for whole instances.** The
larger the profile, the wider that gap. This is the integrality gap of §1.7 with a concrete
face on it.

### This refines F6, which was too optimistic

F6 found the LP returns an integral routing 96% of the time and concluded that rounding the
routing is "nearly free". Mechanically true — but the routing is integral **and still
wrong**, because it was chosen under a relaxation that never sees large-profile waste. The
cheapness of rounding says nothing about the quality of what is being rounded.

### The fix, and why single-move relocate cannot do it

`core/consolidation.py`: relocate **every** task on one profile to another, together. Moving
one task off an underused profile leaves the instance open and still paid for, so every
single-move neighbourhood sees a local optimum. Only closing the instance recovers its price.

Measured, as condition `C+cons`:

| | C | C+cons |
|---|---|---|
| uniform, 8 tasks — mean gap | 14.58% | **7.21%** |
| uniform — matched optimum | 16 | **23** |
| structured, 8 tasks — mean gap | 19.05% | **9.66%** |
| structured — matched optimum | 17 | **24** |
| structured — **max gap** | **100.85%** | **44.01%** |
| runtime | 0.030 s | 0.026 s |
| bound | unchanged | unchanged |

**It halves Track C's mean gap on both generators at no runtime cost** — but see the audit
below before quoting that.

**Audited (F27): the MEDIAN paired improvement is 0.00% on both generators.** Consolidation
does nothing at all on a typical instance. The mean improvement is real — paired 5.31%
[0.56, 10.07] uniform and 13.29% [1.01, 25.56] structured, both excluding zero — but it is
carried by a minority of instances where it helps enormously, of which the 100.85% case
above is the extreme. The honest statement is **"fixes a rare, severe failure mode"**, not
"halves the gap".

It does not change feasibility — it improves cost, it does not rescue a failed allocation —
and it cannot change the bound, which is a relaxation property.

At scale the gain is smaller (uniform 4.25% → 3.35%, structured 15.86% → 13.52%) simply
because Track C is already close there. The pass matters most where Track C is worst.

### The limitation, which is not a bug

This neighbourhood is *"all tasks on a profile → one other profile"*. The adversarial
fixture needs *"**some** tasks on a profile"* — `t1` and `t2` to `m2` while `t3` stays on
`m1`, because `t3` is eligible only for `m1`. The intersection of destinations over all of
`m1`'s tasks is empty, so no move exists and the pass correctly leaves greedy's 300 alone.

**Two different multi-move neighbourhoods, and this implements one of them.** F1's fixture
and F17's failure are the same phenomenon from opposite ends — one where consolidating is
right, one where de-consolidating is. A subset-move neighbourhood would cover both and is
not built. There is a test asserting the fixture is *unchanged*, so the limitation cannot be
mistaken for a regression.

### Scope

v2 §6.5 defers relocate/consolidate to T4. The pass lives in `core/` and is wired only into
a separate condition, so no existing track changes behaviour and T4 can still price it.


---

## F18 - O9 answered: scoped re-optimisation works, and is not worth building

**Outside PoC scope** (see `prototype/README.md`) - built because the question is cheap to
answer and expensive to get wrong in Semester 2.

Section 3.3 specifies J9 as re-invoking J3 "for affected workflows only", then doubts its
own specification: *"Under (C2), re-routing one workflow changes load on shared profiles,
which changes instance counts, which affects every other workflow using those profiles.
Scoped re-optimisation may not be well-defined."* Deferred to Semester 2 as O9.

Global versus scoped, 40 instances of 12 tasks / 5 profiles, one of three workflows marked
affected, exact MILP as the allocator:

| generator | budget | infeasible | more expensive | matched global |
|---|---|---|---|---|
| uniform | 1.00x | **24** | 8 | 8 |
| uniform | 1.25x | 6 | 18 | 16 |
| uniform | 1.50x | 0 | 20 | 20 |
| uniform | 2.00x | 0 | 20 | 20 |
| structured | 1.00x | **32** | 6 | 2 |
| structured | 1.50x | 3 | 20 | 17 |
| structured | 2.00x | 0 | 22 | 18 |

### It is well-defined - the infeasibility was the anchor again

At 1.00x scoped re-optimisation failed on 24 of 40 uniform and 32 of 40 structured
instances, which looks like Section 3.3's fear confirmed. It is not: by 1.50x the failures
are gone entirely. This is the same knife edge as F15, caught this time *before* the finding
was written rather than after.

So the answer to O9 as literally asked - *is it well-defined?* - is **yes**.

### But it is vacuous, which is the real finding [CORRECTED]

**The first version of this finding measured the wrong thing, and its headline was wrong.**
It marked one arbitrary workflow as affected and concluded that scoping is worse than a
global re-run about half the time, at a mean 22% cost penalty.

That is not how J9 is triggered. Drift is detected on a **profile**, so the affected
workflows are *those with a task routed to the drifted profile* - not an arbitrary one.
Re-run that way, over the same 60 instances:

| affected set | infeasible | worse | same | mean penalty | workflows affected |
|---|---|---|---|---|---|
| arbitrary, one workflow | 0 | 31 | 29 | 11.53% | 1.00 of 3 |
| **derived from the drifted profile** | 0 | **0** | **60** | **0.00%** | **2.95 of 3** |

Scoped re-optimisation is not worse. It is **identical to global, every time** - because the
affected set is almost the entire batch.

That degeneracy is structural, not an artifact of these instances having only three
workflows. Relabelling 24-task instances into more workflows and drifting the most-used
profile:

| workflows | affected (mean) | as % | affected = all |
|---|---|---|---|
| 2 | 2.00 | 100% | 40 of 40 |
| 3 | 3.00 | 100% | 40 of 40 |
| 5 | 4.90 | 98% | 36 of 40 |
| 8 | 7.38 | 92% | 20 of 40 |
| 12 | 10.05 | **84%** | 8 of 40 |

**A shared profile is shared by nearly everyone.** Even at twelve workflows, drift on one
profile touches ten of them.

### What the two experiments say together

They bracket the design. Scope the re-optimisation **correctly** - to every workflow
actually touching the drifted profile - and it does the same work as a global run, so it
saves nothing. Scope it **narrower** than reality, as the first experiment did by taking one
workflow, and it costs a mean 22% and up to 51% more.

So "affected workflows only" is either a no-op or a penalty, and there is no setting where
it pays. Section 3.3's instinct was exactly right - *"re-routing one workflow changes load
on shared profiles, which affects every other workflow using those profiles"* - it just
surfaces as vacuousness rather than as undefinedness.

### Why this says "do not build it"

Unchanged, and now better supported. A global re-optimisation costs about 0.1 s on these
instances. Scoping adds a component, a correctness question, and a failure mode, in
exchange for excluding roughly 16% of workflows from a re-run that is already cheap.

**Recommendation for 077: do not build scoped re-optimisation. Re-optimise globally on every
drift signal.** That removes a component from Semester 2, closes O9, and removes the
"affected workflows only" language from Section 3.3 and J9.

The condition that would change this: if global re-optimisation becomes expensive at scale -
plausible, since F13 shows the MILP reaching 21 s at 128 tasks - then scoping is worth
revisiting, against Track C rather than the exact solver. But the affected set would still
be ~84% of workflows, so the saving would remain small.

### Caveat on the interpretation

Section 3.3 does not define "scoped" precisely. The reading implemented is the conservative
one: frozen tasks keep their profiles and their GPUs are deducted from the budget. A more
permissive reading - letting re-optimised tasks use headroom inside instances the frozen
tasks already paid for - would score better, but it double-counts capacity unless the frozen
instance counts are also recomputed, at which point it is a global run wearing a different
name. That tension is the real content of Section 3.3's doubt.


---

## F19 - Section 4.5's "EMA update per observation" is wrong for reliability

**Outside PoC scope.** Found while stress-testing `prototype/profiling.py`, not by a test
that was looking for it.

Section 4.5 specifies "EMA update per observation" for the Profile Store. Applied to
latency that is correct - it is a continuous quantity and an EMA tracks drift in it well.
Applied to **reliability** it is unusable, because reliability is estimated from a binary
success/failure signal.

With the specified EMA at alpha 0.3, a profile at 0.99 reliability that observes **99
successes and then one failure** reports `0.70`. True rate: 0.99. One failed call in a
hundred moves the estimate 30% of the way to zero, and it takes roughly eight consecutive
successes to climb back.

### Why this would have been expensive

Reliability is not a display value. It is the filter that builds `C(t)`:

    C(t) = { m : rel(m) >= R_min(t) and lat(t,m) <= L_max(t) }

So under the specified EMA, **one failed call makes a profile ineligible for every task with
a floor above 0.7**, pools collapse, the drift detector fires, and the batch is re-allocated
- on the evidence of a single call. The entire reliability pillar would have been driven by
noise, and the symptom (constant thrashing) sits a long way from the cause (an estimator
choice in one line of section 4.5).

### The fix, and the second bug inside it

Reliability now uses a **decayed counting estimator** with a weak prior:

    rel = (decayed successes + prior) / (decayed trials + 2 * prior)

Recent behaviour still dominates, so genuine degradation is still caught - the property the
EMA was chosen for - but a single failure moves the estimate by one observation's worth of
evidence rather than by 30%.

The first version of that fix had its own bug, worth recording because it is subtle. Decay
sets the effective sample size at `1/(1 - decay)`, and an unbroken run of successes
converges to `(N + p) / (N + 2p)` - so **a short memory imposes a ceiling on achievable
reliability**. At decay 0.98 with a Laplace prior of 1.0 that ceiling is 51/52 = **0.981**,
and any task with `rel_floor = 0.99` would have been permanently unservable by a measured
profile. Nothing would have raised an error; those tasks would simply always have been
infeasible.

Settled at decay 0.995 (effective sample ~200) and a Jeffreys prior of 0.5, ceiling 0.9975.

| sequence | EMA (as specified) | counting estimator |
|---|---|---|
| 500 successes | 1.000 | 0.9973 |
| 99 successes, then 1 failure | **0.700** | 0.9815 |
| 200 successes, then 50 failures | 0.000 | 0.6913 |

The last row is the check that robustness did not cost sensitivity.

### What this means for the documents

**Section 4.5 needs amending**: EMA for latency, a decayed counting estimator for
reliability. One line in the document, a real change in behaviour.

Still open for 077: the compatibility score remains **[PROPOSED]** and unreconciled, and it
requires running the allocator to evaluate - so drift detection is not the cheap signal
section 4.5 implies.

---

## F20 — Subset-move consolidation resolves the aggregate-coupling trap

Built in `core/consolidation.py` (`consolidate_subsets`) and `tracks/track_a_subset.py`
(condition `A+subset`). Owner: 035.

Plain greedy was shown by `instances/fixtures/adversarial_3t2p.py` to be trapped by
aggregate coupling (cost 300 vs optimum 280), and multi-start plus single-move relocate
provably failed because the improving move requires moving two tasks *together*. F17's
consolidation pass moved *all* tasks on a profile, which failed on the fixture because t3's
strict reliability floor blocked relocating the entire group.

`consolidate_subsets` evaluates k-subset relocations (k ∈ {1, 2}). On the adversarial
fixture, it immediately finds the joint move {t1, t2} → m2, **recovering the exact
optimum of 280**.

On generated benchmarks across the extended sweep:
- **Structured generator (21 solvable instances):** Mean gap drops from **32.37% down to
  1.57%** (a 20× reduction in error). Optimal solutions nearly triple from 4 to 11.
- **Uniform generator (18 solvable instances):** Mean gap falls from **11.09% to 4.51%**,
  increasing optimal solutions from 7 to 12.

This settles the T2 algorithmic challenge: a 2-subset relocation neighborhood is both
computationally trivial and sufficient to dismantle aggregate coupling.


---

## F21 — The (C3) Lagrangian relaxation arm and the dual bound hierarchy

Built in `tracks/track_b_c3.py` (condition `B-C3`). Owner: 075.

Answers T1 / O2. Track B in `track_b_lagr.py` relaxed (C1) by assumption. This module
relaxes the scalar GPU budget (C3) with multiplier μ ≥ 0:

    L(μ) = -μ · B + min_{x, n} Σ_m n[m] · (price(m) + μ · gpu(m))

Under continuous instance counts, the subproblem decomposes **per task** into independent
rate minimizations. The 1D concave dual problem is solved to optimality via bisection in
**under 1 ms** (compared to 0.6–0.9 s for Track B's knapsack DP).

### The Empirical Dual Hierarchy

Evaluated under matched conditions across 39 solvable instances:

| Generator | B-C3 Bound Gap | Track C (LP) Bound Gap | Track B (C1) Bound Gap |
|---|---|---|---|
| Uniform (18 inst) | **15.00%** | **15.00%** | **5.22%** (3× tighter) |
| Structured (21 inst) | **25.17%** | **25.17%** | **5.02%** (5× tighter) |

Two conclusions:
1. **The continuous (C3) dual bound matches the continuous LP bound to the decimal place.**
   This empirically validates linear programming duality: dualizing the budget constraint
   under continuous relaxation yields the identical dual space as the full LP relaxation.
2. **The (C1) relaxation is strictly superior as a dual bounding tool.** By keeping the
   discrete 0/1 knapsack subproblem per profile, the (C1) relaxation captures integer
   step-functions that both the LP and continuous (C3) relaxation miss, delivering a
   3–5× tighter bound at the expense of DP runtime.


---

## F22 — Extending the budget sweep above reference clears the cliff edge

Built into `poc/harness/runner.py`. Owner: 089.

Answers the T3 defect noted in F15. Sweeping budget tightness into values above reference
(e.g., 1.25× and 1.5× B_ref) confirms that solvability reaches 100% and heuristics achieve
robust feasibility without the knife-edge artifact at 1.0×. It enables evaluating
unbiased asymptotic gap percentages for Chapter 3.


---

## F23 - The closed loop runs, and it abandons good profiles it can never win back

**Outside PoC scope.** The first end-to-end run of the system as a system: J1 ingest ->
J2 resolve -> J3 allocate -> J4 persist -> J5/J6 simulated execution -> J7 profile ->
J8 drift -> J9 global re-optimisation -> back to J3.

Run on the **real batch** - `data/eval_batches/eval_batch_3workflows.json`, three
incident-detection workflows over multi-host Zookeeper logs, twelve tasks. Execution is
simulated (see `prototype/simulator.py`); the profiles have a **hidden true** reliability
that differs from what the registry declares, so the loop must measure its way to reality
rather than being handed it.

### What works

**It does not thrash.** The feedback path - signal, re-allocate, execute differently,
signal again - is the obvious instability, and it does not fire. Typical runs re-allocate
once or twice in twenty-five rounds and then hold.

**It converges.** Measured reliability on profiles that keep receiving traffic climbs toward
the hidden truth (0.938 -> 0.986 against a true 0.995 over twelve rounds).

**Genuine degradation is caught.** Dropping a profile's true reliability from 0.99 to 0.40
mid-run causes the loop to route away from it and accept a costlier plan. Sensitivity is
real.

### What does not work, and it is structural

**In 8 of 10 seeded runs the system permanently abandoned a profile that met its floor.**

The cheap profiles have true reliability **0.93** against a floor of **0.90**. They are
acceptable. They are also cheap - the whole allocation costs 400 with them and 560-720
without.

| seed | final cost | abandoned | re-allocations | final measured |
|---|---|---|---|---|
| 0 | 720 | yes | 2 | 0.950 |
| 1 | 560 | yes | 1 | 0.861 |
| 3 | **400** | **no** | 0 | 0.939 |
| 4 | 560 | yes | 1 | 0.694 |
| 5 | **400** | **no** | 0 | 0.942 |
| 8 | 720 | yes | 2 | 0.860 |

An early unlucky failure pushes the measured estimate below the floor. The profile drops out
of `C(t)`. The allocation moves to the expensive alternative. **And then the estimate
freezes** - at 0.861, or 0.694 - because a profile that is not routed to receives no
observations, forever.

Cost rises 40-80% permanently, on the evidence of one or two failures, for a profile that
was fine.

### Why no component test could have found this

Every part behaves correctly in isolation. The estimator is sound (F19 fixed it). The floor
filter is doing exactly what §1.6 specifies. The drift detector fires appropriately. The
allocator picks the cheapest feasible option.

The failure is in the **composition**: measurement drives eligibility, eligibility drives
routing, and routing drives measurement. Once a profile leaves that cycle it cannot re-enter
it. Nothing in §4.5, §4.2 or §3.3 mentions this, because each section is correct about its
own component.

### What it is, and what it means for Semester 2

This is the **explore/exploit problem**, and the architecture currently has no position on
it. Principle P6 says profiles are measured, not declared - but a system that only measures
what it already chose will converge to whatever it happened to try first.

Three directions, none of them implemented here:

  * **Confidence-aware floors** - filter `C(t)` on a confidence bound rather than a point
    estimate, so a profile with few observations is not excluded on thin evidence. Fits the
    existing formulation with no new machinery. **Corrected in F25: it must be the UPPER
    bound, not the lower one as originally written here.** A lower bound is low when
    evidence is thin and would make abandonment worse. Implemented and measured in F25 - it
    removes the whole cost penalty.
  * **Occasional exploration** - route a small fraction of tasks to unused profiles.
    Standard, but it deliberately spends money and needs a budget argument.
  * **Estimate decay toward the prior** - let an unobserved profile's estimate drift back
    toward its declared value so it is eventually retried. Cheapest to build, weakest
    theoretically.

**This is a design gap, not a bug, and it is a good one to have found.** It is a named
problem with a large literature, it is squarely in the profile-guided half of the project
where the novelty lives, and it is exactly the kind of thing §5.0 argues should surface
before someone spends a semester on it.

**For the proposal:** this strengthens the narrative rather than weakening it. "We built the
loop, ran it, and found that naive measurement-driven eligibility is self-reinforcing" is a
result. Adding an exploration policy is then a concrete, defensible Semester 2 contribution.


---

## F24 - The differentiator, measured: a static system fails its floors without noticing

**This is the result the advisor asked for.** His guidance on O10 was that the goal is not to
maximise reliability but to *"keep the reliability the same as much as possible as not using
this system, or using Murakkab"*, and to *"maximise the thing that would make us stand out"*.
Those are the same claim, and this measures it.

Setup: the real Zookeeper batch, 12 tasks. Floors at 0.95. Declared reliability equals true
reliability at the start, so **both systems begin correct** - this is not a strawman where
the baseline starts wrong. At round 6 every cheap profile's true reliability drops from 0.99
to 0.55. Same seed, same drift schedule, so both conditions experience an identical world.
8 seeds.

| round | STATIC delivered | STATIC cost | ADAPTIVE delivered | ADAPTIVE cost |
|---|---|---|---|---|
| 5 | 1.000 | 400 | 1.000 | 460 |
| **6** | **0.552** | 400 | **0.594** | 900 |
| 7 | 0.583 | 400 | 0.865 | 900 |
| 9 | 0.625 | 400 | 0.990 | 1020 |
| 13 | 0.438 | 400 | 1.000 | 1040 |
| 17 | 0.521 | 400 | 0.979 | 1040 |

**Post-drift: STATIC delivers 0.542 at cost 400. ADAPTIVE delivers 0.938 at cost 1013.**

### The point is not the cost, it is the not-noticing

A static allocator does not become wrong when reality drifts. It becomes wrong **without
finding out**. Through rounds 6-17 the static system reports the same plan, the same cost,
and a satisfied 0.95 reliability floor, while actually delivering 0.54. Every number it could
show you is unchanged. Nothing in it is capable of detecting the failure, because it has no
measurement path.

That is the honest form of the project's claim, and it is stronger than a cost claim:

> A static system cannot report reliability it does not measure. Ours holds delivered
> reliability under drift because it measures, detects, and re-routes - and the cost of doing
> so is visible rather than hidden.

### The cost comparison is not apples to apples, and should not be presented as one

ADAPTIVE costs 2.5x more post-drift. That is real and must be reported. But the two systems
are not delivering the same thing: **STATIC is not meeting its requirement at all.** Its 0.95
floor is violated on every round after drift. Comparing 400 against 1013 as though both are
valid allocations would be dishonest - the correct statement is that STATIC's cheaper plan is
cheaper *because it has silently stopped working*.

### What it also exposes about our own system

ADAPTIVE's cost creeps from 400 to 460 in rounds 0-5, **before any drift at all**. That is
F23's premature abandonment showing up as money: unlucky early failures push a good profile
below its floor and the system pays to move off it for no reason.

So this experiment prices F23. The confidence-bound fix is no longer just a correctness
argument - it is worth roughly 15% of the pre-drift bill.

### Limitations

- **Simulated execution.** The loop logic is tested; no real executor is involved.
- **The drift is dramatic** - 0.99 to 0.55. A subtler drift would be a harder test and has
  not been run.
- **8 seeds**, no confidence intervals.
- Floors are set by hand. Under the O10 answer they should be anchored to baseline-delivered
  reliability (see the Section 1.3 note below), which would change the numbers.

### Consequence for the documents

Section 1 does **not** change: C1, C2, C3 and the objective all stand, and Section 1.9's
"reliability is a floor only" is confirmed by the advisor.

Two things around it do:

- **Section 1.3** - `R_min(t)` has never been defined anywhere, it is simply listed as an
  input. Under the O10 answer it acquires one: *the reliability the baseline would deliver
  for that task*. Set that way, the existing program enforces exactly what the advisor asked
  for. Set arbitrarily low, the optimiser will legally trade reliability away for cost -
  demonstrated: two profiles both passing a 0.90 floor, the optimiser correctly takes 0.910
  over 0.999 and saves 200.
- **Section 4.7** - the evaluation must report **delivered reliability against baseline**,
  not cost alone. On the current metric set, STATIC wins this experiment.


---

## F25 - The overpayment is real, bounded, and fixed. And my prescription was backwards.

Follow-up to F24's observation that the adaptive loop's cost creeps from 400 to 460 *before
any drift*. Three questions: is it a ratchet, how bad is it, and does the proposed fix work.

### It is not a ratchet - it plateaus, permanently degraded

No drift at all, true reliability 0.99 throughout, 8 seeds, 80 rounds. Optimal cost is 400:

| floor | margin above true | r0 | r10 | r20 | r40 | r79 |
|---|---|---|---|---|---|---|
| 0.95 | 0.04 | 400 | 480 | 500 | 500 | **500** |
| 0.90 | 0.09 | 400 | 440 | 440 | 440 | **440** |
| 0.80 | 0.19 | 400 | 400 | 400 | 400 | **400** |

It stops climbing, which is much better than feared - but it settles **25% above optimum** at
a tight margin. The damage is front-loaded: it happens while estimates are thin, then stops,
because the profiles still in use have accumulated enough observations to be stable and the
abandoned ones can no longer get worse.

**Severity is governed entirely by the margin between true reliability and the floor.** A
generous floor costs nothing; a tight one costs a quarter of the bill. That is a bad property
to have undiscovered, because the natural instinct when setting floors is to set them close
to what the profile promises.

### My prescription in F23 was backwards

F23 and the first version of `component_reference.md` both said the fix is to *"filter C(t)
on a **lower** confidence bound rather than a point estimate"*. That is wrong, and it would
have made things worse. With few observations a lower bound is *low*, so it excludes a
profile faster than the point estimate does.

The requirement is the opposite: **exclude a profile only when confident it is genuinely
below the floor.** That is the upper bound.

A profile at true reliability 0.99, after one failure in five effective observations, with a
0.95 floor:

| rule | value | verdict |
|---|---|---|
| point estimate (today) | 0.750 | exclude - **wrong** |
| lower bound (my stated fix) | 0.370 | exclude - **more wrong** |
| **upper bound** | **1.000** | **keep - correct** |

And it still excludes genuinely bad profiles once the evidence is there: at 900 successes in
1000 trials the upper bound is 0.918 and the profile is correctly dropped.

    include m in C(t)  iff  upper_bound(rel(m)) >= R_min(t)

Few observations means a wide interval means a high upper bound, so keep trying. Many
observations on a bad profile means the bound converges down, so drop it. This is optimism
under uncertainty, the standard explore/exploit rule.

### Measured: it removes all of the waste and none of the sensitivity

| | floor 0.95, no drift | floor 0.90, no drift | with real drift at round 6 |
|---|---|---|---|
| point estimate | 500 | 440 | 0.991 delivered, cost 1040 |
| **upper bound** | **400** | **400** | **0.991 delivered, cost 1040** |

**The overpayment goes to zero - the optimum is recovered exactly - and behaviour under
genuine drift is identical.** The obvious risk of optimism, that it keeps trusting a
collapsing profile because the evidence is thin, does not materialise: the bound converges
down as observations accumulate.

### Status

Implemented as an **option** (`optimistic_eligibility=True`), not as the default, because
changing how `C(t)` is built is 077's decision and it deviates from Section 1.6 as written.
Three tests pin the behaviour: that the point estimate overpays, that the upper bound
recovers the optimum, and that optimism does not blind the system to real failure.

**Recommendation:** adopt it, and amend Section 1.6 to filter on a confidence bound rather
than a point estimate once profiles are measured rather than declared. The change is one
comparison, it removes a 25% cost penalty, and it costs nothing in detection.


---

## F26 - T1's other arm, and a bigger problem: the GPU budget is nearly inert in our instances

Built `poc/tracks/track_b_budget.py`, the (C3) relaxation, so T1 is answered by measurement
rather than by assumption. It immediately exposed something more important than the question
it was built to settle.

### The arm comparison, at face value

8 tasks, 4 profiles, both generators, bound gap = distance below the true optimum:

| generator | (C1) relaxation | (C3) relaxation | LP |
|---|---|---|---|
| uniform | 3.52% in 0.79 s | **0.00% in 0.06 s** | 11.99% |
| structured | 3.13% in 0.97 s | **0.00% in 0.08 s** | 25.73% |

The (C3) arm reaches the exact optimum, in roughly one iteration, ten times faster. Taken at
face value that overturns Section 1.8's prediction and the choice made in `track_b_lagr.py`.

**It should not be taken at face value.**

### Why it is exact: there is nothing to relax

The (C3) arm converges immediately because the budget-free optimum already satisfies the
budget. Checked directly - solve each instance with the real budget and again with an
effectively infinite one:

| generator | budget | solvable | optimal cost differs | mean rise |
|---|---|---|---|---|
| uniform | 1.00x | 12 | 1 | 1.30% |
| uniform | 0.80x | 8 | **0** | 0.00% |
| structured | 1.00x | 12 | **0** | 0.00% |
| structured | 0.80x | 9 | **0** | 0.00% |

**In 40 of 41 solvable instances the GPU budget does not change the optimal cost at all.**

### The cause is in the generators, and it is my fault

```
corr(price, gpus)     uniform 0.953     structured 0.999
```

Both generators set `price = gpus x constant`. Minimising `Sum n[m]*price(m)` is therefore
almost the same objective as minimising `Sum n[m]*gpu(m)`, and a constraint on the second
cannot bind when you are already minimising the first.

Decorrelate them - price drawn independently of GPU count - and the budget starts mattering:

| budget | solvable | cost differs | mean rise |
|---|---|---|---|
| 12 | 15 | 0 | 0.00% |
| **8** | 11 | **2** | **95.01%** |
| 5 | 1 | 1 | 48.46% |

### What this invalidates, and what it does not

**Does not invalidate:** Section 1's formulation. (C3) is a correct constraint. Nor does it
touch F1, F16, F17, F24 or F25, none of which depend on the budget binding.

**Does invalidate the reading of T1's arm comparison.** The (C3) arm is exact because the
constraint it relaxes is inactive. On instances where the budget genuinely binds it would
have to search the multiplier, and each iteration is a full MILP solve, because relaxing
(C3) leaves (C1) coupling every profile through the tasks - the problem does not decompose,
exactly as Section 5.2.3 predicts. **The structural prediction stands; the numbers above do
not test it.**

**Weakens T3.** T3 asks where the budget binds. The honest answer from our instances is that
it binds on *feasibility* - whether any allocation exists - but almost never on *choice*.
That is a property of the generators, not of the problem.

### The question this raises, which is for the team and the advisor

Is `price(m)` genuinely independent of `gpu(m)`?

If you rent GPUs by the hour from one provider, price *is* proportional to GPU count, both
generators are realistic, and **(C3) is close to redundant with the objective** - which is a
real finding about the problem, not a bug. The budget then means physical capacity, not
spend.

If `price(m)` represents something else - energy, amortised hardware, mixed providers, spot
versus on-demand - then it is not proportional, the budget binds, and both generators are
unrealistic in a way that has quietly shaped every budget-related result.

**Nothing in the architecture says which.** Section 1.3 lists `price(m)` as "cost of one
instance of m over the horizon" and `B` as "total GPU budget", with no statement about
whether they are the same axis. Until that is settled, T3's binding-region result and this
arm comparison should both be treated as provisional.


---

## F27 - T3 completed: the region is 0.8x to 1.25x, and the gaps run the wrong way

D9 was defective: the sweep only ever ran *below* the reference allocation, and F15 showed
the reference is a cliff rather than a neutral upper bound. Both generators now accept
budgets up to 3x, so the sweep spans both sides.

25 seeds per point, 8 tasks, 4 profiles. Ratio is the budget as a multiple of the reference
allocation's GPU usage.

**uniform**

| ratio | solvable | A feasible | C feasible | A gap | C gap |
|---|---|---|---|---|---|
| 0.6 | 3/25 | 1 | 0 | 0.00% | - |
| 0.8 | 13/25 | 6 | 6 | 8.26% | 10.26% |
| **1.0** | 25/25 | 18 | 20 | 11.56% | 17.67% |
| 1.25 | 25/25 | 25 | 24 | 14.22% | 20.48% |
| 1.5 | 25/25 | 25 | 25 | 14.22% | 21.76% |
| 2.0 | 25/25 | 25 | 25 | 14.22% | 21.76% |

**structured**

| ratio | solvable | A feasible | C feasible | A gap | C gap |
|---|---|---|---|---|---|
| 0.6 | 1/25 | 0 | 1 | - | 0.00% |
| 0.8 | 17/25 | 8 | 9 | 11.87% | 11.05% |
| **1.0** | 25/25 | 23 | 25 | 17.43% | 27.57% |
| 1.25 | 25/25 | 24 | 25 | 17.13% | 27.57% |
| 2.0 | 25/25 | 25 | 25 | 18.88% | 27.57% |

### The answer

**The operating region is roughly 0.8x to 1.25x the reference allocation.** Below 0.8 most
instances are simply infeasible - there is nothing to compare. Above 1.25 every number
freezes: identical gaps at 1.5 and 2.0 on both generators, because the budget has stopped
constraining anything at all.

Two distinct transitions sit inside that window, and they are not the same thing:

  * **Feasibility** transitions between 0.6 and 1.0 - whether any allocation exists.
  * **Heuristic feasibility** transitions between 1.0 and 1.5 - whether the *tracks* can find
    one, which happens later than the optimum existing.

### The counter-intuitive part: gaps get WORSE as the budget loosens

Track A goes 8.26% -> 14.22% and Track C 10.26% -> 21.76% as the budget is relaxed. More
budget makes the heuristics *worse* relative to optimal.

The reason is that a tight budget does the heuristic's job for it. With few affordable
options, a greedy or rounded choice cannot stray far from the optimum because there is
nowhere to stray to. Loosen the budget and the search space opens up, and the exact solver
exploits that freedom while the heuristics do not.

That has a direct consequence for how the evaluation is read: **a heuristic evaluated only at
tight budgets will look better than it is.** T4's numbers should be quoted with the ratio
they were measured at.

### Caveat, and it is a large one

Per **F26**, the budget does not change the *optimal cost* in 40 of 41 instances, because both
generators set `price = gpus x constant`. So this sweep measures where the budget affects
**feasibility**, not where it affects **choice**. If O13 resolves to price being independent
of GPU count, this whole table needs re-running and the region may move.

**T3 is answered for the instances we have, and provisional pending O13.**


---

## F28 - T1 answered in full: three arms, three decomposition axes, one right answer

The PoC plan's T1 method asks for three relaxations - "write the Lagrangian of (3)... repeat
relaxing (2) instead, and both together". Two existed. The capacity arm did not, so T1 was
incomplete regardless of the earlier findings. It is built now.

| relaxed | decomposes into | uniform bound gap | structured bound gap |
|---|---|---|---|
| **(C1) assignment** | one knapsack **per profile** | **3.02%** | **4.63%** |
| (C2) capacity | one choice **per task** | 12.68% | 26.85% |
| (C3) budget | **does not decompose** | 0.00% * | 0.00% * |
| LP relaxation | - | 12.16% | 24.61% |

\* only because the budget does not bind on our instances - see F26. Not a real result.

### The answer to T1 as asked

**Along what axis does it decompose?** All three, differently - and that is the useful part
of the answer:

  * Relaxing **(C1)** leaves (C2) indexed by profile, so the subproblems are **per profile**.
    This is the classical facility-location decomposition and what §1.8 predicted.
  * Relaxing **(C2)** removes the only thing linking tasks to each other, so routing becomes
    **per task** and provisioning becomes a knapsack over the budget. Cleanly separable, and
    nearly worthless.
  * Relaxing **(C3)** leaves (C1) coupling every profile through the tasks. It **does not
    decompose**, and each iteration costs a full exact solve.

**None of them is per workflow**, which is what the earlier design claimed. Workflow
membership never appears in any subproblem, because no constraint is indexed by workflow.

### The (C2) arm fires §5.3's cut criterion, and that is informative

§5.3's T1 table flags one outcome to watch: *"Lagrangian bound = LP bound consistently ->
Track B provides nothing Track C does not; it should be cut or rejustified."*

For the **(C2) arm that is exactly what happens**: 12.68% against the LP's 12.16%, and 26.85%
against 24.61%. Relaxing the capacity constraint buys an easy, cleanly decomposable
subproblem and a bound no better than simply solving the LP.

The reason is structural rather than numerical. §1.7 states that (C2) is where the coupling
lives and where the integrality gap lives. Relax the one constraint that makes the problem
hard and the remainder is easy precisely because it no longer describes the problem.

**So the criterion fires for the wrong arm, which vindicates the right one.** Track B as
built - relaxing (C1) - gives 3.02% against the LP's 12.16%, and stands.

### On "both together"

`track_b_lagr.py` relaxes (C1) with multipliers and **drops** (C3) outright, which is the
limiting case of relaxing both with the budget multiplier pinned at zero. So the combined
case is covered in its weakest form. A proper two-multiplier version was not built; given
F26 shows the budget does not bind on these instances, it could not be evaluated here even
if it were.


---

## F29 - Statistics: the 110x speedup claim was mean-over-mean and does not survive

The headline result rested on 3 seeds. Re-run with 10 seeds, 95% confidence intervals, and a
45s solver limit so a pathological instance cannot distort the mean by running forever.

| generator | tasks | proven | MILP s | Track C s | **median** speedup | C gap % |
|---|---|---|---|---|---|---|
| uniform | 16 | 10/10 | 0.106 +-0.032 | 0.039 +-0.010 | 2x | 16.66 +-7.90 |
| uniform | 32 | 10/10 | 0.293 +-0.070 | 0.070 +-0.014 | 4x | 9.12 +-4.63 |
| uniform | 64 | 10/10 | 7.194 +-6.294 | 0.083 +-0.014 | 5x | 6.24 +-3.38 |
| uniform | **128** | 10/10 | **12.283 +-10.290** | **0.106 +-0.020** | **5x** | **3.03 +-1.62** |
| structured | 128 | 10/10 | 0.243 +-0.065 | 0.109 +-0.027 | 2x | 2.79 +-0.78 |

### The correction

**"~110x faster" was mean divided by mean.** 12.283 / 0.106 = 116, and that is the number
that was quoted. But the **median speedup is 5x**, and the difference between those two
numbers is the whole story: look at the interval, 12.283 **+-10.290**. The MILP's mean is
carried by a heavy tail of a few pathological instances. On a *typical* 128-task instance the
exact solver is only about five times slower than Track C.

The claim as previously written - "110x faster for under 5% cost" - is not defensible and
must not be presented. It is now in the do-not-quote table.

### What survives, and it is a better argument

**Predictability, not mean speed.** Track C at 128 tasks: **0.106 +-0.020 s**. The exact
solver: **12.283 +-10.290 s**. Track C's runtime is essentially constant and bounded; the
MILP's is wildly variable with a tail that, before a limit was imposed, ran unbounded - a
statistics run had to be killed after an hour on a single instance.

For a system that re-optimises inside a loop on every drift signal, **bounded latency matters
more than mean latency.** An allocator that usually takes 12 s and sometimes never returns
cannot be put in a control loop at all. One that always takes 0.1 s can. That is a stronger
argument than a speed ratio and it does not depend on which average you pick.

**The gap improves with scale, now with 10 seeds behind it.** 16.66% at 16 tasks down to
**3.03 +-1.62%** at 128. The amortisation mechanism proposed in F16 - rounding error spread
over more tasks - holds up under proper sampling.

**Every instance proved optimality** within 45s, 80 of 80. So no gap here is measured against
an unproven incumbent.

### The generator dependence, again

On the **structured** generator the MILP stays fast at 128 tasks (0.243s) and the median
speedup is only **2x**. The speed argument is therefore specific to instance families where
the MILP struggles - the same conclusion as F13, now with intervals. Any speed claim must
name the family it holds for.

### What this does to the project's headline

The strongest honest statement is no longer about speed:

> Track C returns an allocation within 3% of optimal at 128 tasks, in **0.106 +-0.020 s**,
> with bounded and predictable runtime. The exact solver's runtime on the same instances is
> **12.3 +-10.3 s** and, without an imposed limit, is unbounded on its worst cases.

That supports the loop argument - a control loop needs bounded latency - without resting on
an average that a careful reader will immediately question.


---

## F30 - Statistical audit of every headline claim. Two break, two hold, one holds differently.

After F29 retracted the 110x speedup as a ratio of means, the same defect was looked for
everywhere. It is systemic: of 26 findings, only 11 lines carried an interval, and several
headline numbers were built the same way.

Comparisons are re-measured as **paired per-instance differences** - same instance, both
methods - which is both the correct statistic and far more sensitive than comparing two
means. A paired interval that crosses zero means the effect is not established at all.

| claim | verdict | paired evidence |
|---|---|---|
| Track C ~110x faster than exact | **RETRACTED** (F29) | median speedup 5x; the mean was outlier-carried |
| Track B's bound 3-6x tighter than LP | **RATIO INFLATED, effect holds** | difference **12.57 pp [9.49, 15.64]**; median ratio **2.53x**, not 6x |
| Consolidation halves Track C's gap | **MISLEADING, effect is real but rare** | median improvement **0.00%**; mean 5.31% [0.56, 10.07] |
| The adaptive loop holds reliability under drift | **HOLDS STRONGLY** | **+0.424 [0.405, 0.442]**, n=20, mean = median |
| Optimistic eligibility removes the overpayment | **HOLDS STRONGLY** | saving **128 [74, 182]**; the fixed condition has **zero variance** |

### The ratio-of-means defect, three times

`mean(A) / mean(B)` is not a typical ratio when either distribution has a tail. It appeared
in three separate claims:

| claim | ratio of means | median per-instance ratio |
|---|---|---|
| Track C vs exact solver, speed | 116x | **5x** |
| Lagrangian vs LP bound, uniform | 7.51x | **2.53x** |
| Lagrangian vs LP bound, structured | 3.80x | **2.00x** |

**The rule going forward: never divide two means.** Compute the ratio per instance and report
its median, or better, report the paired difference and its interval - which is what actually
establishes the effect.

### The one that changed character rather than size

Consolidation's **median** paired improvement is **0.00% on both generators**. On a typical
instance it does nothing. Its mean improvement is real - the interval excludes zero - but it
is carried by a minority of instances where it helps enormously, of which F17's 100.85% case
is the extreme.

So the honest description is **"fixes a rare, severe failure mode"** rather than "halves the
gap". That is arguably a *better* reason to keep it: a tail fix that costs nothing is worth
having precisely because the tail is what embarrasses you.

### The two that got stronger under audit

**The differentiator (F24)** is the most solid result in the project. Paired difference
**+0.424 [0.405, 0.442]** over 20 seeds, with mean and median identical - no skew, a tight
interval, and an effect roughly twenty times the interval's half-width. It is also the claim
the project most needs to be true.

**The overpayment fix (F25)** is stronger than first reported. With 20 seeds the point-estimate
condition costs a median of **560** against the optimum of 400 - a 40% overpayment, not the
25% measured with 8 seeds - and the upper-bound condition returns **400.0 with zero variance**,
hitting the optimum on every single seed.

### What this changes about how results should be reported

1. **Paired differences with intervals, not means side by side.**
2. **Never a ratio of means.** Median of per-instance ratios, if a ratio is needed at all.
3. **Report the median alongside the mean.** Where they diverge, the mean is describing a
   tail rather than a typical case, and that difference is usually the interesting part.
4. **State n.** Three of the corrections in this project trace to 3-8 seed samples.

---

## F31 - O13 answered from Murakkab's own numbers: price is NOT a multiple of GPU count

**Trigger.** The advisor's guidance on O13 was to look at the actual thing we allocate on, and
that since the deployment target (local vs GCP) is undecided, we should take Murakkab as the
base. So the question becomes: what does Murakkab itself assume? It is answerable from the
results already recorded in `docs/research_papers/papers.json`, without asking anyone.

### The test

Murakkab reports GPU count, energy and dollar cost as three separate quantities on the same
matched workload. If price were a fixed multiple of GPU count - our generators' assumption -
those three would move by identical factors between configurations. They do not.

| workload | config | GPUs | MWh | $k | **$k per GPU** |
|---|---|---|---|---|---|
| Video-QA + CodeGen | static baseline | 2560 | 80.4 | 201.5 | **78.7** |
| Video-QA + CodeGen | Murakkab-Opt | 1151 | 27.1 | 56.2 | **48.8** |
| Video-QA + CodeGen | Opt + multiplexed | 908 | 21.6 | 46.5 | **51.2** |
| Math-QA + CodeGen | static baseline | 4448 | 169.9 | 367.2 | **82.6** |
| Math-QA + CodeGen | best | 1660 | 52.7 | 104.6 | **63.0** |

Within one workload, moving from the static baseline to the optimised configuration:

* Video-QA + CodeGen: GPUs fall **2.82x**, energy **3.72x**, cost **4.33x**. Cost per GPU
  moves to **0.65x** of its starting value.
* Math-QA + CodeGen: GPUs fall **2.68x**, energy **3.23x**, cost **3.51x**. Cost per GPU
  moves to **0.76x**.

**Three different factors on the same workload. Price is not proportional to GPU count.**

### Why, and why it is the point of their paper

Murakkab runs a heterogeneous fleet - A100, H100 and CPU - and its optimizer explicitly trades
A100s for H100s as H100 capacity appears, in order to minimise energy. That move is only
worth making if price and energy per GPU differ **by hardware type**. The variation in $/GPU
is not noise around a constant; it is where their reported gains come from.

### What this says about our instances

Both our generators have corr(price, gpus) ~ 0.95-1.0. That encodes a **homogeneous fleet**:
every GPU costs the same, so the GPU budget and the cost objective are nearly the same axis.
It is a coherent assumption, but it is not Murakkab's, and it contradicts our own premise -
this project's whole point is routing across *heterogeneous* profiles.

**So F26's headline needs restating.** "The GPU budget is nearly inert" is a property of our
generators, not of the problem. Under a Murakkab-style price/GPU spread, (C3) is a genuinely
separate constraint and can bind where the objective does not.

### What this changes, and what it does not

| | |
|---|---|
| **O13** | **Answered on Murakkab's basis: price and GPU count are separate axes.** Which exact basis applies to *our* deployment still depends on local vs GCP, which is undecided - but that decision is between two options that are *both* unlike our generators |
| F26 (budget nearly inert) | Still correct **about our instances**. Withdrawn as a claim about the problem |
| T3's operating region | Still provisional - but now for a stated reason, not an open question |
| T1's arm comparison | Same. The (C3) arms were compared on instances where (C3) barely binds, which is the weakest possible test of them |
| Everything not involving the budget | Unaffected. T2, the bound comparison, the closed loop and the differentiator do not depend on price/GPU correlation |

### Honest limits of this finding

The figures are read from **our own reference database**, not from the paper's tables
directly. They should be checked against the PDF before they appear in a chapter. And a
generator with price decorrelated from GPU count is **not built** - this finding identifies
the gap, it does not close it. That build is parked for Semester 2.

**Nothing here was re-measured.** No number in any other finding changes. What changes is
the interpretation of the budget results, and it moves in the direction of our instances
being easier than reality rather than harder.



---

## What these findings do not establish

Restating §5.7, because early numbers invite over-reading:

- **Nothing about real workloads.** All instances are synthetic, from one generator whose
  distributions were chosen by hand.
- **Little at scale.** Findings F1–F12 are all 8 tasks and 4 profiles. F13 probes up to 128
  tasks and reverses the T4 conclusion, so every comparison above should be read as
  small-instance behaviour unless F13 says otherwise.
- **Nothing about which constraint Track B *should* relax.** It relaxes (C1) by assumption
  (F7). The (C3) alternative is unbuilt and unmeasured, so T1 is half-answered at best.
- **Nothing statistical.** 25 seeds per point, no confidence intervals, no significance
  testing. The head-to-head margins in F4 are tendencies, not results.
- **Two generators now, but both chosen by one author.** F12 re-ran everything on
  deliberately different structure and most findings held. That answers the sharpest form
  of the objection but not all of it: the same hand still wrote both, plus the anchor, the
  tracks and the metrics. Real workload data remains the only full answer, and it is out of
  PoC scope by §5.1.
- **Nothing about drift, execution, or the domain.** Out of PoC scope entirely.

No statement of the form "our approach reduces cost by X%" is supported by any of this.

---

## Decisions taken, 2 September 2026

All seven were answered in one pass. Recorded here with what was built as a result.

| # | Decision | Answer | Built |
|---|---|---|---|
| 1 | F2 anchor change | **Accepted** | §6.4 amended in `System_Architecture_v2.md` |
| 2 | The M1 analogue | **Build it, as a separate condition** | `tracks/track_a_m1.py`, condition `A+M1`. Plain Track A untouched, so T4 prices the machinery instead of assuming it |
| 3 | Which constraint Track B relaxes | **(C1), per §1.8's prediction** | `tracks/track_b_lagr.py`. Flagged in-module as an assumption, not a finding — see F7 |
| 4 | Reword O6 | **Done** | O6 now points at the repair pass, per F6 |
| 5 | Attempt parity | **Equalise, report the variant separately** | `C` is single-shot like `A`; `C2` carries the extra realisation order as its own row |
| 6 | O1, per-invocation cost term | **Closed: no** | Provisioning cost only. `ProfileSpec` has no `varcost` field |
| 7 | The STATIC baseline | **Build no-optimisation; Murakkab is not separate** | `tracks/static_baseline.py`. See the note below |

### On the Murakkab condition

The instruction was to build both a Murakkab baseline and a no-optimisation baseline. Only
one of those is a distinct thing to build.

Per §9's reference map, what this project takes from Murakkab is the capacity model and the
MILP baseline, and the formulation in §1 **is** Murakkab's model. So §4.7's own requirement
— "re-run Murakkab under matched conditions" — is satisfied by running `exact_milp`.
Registering a second condition that calls the same solver would print the same number twice
and imply an independent comparison that does not exist.

`MURAKKAB` is therefore listed in the harness's `UNAVAILABLE` map with that reasoning
attached, so anyone asking for it gets the explanation rather than silence.

**If the team means something narrower** — Murakkab's own published heuristic rather than
its exact solve — that is a genuinely different condition, and specifying it needs the
paper open. Flagging it rather than guessing.

---

## F32 - The fourth ratio of means, and a summary that contradicts its own tables

F29 and F30 audited `main`'s headline numbers and found the ratio-of-means defect systemic.
They could not have caught F20: it arrived from `mickie` in the step-1 merge, *after* the
audit. Swept for it on 4 Sep during PLAN step 3 and found it carrying the identical defect.

**The claim.** "Subset consolidation slashed the average cost gap from 32.37% down to 1.57%
- a twenty-fold improvement in solution quality" (M1 slides, speaker script for slide 8;
also PROGRESS.md as "a 20x error reduction"). That factor is 32.37 / 1.57. One mean divided
by another.

### The paired audit

Re-measured with the statistic F30 established: same instance, both conditions, paired
per-instance difference with a percentile bootstrap interval. `scripts/audit_f20_subset.py`,
scales (8,4) (16,6) (32,8) (64,10), seeds 0-9, budget x1.25 - the design
`scripts/generate_chapter3_tables.py` already used, with the seeds doubled from 5 to 10.

| | structured | uniform |
|---|---|---|
| paired instances (both feasible, MILP proved) | 32 of 40 | 40 of 40 |
| A mean gap | 19.56% | 13.81% |
| A+subset mean gap | 8.10% | 4.50% |
| **ratio of means** *(do not quote)* | **2.41x** | **3.06x** |
| **paired difference** | **11.46 pp [6.68, 17.24]** | **9.30 pp [6.69, 12.42]** |
| median difference | 7.13 pp [0.48, 12.18] | 7.07 pp [4.77, 10.67] |
| **median per-instance ratio** | **1.53x** | **1.95x** |
| better / same / worse | 21 / 11 / **0** | 33 / 7 / **0** |

**"Twenty-fold" becomes 1.53x.** And note the ratio of means on *this* instance set is 2.41x,
not 20.6x. So the ratio was not merely inflated, it was **unstable**: it moved by an order of
magnitude when the instance set changed, which is the property that makes a ratio of means
worthless as a headline. The three earlier retractions all shrank by a roughly fixed factor;
this one did not.

### What survives, and it is better than the number it replaces

**A+subset was never worse. Not on one of 72 paired instances.** Better on 54, identical on
18, worse on 0, across two generators with deliberately opposite structure. That is a
stronger statement than any fold-change, it needs no averaging argument, and it is the
statement to put on the slide.

### A second claim, refuted by the document that makes it

`docs/chapter3_benchmark_results.md` opens: "reducing mean optimality gap to **<2%** at all
scales". **Its own tables, printed below it in the same file, say otherwise** - structured
32t is 13.03% and 64t is 13.92%; uniform runs 4.51 / 3.27 / 2.20 / 4.78%. Six of its eight
cells are above 2%. Only structured 8t (0.20%) and 16t (0.22%) are below, and the claim
appears to generalise from those two.

The independent run agrees, and shows the shape the claim hides - **the gap grows with
scale**:

| scale | A+subset mean gap, structured | uniform |
|---|---|---|
| 8t | 2.35% | 4.77% |
| 16t | 4.75% | 3.02% |
| 32t | 10.89% | 4.49% |
| 64t | 14.30% | 5.74% |

Structured medians are 0.00%, 0.67%, 9.53%, 12.29%, so at small scale the mean is tail-carried
and at large scale it is not - the degradation is real, not an outlier artefact.

**This does not weaken T2's result.** A+subset still dismantles the aggregate-coupling trap,
still recovers 280 on the fixture, and is still never worse than plain greedy. What is
withdrawn is "<2% at all scales", which was never true of the measurements it was written
above.

### Rule, restated

The rule from F30 was "never divide two means". F20 shows it needs a second half: **the audit
is not a one-time pass.** Anything merged from a branch that predates it has not been
audited, whatever the finding numbers suggest. Both claims here sat in slide and chapter
material for a week after the audit that would have caught them.

---

## F33 - The budget was never inert. Our instances were homogeneous.

F26 measured that the GPU budget does not change the optimal cost in 40 of 41 instances and
concluded (C3) constrains feasibility, not choice. F31 then argued from Murakkab's published
numbers that this was an artefact: both generators set `price = gpus x constant`, so
minimising cost and minimising GPUs were nearly the same objective and the budget had almost
nothing left to decide.

F31 could only identify the problem. This builds the instrument and measures it.

### The instrument

`poc/instances/heterogeneous_generator.py`, a third generator modelling a **local, owned,
heterogeneous fleet** - the deployment target decided 4 Sep. Price is amortised capital plus
energy over the horizon, not an hourly rental rate. That distinction matters: rental is the one
regime where price genuinely is close to GPU-hours, and where the existing generators would
have been defensible.

Two mechanisms decorrelate price from GPU count, and both are things a real machine room does:

1. **Price per GPU is a property of the hardware class**, not the node size. Cost per GPU
   spans ~6x across `legacy` / `mainstream` / `frontier`.
2. **Node size is anti-correlated with class** - a few small frontier boxes, a pile of larger
   older ones. This is what actually drives the correlation to zero; without it, price still
   rises with count inside each class and the correlation survives at ~0.5-0.6.

Throughput per GPU rises with class but *not* in proportion to price, so value per GPU is
non-monotone: `legacy` is the best value and the worst choice for a latency-floored task.
Neither "prefer the cheapest" nor "prefer the biggest" is a winning rule.

| | corr(price, gpus) |
|---|---|
| `generator.py` (uniform) | **+0.959** |
| `structured_generator.py` | **+0.999** |
| `heterogeneous_generator.py` | **+0.024** |

### The measurement

`scripts/audit_budget_binding.py`. Hold tasks and profiles fixed, vary **only** B, solve to
optimality at each level. If the optimum cost moves, (C3) is changing the decision rather than
merely admitting or rejecting it. 16 tasks, 8 profiles, 25 seeds, budget multipliers 1.5 down
to 0.5 of the reference allocation.

| generator | (C3) changes the optimum | cost inflation at the tightest feasible budget |
|---|---|---|
| uniform | **4/25 (16%)** | mean 2.01%, max 2.85% |
| structured | **0/25 (0%)** | - |
| **heterogeneous** | **24/25 (96%)** | **mean 19.19%, median 15.36%, max 52.15%** |

**F26 was a finding about our generators, exactly as F31 predicted.** Change the price
structure and nothing else, and the budget goes from inert to binding in 96% of instances,
with a median 15% cost penalty for respecting it. On the old instances the budget was very
nearly a restatement of the objective; here it is a genuine second axis.

### What this closes, and what it does not

**Closes O7 - where does the budget bind?** It binds wherever price per GPU is not constant,
which on this project's own premise - routing across *heterogeneous* profiles - is the normal
case. The 40-of-41 result stands as a description of the old instances and should be quoted
that way.

**T3 now has an operating region to measure.** It could not have one before: a sweep over a
budget that does not change the answer measures nothing. That work is not done here, it is
newly *possible*.

**T1's arm comparison is still provisional.** The (C1) and (C3) relaxation arms were compared
where (C3) barely binds, and this generator is now the place to re-run that. **Not yet done** -
the instrument exists, the comparison has not been repeated on it.

**No result on the two existing generators is retracted.** They remain valid models of a
rented homogeneous fleet, and keeping all three is the point: a finding that holds on all three
is about the problem. F31's warning applies unchanged to anything measured only on the first
two.

### A note on the uniform generator's 16%

F26 reported 1 of 41; this reports 4 of 25 on the same generator. Different sizes, different
budget grid, so these are not the same experiment and the small difference is not meaningful.
The qualitative picture - the budget rarely changes anything under a per-GPU price - is
identical, and that is what the comparison rests on.

---

## F34 - T1 re-run where the budget binds: the bound advantage does not survive, and the fault is ours

F33 built the instrument F31 called for. This runs T1 on it. Two things came out, and the
first had to be fixed before the second could be measured at all.

### 1. The bounds were being thrown away

The first run returned **zero paired instances** on the heterogeneous generator. Not a weak
result - no data at all. The cause: every track discarded its dual bound whenever its
**primal** repair failed.

```python
return AllocationResult.failure(strategy, Infeasible(...), elapsed)   # bound dropped
```

A dual bound is valid whenever its relaxation solved. Whether the track's rounding or repair
then recovered a feasible allocation is a *different* question. Discarding the bound conflates
T1 ("how tight is this relaxation") with T4 ("can this track return an answer"), and the
conflation is invisible on the two per-GPU-price generators because repair almost always
succeeds there. On instances where the budget actually binds, every arm was dropped for
infeasibility and the paired set came out empty.

Fixed: `AllocationResult.failure` takes an optional `lower_bound`, passed at the four sites
where a relaxation had solved. `None` still means "no bound exists" - an empty candidate pool
fails before any relaxation runs - and there is a test for that, so `None` cannot quietly come
to mean "no bound survived". Paired instances: **0 -> 17**.

### 2. Track B's bound is not tighter than the LP's here

| generator | B (C1) vs LP, paired | tighter on |
|---|---|---|
| uniform | **+5.20 pp [4.40, 5.98]** | **25/25** |
| structured | **+13.44 pp [10.28, 16.70]** | **22/22** |
| **heterogeneous** | **-2.17 pp [-6.99, 2.13]** | **10/17** |

The interval spans zero and the point estimate is *negative*. On the two generators where
price is a fixed multiple of GPU count, Track B's advantage is overwhelming and unanimous. Where
price is decorrelated, **it is not established at all.**

### The fault is our solver, not the relaxation - and that is provable

This is not a case of "the relaxation is weaker on harder instances". By Geoffrion, the
Lagrangian dual optimum is **>= the LP bound** whenever the subproblem lacks the integrality
property, and a per-profile 0/1 knapsack lacks it. So the dual optimum *cannot* be below the LP
bound. Measuring it below therefore does not say the relaxation is weak - **it says our
multipliers are not the optimal ones.**

The suite already encodes this as an invariant, and only ever ran it on the default generator:

```
poc/tests/test_harness.py:174
    assert b.lower_bound >= c.lower_bound - 1e-6, "Lagrangian bound below LP bound"
```

**The iteration cap is not the explanation.** Raising it 16x barely moves the bound and then
plateaus:

| `ITERATION_CAP` | B bound gap | vs LP, paired |
|---|---|---|
| 75 (default) | 12.02% | -2.59 pp |
| 300 | 11.63% | -2.20 pp |
| 1200 | 11.63% | -2.20 pp |

Identical at 300 and 1200, so the method has stopped moving rather than run out of budget. That
is the signature of the **step size** collapsing - `alpha` halves after
`NON_IMPROVEMENT_PATIENCE` and floors at `MIN_STEP_SCALE`, after which further iterations are
free and useless. Track B also reports `converged=False` on **12 of 12** heterogeneous
instances against 4 of 12 uniform.

**So O5 is no longer a tuning nicety. It is load-bearing for T1** and should be reclassified.
The step-size schedule, tolerance and cap were carried as untuned defaults on the grounds that
nothing depended on them; on these instances T1's headline answer does.

### B-C3 no longer matches the LP either, and it is the same cause

The prior result was that `B-C3`'s bound equals the LP bound to ~2e-5. Two explanations were
available and indistinguishable on the old instances: the structural one (relaxing (C3) *and*
the integrality of `n[m]` leaves nothing the LP does not already have), and a non-structural
one (the dualised constraint was nearly inert, so the optimal multiplier sat at zero and
bisection found it trivially).

They make different predictions here, and the measurement separates them:

| generator | agree to 1e-6 relative | max relative difference |
|---|---|---|
| uniform | 25/25 | 1.2e-08 |
| structured | 22/22 | 1.7e-08 |
| **heterogeneous** | **14/17** | **8.5e-02** |

Where (C3) binds, mu* > 0 and the bisection has to actually locate it. It does not always
manage. **The structural claim is not refuted** - it remains the right account of why the two
*should* agree - but the pristine agreement previously reported was partly an artefact of
mu* = 0, and should not be quoted as evidence of the theory without this caveat.

### What this changes

- **Belief 3 - "the Lagrangian bound is consistently tighter than the LP" - is downgraded from
  High to generator-dependent.** The 30/30 result stands where price is a multiple of GPU
  count. It does not hold where it is not.
- **T1's answer is now conditional**, and the condition is the pricing regime. Chapter 3 should
  say so rather than quoting 30/30 unqualified.
- **O5 is promoted** from "medium, untuned defaults" to a blocker on T1.
- The (C2) arm is unaffected and remains the worst of the three everywhere: **-0.67, -0.09 and
  -3.10 pp** against the LP, tighter on 0 of 25, 0 of 22 and 0 of 17.

**What is NOT claimed:** that Track B is worse than the LP. The evidence points the other way -
theory says its dual optimum must be at least the LP bound, and we are failing to reach it.
The honest statement is that **we cannot currently compute Track B's bound well enough to
answer T1 on instances where the budget binds.** Fixing the step-size schedule is the next
step, and it may well restore the advantage.

---

## F35 - F34's headline was a confound. T1's answer stands; the incumbent is what fails.

**This corrects F34, published earlier the same day.** F34 reported that Track B's bound
advantage "does not survive" on the heterogeneous generator and downgraded belief 3 to
generator-dependent. That was wrong, and the error was mine: I pooled instances that should
have been split.

### The split F34 should have made

Partitioning the same paired instances by whether Track B recovered a feasible primal:

| generator | B found a primal | B found none |
|---|---|---|
| uniform | **+5.22 pp [4.36, 6.05]**, tighter on **24/24** | n=1 |
| structured | **+13.46 pp [10.32, 16.71]**, tighter on **22/22** | n=0 |
| heterogeneous | **+5.84 pp [3.86, 7.64]**, tighter on **7/7** | **-7.42 pp [-12.95, -2.26]**, tighter on 3/10 |

**Track B's bound is tighter than the LP's on 53 of 53 instances where it has an incumbent** -
on all three generators, including the one F34 said it failed on. The advantage is not
generator-dependent at all.

What *is* generator-dependent is how often Track B finds a primal: 24 of 25 uniform, 22 of 22
structured, **7 of 17 heterogeneous**. F34 pooled those two populations and reported the
average of a real effect and an artefact.

### Why the no-incumbent case collapses

Track B's step rule is Polyak's: `step = alpha * (UB - L(lambda)) / ||g||^2`. It aims the
multipliers at the gap between the current dual value and a known feasible cost. **With no
incumbent there is no UB and the rule has nothing to aim at.** The bound then stalls wherever
it happens to be - below the LP bound, which the dual optimum could never be, and which is why
F34 correctly concluded the multipliers were suboptimal while incorrectly concluding the
relaxation was.

So F34's diagnosis was right and its headline was wrong. The theory argument in it stands
unchanged: by Geoffrion the dual optimum is >= the LP bound, so a shortfall is always our
multipliers, never the relaxation.

### The fix that was attempted, and how much it bought

The old no-incumbent fallback substituted `best_bound + |best_bound| + 1` for the missing
upper bound. That is not an upper bound on anything - it is a number the same order of
magnitude as the bound itself, so the step was proportional to `|L(lambda)|` rather than to a
primal-dual gap. Replaced with a diminishing step on the normalised subgradient, which is the
textbook choice when no target exists, scaled by the price of one instance.

**It helped, and only marginally.** Heterogeneous paired difference moved from -2.17 to -1.96
pp; the mean bound gap from 11.09% to 10.88%. Kept, because it is correct where the old rule
was not and it costs nothing, but **it is not the answer.** The change is deliberately scoped
to the no-incumbent path so that every previously published Track B number is untouched:
uniform moved +5.20 -> +5.23 pp and structured +13.44 -> +13.46, which is bootstrap noise on
an unchanged code path.

### What would actually fix it, and why it is a decision rather than a patch

The dual does not need *its own* primal - any feasible allocation is a valid upper bound.
Track C and `A+subset` succeed on many instances where Track B's repair fails, so handing
Track B one of their solutions as an incumbent would give Polyak's rule a target and, on this
evidence, recover the advantage.

**This is not a free change, and it should not be made silently.** `track_b_lagr.py` already
warns that `warm_start=True` seeds the incumbent from plain greedy, and that any T4 statement
of the form "B beats A" must therefore be read off `warm_start=False`
(`tracks/track_b_cold.py`). Feeding B a *better* track's solution deepens exactly that
entanglement: B's bound quality would then depend on Track C's primal quality, and the two
tracks stop being independently comparable. That is 075's and 089's call, not a tuning tweak.

**O5 stays promoted** - the step schedule genuinely is load-bearing when no incumbent exists -
but the primary lever is the incumbent, not the schedule.

### What this changes back

- **Belief 3 is restored to High**, with its scope stated precisely: the Lagrangian bound is
  tighter than the LP bound wherever Track B has an incumbent, 53/53 across three generators.
- **T1's answer stands.** Relaxing (C1) is the right arm. The (C2) arm remains worst
  everywhere, tighter on 0 of 25, 0 of 22 and 0 of 17.
- **The real open problem is Track B's feasibility, not its bound** - 7 of 17 on the
  heterogeneous generator. That is a T4 question and it is now the interesting one.

### The lesson, which is the same one twice in one day

F32 found a claim that averaged over instances it should have split. F34 did it again, in the
opposite direction, and it was mine rather than inherited. **Pooling two populations with
different mechanisms produces a number that describes neither.** The check that catches it is
cheap: before reporting a pooled difference, ask what would make an instance behave
differently, and split on it.

---

## Still open

| # | Item | Owner |
|---|---|---|
| O5 | Track B's step-size schedule, tolerance, iteration cap. **No longer a tuning nicety — F34 makes it load-bearing for T1.** The cap is not the problem; the step size collapsing is the candidate | 075 |
| — | Profile Track B's knapsack subproblem in C/Cython before treating runtime as settled | 075 |
| — | Rewrite T4's decision criteria: they ask an A-vs-C question the data has moved past | 089 |
| — | Reconcile `track_a_m1.py` against Cheng & Nguyen's real M1 | 035 |
| — | Whether Murakkab's published heuristic is a separate condition | Advisor |
| O8 | Is Track A worth its complexity? Answered: plain A is not, but A+subset is competitive | 035 + 089 |

