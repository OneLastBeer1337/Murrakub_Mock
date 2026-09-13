# Part 4 — Improving Murakkab, From Inside Murakkab

*Ten improvements. Each is traceable to a sentence the paper already contains, expressed in A.5's
own vocabulary, and measurable against the literal baseline we built.*

---

## The organising principle

The strongest improvements here are **not new ideas**. They are:

> **Make Appendix A.5 encode what Sections 2–4 already claim.**

This matters for three reasons.

**It is comparable.** An improvement expressed in A.5's own symbols can be measured against the
literal A.5 we implemented — same profiles, same solver, same traces, one term different. An
improvement that imports a different architecture cannot.

**It is defensible.** Every change below cites a paper sentence. None of them requires arguing
that Murakkab *should* have done something; they argue that Murakkab *said* it did and the
formulation does not.

**It is bounded.** These are edits to a MILP, not a redesign. Most are a new index, a new
parameter, or a constraint the paper's prose already describes.

```
   ┌─────────────────────────────────────────────────────────────────┐
   │  WHAT THE PAPER SAYS  ──────────────►  WHAT A.5 ENCODES         │
   │        (Sections 2–4)                      (Appendix A.5)        │
   │                                                                  │
   │              └──────────── the gap ───────────┘                  │
   │                             │                                    │
   │                             ▼                                    │
   │              THIS IS WHERE THE IMPROVEMENTS LIVE                 │
   └─────────────────────────────────────────────────────────────────┘
```

---

## The ten, ranked

| # | Improvement | Traceable to | Effort | Measurable gain |
|---|---|---|---|---|
| **1** | Peak-coincidence multiplexing | §3.3.1 Decision 4 | Medium | Makes 21.6% falsifiable |
| **2** | SLO-indexed throughput `θ_{m,s}` | §3.3.1 Constraint 3 | Low | Removes a 6.8× artifact |
| **3** | Coherence constraint | A.5 has none | Trivial | Eliminates 100% incoherent mass |
| **4** | SLO filters on `x^avg` | §3.3.1's peak/avg intent | Trivial | Closes objective (13)'s hole |
| **5** | Basic-accuracy floor on latency runs | §4.3 verbatim | Low | Matches described behaviour |
| **6** | Per-node executor index | §2.2 + Dec. 2 + Table 1 | Medium | 10.8–17.9% (banded) |
| **7** | Precedence + makespan | §4.6, Listing 2 | High | 69% of latency on Video Q/A |
| **8** | Spare capacity parameter | §3.4 "spare resources" | Low | Attacks 81.5% violation rate |
| **9** | Inter-epoch switching cost | §4.7 Zone 1 | Medium | Makes churn visible |
| **10** | CPU resource type | §4.6 Figs 12b/12c | Medium | Reproduces paper's own best config |

---

## 1. Replace `μ_m` with peak-coincidence modelling

**The problem.** Finding 1: A.5's structure produces zero multiplexing gain, and the entire
reported 21.6% enters through a coefficient that is undefined, unbounded, and algebraically
indistinguishable from scaling throughput. Worse, the only way to obtain it is to fit it to the
number it is supposed to explain.

**Where the real gain actually lives.** Equation (3) sums over `x^peak` — the *peak* rate of each
workflow:

```
   A.5 charges:        Σ_w  peak(w)        ← sum of peaks
   Reality is:         peak( Σ_w w )        ← peak of the sum
```

Those differ precisely when workflows peak at *different times*. The sum-of-peaks formulation
assumes every workflow peaks simultaneously — the worst case — and therefore provisions as though
colocation buys nothing. **Which is exactly what we measured.**

Statistical multiplexing gain *is* the difference between those two quantities. It is not a
coefficient; it is a property of the arrival traces.

**The change, in A.5's vocabulary.** Replace eq. (3)'s left side:

```
   BEFORE   μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c   ≤  n_m · θ_m

   AFTER    max_over_epochs( Σ_{w,s,c} x_{w,s,c,m}(t) · t_c )  ≤  n_m · θ_m
```

**Why this is strictly inside Murakkab.** §3.3.1 already says the routing map *"encodes
cross-workflow multiplexing."* This makes that true. And Figure 19's 24-hour traces — the chat and
coding series — are already in the repository, so the coincidence structure is computable today
with no new data.

**What it buys.** Multiplexing becomes **derived from the routing the optimizer chooses**, instead
of inserted through a fitted constant. Table 2's 21.6% turns from an assertion into a prediction
you can be wrong about. That is the single most valuable change on this list.

**Caveat worth stating.** The gain may come out well below 21.6%. Chat and coding traces may be
strongly correlated, in which case peak-coincidence multiplexing is worth little — and *that*
would also be a finding, because it would mean the reported number needs a different explanation.

---

## 2. Make throughput SLO-indexed: `θ_m → θ_{m,s}`

**The problem.** §3.3.1's third constraint says capacity means *"per-instance load stays within
the throughput envelope at which the profile satisfies the latency SLO."* That makes the envelope
a function of the tier. A.5 makes `θ_m` a constant.

**Evidence this is a real loss, not a quibble.** Tables 5 and 6 report the *same*
`(model, GPU, TP)` tuple at up to four different operating points:

```
   Phi-4 / H100 / TP=1, as reported by Table 6:
      accuracy-energy-basic   TPOT 0.0373   TPS  757
      latency-energy-good     TPOT 0.0165   TPS  248
      latency-energy-fair     TPOT 0.0253   TPS  552
      latency-energy-basic    TPOT 0.0372   TPS  755

   A.5 can hold ONE of these.
```

The paper is explicit about why in A.2: the system *"increases the allowed load per model instance
to increase batching as the SLO is relaxed."* So the operating point **is** SLO-dependent, by the
paper's own account, and the appendix discards that.

On Llava-OneVision-7B/H100/TP=4 the reported throughputs span 479 → 3271 tokens/s — a **6.8×
range** from Table 5's own rows. Which point you collapse to moves every GPU count by that factor.
In our implementation this is the single largest sensitivity knob.

**The change.** Index throughput and per-token latency by SLO tier: `θ_{m,s}`, `ℓ^TPOT_{m,s}`. The
profile data already supports it — it is literally what Tables 5/6 report.

**What it buys.** Removes the largest measurement artifact in the system, and lets the optimizer
do what A.2 says it does: trade batching against latency as the SLO relaxes.

---

## 3. Add the coherence constraint

**The problem.** Finding 5: 100% of allocated mass routed a Video Q/A configuration onto Phi-4, a
model that appears in no Video Q/A configuration at all.

**The change.** One line:

```
   x_{w,s,c,m} = 0   if   model(c) ≠ model(m)
```

**Why it is inside Murakkab.** This is not adding a capability — it is enforcing something the
paper clearly assumes. Tables 5 and 6 report a Model column *per configuration*; the notion that a
configuration's accuracy could be claimed while a different model serves it is never contemplated
in the prose. The gap is an artefact of the index structure, not a design decision.

**What it buys.** Every accuracy number the optimizer reports becomes achievable. Note it will make
results *worse* on paper — the optimizer loses a cheat — and that is the point: the current numbers
are partly obtained by exploiting it.

---

## 4. Apply the SLO filters to `x^avg`

**The problem.** Equations (4) and (5) constrain `x^peak` only. `x^avg` appears in equations (2),
(6)/(10) and objective (13) — **none of which is a filter**. So objective (13), which maximises
`Σ x^avg · a_c`, may place average load on configurations whose accuracy is below the very
threshold the run is named after.

```
   x^peak  ──► filtered by eq.(4) accuracy, eq.(5) latency   ✓
   x^avg   ──► eq.(2) demand · eq.(6) cost · obj.(13) accuracy
               └─────────── NO FILTER ANYWHERE ───────────┘
```

The objective that optimises quality is the one the quality filter does not reach.

**The change.** Extend the filters to both variables, or restrict `x^avg`'s domain to the
SLO-admissible set.

**Why it is inside Murakkab.** §3.3.1's first constraint says *"only configurations whose profiled
accuracy and latency meet the SLO tier are eligible."* Eligibility is a property of the
configuration, not of which variable references it. The appendix simply wrote the filter on one of
two variables.

---

## 5. Add the basic-accuracy floor on latency runs

**The problem.** §4.3 states, verbatim: *"We guarantee a basic accuracy tier even for latency SLO
requests (e.g., 50% for video Q/A)."* A.5 gives one `τ_{w,s}` per pair and scopes eq. (4) to
`s = max_accuracy`, so on a latency-tier run there is no accuracy constraint at all.

**The change.** Give each `(w,s)` two thresholds rather than one:

```
   BEFORE   τ_{w,s}              one number, dimension depends on s
   AFTER    τ^acc_{w,s}          accuracy floor  — always active
            τ^lat_{w,s}          latency ceiling — always active
```

**Why it is inside Murakkab.** This is the improvement with the least interpretive distance of any
on the list: the paper *says* it does this. Our implementation does not, because we reproduced the
formulation rather than the described behaviour — which is faithful, and also a divergence from
the system §4.3 evaluates.

**What it buys.** The implementation starts matching the paper's described behaviour. It also
closes a real hole: without it, a latency-tier run may legally select the worst configuration in
`C_w`.

---

## 6. Per-node executor assignment

**The problem.** Three places promise per-executor model choice — §2.2 (*"may employ the same or
different LLMs"*), §3.3.1 Decision 2 (*"for each executor"*), and Table 1 (*"refined per SLO tier
by optimizer"*). `x_{w,s,c,m}` has one model index.

**The change.** Add a node index:

```
   BEFORE   x_{w,s,c,m}
   AFTER    x_{w,s,c,v,m}        v ∈ nodes(DAG_c)

   plus a consistency constraint: each node's assigned mass equals the request rate.
```

**The concrete opportunity.** Code Generation's nodes do very different work:

```
   propose_solutions   the debate — where accuracy is created   → needs the strong model
   write_tests         generating unit tests                     → middling
   rank_solutions      picking the highest-voted candidate       → a tallying job

   DeepSeek-Qwen-32B/H100/TP=4   91.61% accuracy   347.5 tokens/s per GPU
   Phi-4/H100/TP=1               67.20% accuracy   757.0 tokens/s per GPU
                                                   └─ 2.2× more efficient
```

Under A.5 you must pick one model for the entire workflow, so choosing the accuracy means the
*ranking* step also runs on the expensive model. Moving a fraction *f* of tokens to Phi-4 saves
`f × (1 − 347.5/757) = f × 0.541`:

```
   ranker is 20% of tokens   →  10.8% fewer GPUs
   ranker + tests are 33%    →  17.9% fewer GPUs
```

**The honest blocker.** That band cannot be narrowed from the paper's data, for two reasons, and
both come from the same root:

```
   DECIDES at executor granularity      PROFILES at configuration granularity
   (§3.3.1 Decision 2)                  (§3.3, Figure 2c, Table 6)
        ┌─────────┐                          ┌──────────────────────┐
        │ propose │ ← pick m                 │  whole configuration │
        │ tests   │ ← pick m                 │  a_c = 91.61 %       │
        │ rank    │ ← pick m                 │  t_c = 39,969 tokens │
        └─────────┘                          └──────────────────────┘
              ▲                                          ▲
              └──────────── MISMATCH ───────────────────┘
```

There is no published per-node token split, and no accuracy measurement for mixed assignments.
**Implement the formulation change and report the band**; closing it needs measurement, which
needs GPUs.

---

## 7. Precedence and makespan

**The problem.** Finding 2: eq. (5) models a workflow as one serialised token stream on one model.
Listing 2's Video Q/A has a genuine fan-out, and the observed span is 69% latency the formulation
cannot see.

**The change.** Replace the single-stream filter with a critical path over the DAG:

```
   BEFORE   ℓ^TTFT_m + t_c · ℓ^TPOT_m  ≤  τ

   AFTER    makespan(c, m) ≤ τ,  where
            makespan = max over paths of Σ node durations
                     = L_scene + max(L_frames, L_stt) + L_qa    (Video Q/A)
```

**Why it is inside Murakkab.** The DAG already exists — Phase 1 produces it and the registry
carries it. Nothing new is imported; the optimizer is simply allowed to read a structure the
system already has. §4.6 measures parallel execution empirically, so the capability is one the
paper demonstrates.

**Effort and honesty.** This is the largest change on the list, and it needs per-node durations,
which need a per-node token split (see #6's blocker). On Video Q/A this is tractable — there is
one LLM node, so the split is exact. On Code Generation it is not.

**This is also where your own architecture's contribution lives**, so it is worth doing carefully
rather than quickly.

---

## 8. Give spare capacity a parameter

**The problem.** Finding 3: the auto-scaler's 60-second monitoring window cannot be answered by a
20-minute provisioning delay. §3.4 says Murakkab *"maintains spare resources to absorb demand
spikes"* and never sizes them. A.5 has nowhere to put one — `B_g` is a hard budget, `α` is a demand
buffer.

**The change.** Add `σ_g` (spare fraction) as a first-class parameter, and let the optimizer size
it against the projected variance rather than treating it as a constant:

```
   eq.(7)  becomes   Σ n_m · g_m  +  spare_g  ≤  B_g
                     with spare_g sized from the token distribution's p99/p50 spread
```

**Why it is inside Murakkab.** §3.4 already motivates the auto-scaler entirely with the p50/p99
token spread (*"600 and 1200 tokens… highlighting high variance"*). The data to size spare capacity
is the data already used to justify the component.

---

## 9. Add an inter-epoch switching cost

**The problem.** A.5 has no coupling between epochs — no warm start, no switching cost, no minimum
instance lifetime. So the optimizer may legally tear down an entire fleet between two adjacent
hours at zero modelled cost. Meanwhile §4.7 builds a whole sensitivity analysis on exactly that
overhead:

> *"Zone 1 (10–60 minutes): Buffer-dominated. Frequent reoptimization induces high transition
> overhead. Excessive GPU provisioning during transitions leads to lower utilization… Frequent
> model and tool changes can also reduce KV cache efficiency."*

**The change.** Add a term penalising `|n_m(e) − n_m(e−1)|`, priced at the 20-minute provisioning
cost §4.7 already assumes.

**What it buys.** Figure 13a's three-zone structure becomes *derivable* from the formulation rather
than measured around it. Right now the optimizer cannot see the cost that defines Zone 1.

---

## 10. Add a CPU resource type

**The problem.** §4.6's *chosen* configuration — the one Murakkab selects as most efficient — runs
OmDet on GPU and Whisper on CPU. A.5's resource set `G`, budget `B_g`, cost `c_g` and constraint
(7) are GPU-only. The paper's own best answer is not expressible in the paper's own model.

**The change.** Extend `G` to include CPU, with its own `B_g`, `c_g` and a capacity relation
appropriate to CPU serving.

**Prerequisite.** This only becomes meaningful alongside profiling tools at all — currently
Whisper, OmDet, CLIP and OpenCV have no profile of any kind, so they contribute zero to every
constraint. Giving tools a profile is the enabling step, and it is also what makes #7 produce real
numbers instead of invented ones.

---

## Suggested sequence

```
   PHASE A — cheap, high signal, no new data needed
   ├── 3. coherence constraint            (one line)
   ├── 4. filters on x^avg                (one line)
   └── 5. basic-accuracy floor            (one parameter)
        └─► these three make the baseline match the described system

   PHASE B — the headline
   ├── 2. SLO-indexed θ                   (removes the 6.8× artifact first)
   └── 1. peak-coincidence multiplexing   (the falsifiability result)
        └─► do 2 before 1, or the μ measurement inherits the θ artifact

   PHASE C — the architectural contribution
   ├── tool profiling                     (enabling step)
   ├── 7. precedence + makespan
   └── 6. per-node assignment
        └─► where your own system's thesis lives

   PHASE D — runtime realism
   ├── 8. spare capacity
   ├── 9. switching cost
   └── 10. CPU resource type
```

**Do #2 before #1.** The operating-point collapse is a 6.8× lever on `θ_m`; measuring a
multiplexing gain on top of that artifact would confound the two.

**One prerequisite before any of it:** validate the reproduction against Tables 1–6 and Figures
7–14. An improvement measured against an unvalidated baseline is not measurable. That work is
scoped and not yet done, and it is the only remaining thing that could invalidate the findings
these improvements rest on.
