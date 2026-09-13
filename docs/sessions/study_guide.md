# Study guide — how to be able to defend every choice

**For the presentation where every decision has to be justified.** This is not a reading
list. Reading produces recognition; questioning produces understanding, and you will be
questioned. Each step below has something to **run**, a **prediction to make before you run
it**, and the **question you will be asked**.

Work in order. Later steps assume earlier ones. Budget roughly 6–8 hours total, spread over
several sittings — it does not work as a cram.

Setup once:

```bash
python -m venv venv && venv/Scripts/activate
pip install -r requirements.txt
pytest poc/tests prototype/tests      # everything should pass
```

---

## Step 1 — The problem, before any algorithm (60 min)

**Read:** `docs/T0_briefing.md` Part 1 only. Then `poc/formulation/types.py`.

**Run:**
```python
from poc.instances.fixtures import adversarial_3t2p as fx
print(fx.__doc__)
```

**Predict before you look:** three tasks, two profiles. `m1` is cheaper per instance. Where
should each task go, and what does it cost?

**Then check** against the enumeration in the docstring. Work through why `t1` and `t2`
*together* on `m2` beats either of them alone.

**You will be asked:** *"Why is `n[m]` a decision variable rather than just derived?"*
The answer: it **is** derived — `n[m] = ceil(load/thr)`. It appears as a variable because the
solver needs it to express constraint (C2), but nothing chooses it freely. If you can say
that unprompted you understand the two-level structure.

**Also asked:** *"Which constraint couples workflows?"* → **(C2), and only C2.** Two tasks in
different workflows interact if and only if they route to the same profile.

---

## Step 2 — Why the problem is hard (45 min)

**Read:** `§1.7` of `System_Architecture_v2.md` — where the coupling lives.

**Run:**
```python
from poc.instances.fixtures import adversarial_3t2p as fx
from poc.core.provisioning import ProvisioningState
t, p, pr, b = fx.build(); by = {x.id.task_name: x for x in t}
s = ProvisioningState(pr, b)
print(s.cost_to_admit(by["t2"], "m2"))     # before anything is placed
s.admit(by["t1"], "m2")
print(s.cost_to_admit(by["t2"], "m2"))     # after t1 lands there
```

**Predict:** does the second call cost more, less, or the same?

It costs **zero** — `t1` already opened the instance and there is headroom. **That single
fact is the whole difficulty of the problem.** A task's price depends on decisions not yet
made.

**You will be asked:** *"Why can't you just sort by cost and assign greedily?"* Because the
cost isn't fixed until you know the other assignments. This is the answer to T2.

---

## Step 3 — Why an exact solver first (30 min)

**Read:** `poc/tracks/exact_milp.py`, especially `_instance_upper_bound`.

**Run:**
```bash
pytest poc/tests/test_tracks_small.py -k brute -q
```

**Understand:** the MILP is checked against independent brute-force enumeration. Nothing else
in the project can be trusted without it — every gap is measured against this.

**You will be asked:** *"How do you know your optimum is actually optimal?"* Two answers:
CBC proves it, and we cross-check against exhaustive enumeration on small instances. Also
mention the cap test — the `n[m]` bound is deliberately slack and there is a test proving it
never binds, because a cap that bound would make the solver report a wrong answer as optimal.

---

## Step 4 — The three tracks, and why each exists (90 min)

Read each in this order, and for each answer *what does this buy that the others don't?*

| track | file | buys you |
|---|---|---|
| A greedy | `track_a_greedy.py` | speed, no bound, no guarantees |
| B Lagrangian | `track_b_lagr.py` | the tightest **bound** |
| C LP + rounding | `track_c_lp.py` | speed **and** near-optimal cost at scale |

**Run:**
```python
from poc.instances.fixtures import adversarial_3t2p as fx
from poc.tracks import exact_milp, track_a_greedy, track_b_lagr, track_c_lp
a = fx.build()
for m in (exact_milp, track_a_greedy, track_b_lagr, track_c_lp):
    r = m.allocate(*a); print(f"{r.strategy:6} cost={r.total_cost:6.1f} bound={r.lower_bound}")
```

**Predict** each cost before running.

**You will be asked:** *"Why three algorithms instead of one?"* Honest answer: they were
proposed to be compared, and the comparison is T4 — which concluded Track A does not earn its
complexity and Track B is a bound generator, not an allocator. **Presenting a negative result
as a result is stronger than pretending all three survived.**

---

## Step 5 — What a bound is, and why it matters (45 min)

This is the part most likely to expose a shallow understanding, because it is easy to say
"lower bound" without meaning anything.

**Understand:** a lower bound is a proof that *no solution can be cheaper than X*. If your
heuristic returns 105 and your bound is 100, you know you are within 5% **without knowing the
optimum**. That is the entire value.

**Run:**
```bash
pytest poc/tests/test_track_b.py -q
```

**You will be asked:** *"Why does Track B matter if it is slower than the exact solver?"*
Because at scales where the exact solver is too slow, the bound is the only way to know how
good Track C's answer is. Then be honest: at the scales we measured, the exact solver was
fast enough, so this is an argument about a regime we have not reached.

---

## Step 6 — The findings that changed the design (90 min)

**Read:** `docs/poc_findings_summary.md` in full. It is 150 lines and it is the highest-value
document in the repo.

Pay attention to the **"numbers that were corrected"** table. Being able to say *"we reported
6× and it turned out to be 3–6× depending on instance structure, here is why"* is far
stronger than never having been wrong.

**Memorise the five design defects** from `D11_poc_report.md` §5 — the anchor, the EMA, the
scoping, the point-estimate filter, and the undefined `R_min`. Each is a case where
**measurement corrected the document**, which is the best evidence that the PoC was worth
doing.

**You will be asked:** *"What did you get wrong?"* Have an answer ready. The EMA one is the
best story: `§4.5` said use an EMA for profile updates, which is correct for latency and
catastrophic for reliability — 99 successes and one failure reports 0.70, and that number
filters eligibility.

---

## Step 7 — The loop, which is the actual contribution (60 min)

**Read:** `prototype/loop.py` docstring, then `docs/proposal_narrative.md`.

**Run:**
```bash
pytest prototype/tests/test_loop.py -q -k "static_fails or warm"
```

**Understand the argument chain**, because this is what the presentation should be built on:

1. Profiles are measured → they drift → allocation can't be decided once
2. On drift the **whole batch** must be re-optimised (scoping is vacuous — 84–100% of
   workflows are affected)
3. Global re-optimisation with the exact solver costs 21 s at 128 tasks
4. Track C does it in 0.16 s → **the loop is affordable**

**Therefore the algorithm work exists because the loop demands it.** The speedup is not a
headline about heuristics; it is what makes continuous re-optimisation possible.

**You will be asked:** *"What is novel here? Facility location is solved."* Correct — and say
so first, it builds credibility. The novelty is the **closed loop**: neither Murakkab nor
Cheng & Nguyen measures profiles or re-optimises on drift. Then show the F24 result.

---

## Step 8 — The limitations, said before you are asked (45 min)

**Read:** `D11_poc_report.md` §4.

Rehearse saying these **unprompted**. An examiner who has to extract a limitation from you
trusts you less than one you volunteer it to.

The four that matter:

- **Simulated execution.** No real executor. Tests the loop's logic only.
- **Two synthetic generators, one author.** The strongest objection to everything.
- **The GPU budget is nearly inert** in our instances because both generators set
  `price = gpus × constant` — so it constrains feasibility, not choice. **Say "in our
  instances", never "in the problem".** O13 is answered and it goes against us (F31):
  Murakkab's own GPU/energy/cost triples move by three different factors on one workload, so
  price is not a multiple of GPU count. Our first two generators assume a homogeneous fleet;
  this project is about heterogeneous profiles. **A third generator now fixes this** and the
  result reverses: (C3) changes the optimum in **24 of 25** instances instead of 0 of 25
  (F33). **Volunteer this one** — it is the strongest example in the project of finding our
  own measurement at fault and then building the instrument to prove it. T1's arm comparison
  has still not been re-run on it, so say so.
- **Statistics.** Know the seed count of any number you quote.

**You will be asked:** *"How do you know this generalises?"* The honest answer is that we
don't, and that a second generator with deliberately opposite structure was built specifically
to test it — most findings survived, and one number (the 6×) did not.

---

## Step 9 — Rehearse the hard questions (60 min)

Write your own answers before reading the suggested ones.

| question | where the answer lives |
|---|---|
| Why not just always use the exact solver? | It is 21 s at 128 tasks, and the loop re-solves on every drift signal |
| Why is Track C better than greedy at scale but not at 8 tasks? | Rounding error amortises over more tasks (F16) |
| Your adaptive system costs 2.5× more. Why is that good? | It isn't cheaper — the static system is failing its requirement silently. Not like-for-like |
| What happens if a profile is briefly unlucky? | It gets abandoned and never re-tested (F23). Fixed by an upper confidence bound (F25) |
| Why does the budget never seem to matter? | **It does — we were measuring it wrong.** Both original generators tied price to GPU count, so cost and GPU count were nearly the same objective. A third generator with price decorrelated reversed it: the budget changes the optimal cost in 24 of 25 instances instead of 0 of 25 (F33). **This is a strong answer — volunteer it** |
| Your Lagrangian bound is sometimes *worse* than the LP bound. Isn't that a broken relaxation? | No — theory forbids it at the dual optimum, so it proves our *multipliers* are unconverged, not the relaxation. It happens only where Track B finds no feasible incumbent and its step rule has nothing to aim at. Tighter on 53/53 where it does (F35) |
| One author wrote the generators, the tracks and the metrics. How do you know any of it? | The strongest objection there is, and we have the best answer available short of real execution: **three** generators with deliberately opposing structure. The third one **overturned one of our own headline findings**, which is the evidence the check is real and not decorative |
| What would you do differently? | Measure the methods, not just the deliverables — two gaps were found by re-reading the plan's method sections |

---

## What to do if you only have two hours

Steps 1, 2, 7 and 8. That gets you: the problem, why it is hard, what the contribution is,
and what you cannot claim. Those four cover most of what an examiner will probe, and being
solid on limitations covers you when a detail question lands somewhere you have not studied.
