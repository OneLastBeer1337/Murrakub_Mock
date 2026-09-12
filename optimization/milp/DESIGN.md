# Milestone 4 — Design: the MILP Workflow Optimizer `/optimization/milp/`

**Phase:** Optimization (paper §3.3.1, "Workflow Optimizer", p.574; Appendix A.5, pp.586-587)
**Status:** design review pending — no implementation code exists or should exist yet.
**Scope:** Appendix A.5's formulation, single-workflow, **without** `μ_m`. Multiplexing is M5 and is
deliberately absent here (§11.1 says exactly how M5 slots in without a rewrite).

**Sources of truth.** [OSDI] Chaudhry et al., *OSDI '26*, pp.567-587, cited `§x.y p.NNN`;
[ARXIV] arXiv:2508.18298v2, cited `arXiv p.N`. A.5 is identical in both versions.

**Standing policy in force (Arno, 2026-09-10, `reproduce-murakkab-literally`):** where the paper is
ambiguous, unsound, or self-contradictory, **take the paper's reading and record the problem**. M4 is
where this policy is cashed in: this milestone's *output* is a set of numbers, and several of them are
expected to be wrong-looking *because the formulation is*. An M4 that produces comfortable numbers has
probably repaired something.

Conventions carried from M1-M3: **[DESIGN CHOICE]** fills a paper silence; **[OURS]** marks a step the
paper does not describe; **[INVENTED]** has no paper counterpart. Ambiguity numbering continues M3
(A34-A65); this document starts at **A66**. Open questions continue at **Q21**.

---

## 1. Plain language first — what this thing is and why

### 1.1 In one paragraph

Once an hour, the platform asks: *given the requests I expect in the next hour, which version of each
workflow should I run, on which model, on which GPU, and how many copies of each model server do I
need to start?* The MILP is the answer machine. It is handed a menu (M3's profiles: what each
configuration costs in tokens and how good its answers are; what each model-on-hardware does in
tokens/sec, seconds, watts and dollars), a demand forecast (requests per second, peak and average),
and a promise to keep (the SLO tier). It returns two things: **how much of each request stream to
route to each (configuration, model) pair**, and **how many instances of each model to run**.

### 1.2 The two things it decides, and the one thing it does not

It decides *assignment* (`x`) and *provisioning* (`n`). It does **not** decide *ordering*. There is no
notion of "task A runs before task B", no start times, no makespan. Latency is not computed by walking
the workflow; it is a single arithmetic expression — one model's time-to-first-token plus that model's
per-token time times the whole configuration's token count — used as a **yes/no filter** on candidate
assignments before optimization. §6 and §10 develop what that costs.

### 1.3 Why it is a MILP and not a simple sort

Because the provisioning variable is an integer (you cannot run 2.4 vLLM servers) while the routing
variable is continuous, and because the two are coupled: routing more load onto model `m` forces
`n_m` up through the capacity constraint, which is what the objective is paying for. Mixed integers +
linear coupling = mixed-integer linear program. A.5 (p.587) says the authors solved it "using Gurobi
with a time limit of 300 seconds"; we substitute an open-source backend (§8) and change nothing else.

### 1.4 What Milestone 4 inherits, and the one door it may use

M3 is done. Everything M4 knows about the world arrives through **one object**, `MilpInputs`, produced
by `ProfileSet.to_milp_inputs()`. `tests/test_milp_boundary.py` already enforces that
`/optimization/milp/` may import nothing else from the profile layer. That test was written before
this code existed; M4 must keep it passing rather than amend it.

Three properties of that input shape everything below:

1. **Every parameter is `Measured | Unavailable`, never a bare float.** Reading an `Unavailable`
   raises. ~14% of the set is `Unavailable`, because the paper does not report it (§4).
2. **`MilpInputs.data_excluded` (21 entries) is not optional output.** Q19 makes printing it beside
   every headline number mandatory (§9.2).
3. **`B_g` is `Unavailable` by default and that is deliberate** (A43). §4.2/4.3 state no resource
   budget, so eq. (7) is *inactive* for the headline experiments. M4 must select a budget scenario
   explicitly and may never default into one (§7.2).

---

## 2. Which equations exist, and which ten M4 implements

### 2.1 A58: thirteen numbered equations, ten distinct ones

A.5 numbers its equations (1)-(13). Three of them are restatements:

| Numbered | Status |
|---|---|
| (4) and (8) | **identical, verbatim** — the accuracy filter, stated twice |
| (5) and (9) | **identical, verbatim** — the latency filter, stated twice |
| (6) and (10) | identical **up to inlining** `Cost_budget` — the cost budget, stated twice |

So the appendix's 13 equations are **7 distinct constraints + 3 objectives = 10 distinct equations**,
and those ten are exactly what M4 implements:

| M4 implements | A.5 | Name | §  |
|---|---|---|---|
| C1 | (1) | peak demand satisfaction | 5.1 |
| C2 | (2) | average demand satisfaction | 5.1 |
| C3 | (3) | capacity | 5.2 |
| C4 | (4) ≡ (8) | accuracy SLO filter | 5.3 |
| C5 | (5) ≡ (9) | latency SLO filter | 5.3 |
| C6 | (6) ≡ (10) | cost budget | 5.4 |
| C7 | (7) | resource budget | 5.5 |
| O1 | (11) | minimize energy | 6.1 |
| O2 | (12) | minimize cost | 6.2 |
| O3 | (13) | maximize accuracy under a cost budget | 6.3 |

The duplicates are **not** silently dropped. `model.py` emits each constraint once and records
`{"eq4": "emitted", "eq8": "duplicate-of-eq4"}` in the result object, so the reproduction can be
audited against the appendix's numbering by a reader holding the PDF. A test pins the mapping (§12).

> **Q21 — transcription checkpoint before implementation.** This document states C1, C2, C6, C7 and
> O3 in the algebraic form the repo's existing citations support (`development/DESIGN.md` §8,
> `optimization/profiles/DESIGN.md` §12.2, `arrivals.py`, `profile_sets.py:100`). Before a single line
> of `model.py` is written, all ten must be re-transcribed **verbatim from p.586-587 of the PDF** into
> `optimization/milp/A5.py` as docstring constants, and this document corrected against them. The
> specific items I want eyes on: (a) whether `α` multiplies both eq. (1) and eq. (2) or only eq. (1);
> (b) whether eq. (3) has an average-rate twin (see A66 below); (c) eq. (13)'s exact accuracy
> aggregation and which of `x^peak`/`x^avg` it weights.

### 2.2 A66 [NEW FINDING] — `x^avg` may be a variable that does nothing

On the reading this document is built from, `x^avg_{w,s,c,m}` appears in **eq. (2) alone**. Capacity
(3) is written against `x^peak`; the filters (4)/(5) are written against `x^peak`; the budgets (6)/(7)
constrain `n_m` only. If that is right, then in objectives (11) and (12) — which contain no `x` term
at all — `x^avg` is **free**: any assignment satisfying eq. (2) is optimal, the variable never
influences `n_m`, and the average-rate half of the formulation is decorative. Worse, `x^avg` would be
**unfiltered by the SLO constraints**, so the average-case traffic may legally be routed to a
configuration that violates the accuracy and latency SLOs the same request stream is buying.

This is potentially the single most consequential structural finding available at M4, and it is
exactly the kind of thing Q21 exists to check before it is asserted. **Do not report A66 until the
verbatim transcription confirms it.** If confirmed, M4 still implements it as written — `x^avg` gets
created, constrained by eq. (2) only, and the result object reports "fraction of `x^avg` mass on
(c,m) pairs that fail filter (4)/(5)" as a measured number (§9.3). If eq. (3) does have an average
twin, A66 collapses and this paragraph is deleted.

### 2.3 A67 [NEW FINDING] — `Cost_budget` is a parameter A.5 never declares

Eq. (6)/(10) constrains cost against `Cost_budget`, and objective (13) maximizes accuracy *subject to
that budget*. But `Cost_budget` is **not in A.5's parameter list**, is reported in no table, and is
consequently **not in `MilpInputs`** (whose 13 fields are pinned by
`test_a5_parameter_list_is_pinned`). So objective (13) — one of the paper's three headline objectives
— cannot be instantiated from the paper's own data.

Handling, per the standing policy: `Cost_budget` is **not** invented into the profile layer (that
would breach M3's 0%-invented guarantee and the pinned parameter list). It becomes an **experiment
coordinate**, exactly as `B_g` already is (A43) — supplied to `solve()` by the caller, defaulting to
nothing, with the same "you must choose deliberately" ergonomics (§7.2). `scenarios.py` ships a
`cost_budget_scenarios()` helper whose entries are **relative** (e.g. `1.0x`, `1.25x`, `1.5x` of the
min-cost solution from O2), so no absolute dollar figure is fabricated and the sweep is
self-calibrating. That relative construction is **[OURS]** and labelled as such.

---

## 3. Sets and index spaces

A.5's sets, and what each is in this reproduction:

| Set | A.5 | Our realization | Size |
|---|---|---|---|
| `W` | workflows | `{code_generation}` **or** `{video_qa}` — M4 is single-workflow (§3.1) | 1 |
| `S` | SLO types | `(type, tier)` pairs: `{accuracy, latency} × {best, good, fair, basic}` | 8 |
| `M` | model profiles | `ModelProfileKey(model_id, gpu, tp)` | 20 |
| `C_w` | workflow configs | `ConfigKey` from `MilpInputs.configs_by_workflow[w]` | 20 / 24 |
| `G` | resource types | `{A100, H100}` | 2 |

### 3.1 "Single-workflow" means `|W| = 1`, chosen explicitly

`MilpInputs` carries **both** workflows (44 configurations). M4's entry point takes `workflow: str` as
a required argument and restricts `W` to it; there is no "all workflows" default, because an
unintended two-workflow solve at M4 would silently pre-empt M5's multiplexing experiment and make the
Table 2 comparison meaningless. §4.2 (p.576) is itself single-workflow ("all requests have the same
SLO for each experiment"), so this matches the paper's own headline setup. The formulation is written
with the `w` index intact throughout, so M5 widens `W` by passing a list — no rewrite.

### 3.2 `S` and a dimensional problem in the filters (A68 [NEW])

`S` is one set, and `τ_{w,s}` is **one number per `(w,s)`**. But eq. (4) compares `τ_{w,s}` against an
accuracy (a fraction) and eq. (5) compares the *same* `τ_{w,s}` against a latency (seconds). Under the
literal reading, for `s = (latency, good)` the accuracy filter tests `a_c ≥ 1.34 s`, which is not a
comparison at all.

M3 already resolved the representation side by keying `tau` as `(workflow, type, tier)`, which is the
charitable reading. M4 takes the consequence: **for each `s`, the filter whose dimension matches `s`'s
type applies; the other has no threshold in `τ` and is therefore inactive.** So an accuracy-tier run
filters on accuracy only, and a latency-tier run filters on latency only. This is a
**[DESIGN CHOICE]** forced by dimensional analysis, recorded as **A68**, and it is *not* neutral: it
means a latency-SLO run places **no floor on answer quality whatsoever** — the optimizer is free to
pick the cheapest, worst configuration in `C_w`. That is a reportable property of the formulation, and
`report.py` prints the accuracy of the chosen configuration on every latency run so the reader sees it.

The alternative (each `s` carries both thresholds, i.e. `S` has 8 members each with an accuracy *and*
a latency bound) is a repair — it invents 8 thresholds the paper does not print — and is rejected.

### 3.3 The epoch index the formulation does not have (A69 [NEW])

`λ^peak_{w,s}` and `λ^avg_{w,s}` have no time index in A.5. But §3.4 (p.575) runs the optimizer "every
60 minutes", and `MilpInputs.lam_peak` is keyed `(w, type, tier, epoch)` over 24 hourly epochs.

**[OURS]** M4 solves **one independent MILP per epoch**, with no state carried between epochs — no
warm start, no switching cost, no minimum-instance-lifetime term. That is the faithful reading (A.5
has no inter-epoch coupling of any kind), and it means our reproduction, like the paper's optimizer,
will happily tear down and rebuild an entire fleet between two adjacent hours. Recorded as **A69**;
`report.py` computes the total instance churn across the 24 epochs so the magnitude of that
free-teardown assumption is a measured number rather than a remark.

### 3.4 Units — the one place a silent bug would be fatal

`λ` is req/**min** (Figure 19's axis); `θ_m` is tokens/**s**; `t_c` is tokens/request; `ℓ` is seconds;
`e_m` is kWh/GPU-**hour**; `c_g` is $/GPU-**second**. Eq. (3) is a rate inequality and eq. (11)/(12)
integrate over an epoch.

**Rule:** `sets.py` converts everything to **SI-per-second at the boundary, once**, and every
converted quantity is carried in a `Quantity(value, unit)` wrapper whose arithmetic checks units. A
test asserts eq. (3)'s two sides reduce to `tokens/s` and that (11)/(12) reduce to `kWh` and `$` over
one 60-minute epoch (`OPTIMIZATION_EPOCH_MINUTES` from `sources/tables.py`). A.5 states none of this;
the conversions are **[OURS]** and enumerated in `units.py` with one line each.

---

## 4. Decision variables — and the fork that costs solver time

A.5 (verified, `development/DESIGN.md` §8):

```
n_m               ∈ Z⁺      number of instances of model profile m
x^peak_{w,s,c,m}  ∈ R⁺      peak request rate assigned to (c, m) for (w, s)
x^avg_{w,s,c,m}   ∈ R⁺      average request rate assigned to (c, m) for (w, s)
```

### 4.1 The fork: is `x` continuous or integer?

**The paper says `R⁺`, and we take it.** Both readings are defensible engineering and only one is
reproduction:

| | continuous `x` (**chosen**) | integer `x` |
|---|---|---|
| Fidelity | A.5's own declaration | a repair |
| Meaning | a request *rate* may be split fractionally across (c,m) — request 7 has no home, but rates do | requests are indivisible |
| Consequence | **a single request stream may be served by many configurations at once**, so "the chosen configuration" is a *distribution*, not a row like Table 5's | Table 5-like single choice |
| Solver cost | ~20 integers (`n_m`) + ~3,000 continuous → an easy MIP; LP relaxation is tight | ~3,000 integers → combinatorially harder, 300 s limit becomes real |

The consequence in row 3 is a finding in itself and must be reported, not smoothed: Tables 5 and 6
present **one** `(model, GPU, TP, knobs)` row per (workflow, SLO tier), as if the optimizer chose a
single configuration. The formulation as written need not do that, and with a continuous `x` it
typically will not — it will blend. `report.py` therefore prints the full assignment distribution and
its **support size** (how many (c,m) pairs carry non-zero mass) next to any Table-5-style summary row,
and flags `support > 1` explicitly. If the optimum always lands on a single pair, that is an empirical
observation worth having; if it does not, Tables 5/6 are reporting an argmax over a distribution
without saying so. Logged as **A70 [NEW]**.

### 4.2 Variable creation is where the filters live

Eqs. (4) and (5) are stated as *assignments* (`x = 0 if …`), not inequalities. M4 implements them by
**not creating the variable** (§5.3). So the real index space of `x` is the *admissible* set
`{(w,s,c,m) : c is SLO-admissible on m for (w,s), and all required data is available}`, computed in
`sets.py` before any variable exists. Consequences: the model is smaller and faster, there is no big-M
and therefore no big-M numerical fragility, and — the point — **the set of things excluded is a data
structure**, printable with a reason per exclusion (§9.2).

### 4.3 `n_m` bounds

`n_m ∈ Z⁺` with no upper bound in A.5 except via eq. (7). Under objectives (11)/(12), which minimize
in `n_m`, the absence of an upper bound is harmless — the optimum is pushed down, and eq. (3) pushes
up. Under objective (13) it is *not* harmless, and the cost budget (6) is the only thing containing
it, which is why A67 matters. `solve.py` asserts, per objective, that at least one constraint bounds
`n_m` in the direction the objective pulls, and refuses to solve otherwise. That assertion is
**[OURS]** and is a guard against an unbounded-looking-but-plausible answer, not a change to the
formulation.

---

## 5. The seven distinct constraints

Each is given first in plain words, then in symbols, then with what it does *not* capture.

### 5.1 C1/C2 — demand satisfaction, eqs. (1) and (2)

> *Every request that arrives must be assigned somewhere, with a safety buffer.*

```
Σ_{c ∈ C_w} Σ_{m ∈ M}  x^peak_{w,s,c,m}  ≥  α · λ^peak_{w,s}      ∀ w ∈ W, s ∈ S      (1)
Σ_{c ∈ C_w} Σ_{m ∈ M}  x^avg_{w,s,c,m}   ≥  α · λ^avg_{w,s}       ∀ w ∈ W, s ∈ S      (2)
```

`α = 1.15`, "unified buffer factor", A.5 p.586 (`PAPER_TABLE` strength, zero band). Subject to Q21(a).

Not captured: nothing forces `x^peak ≥ x^avg` pairwise, or any relation between the two families at
all — see A66. Also, demand is a `≥`, so over-assignment is free; only the objective discourages it.

### 5.2 C3 — capacity, eq. (3). **This is Arno's critique-a constraint.**

> *The token demand placed on a model must not exceed what its instances can generate.*

```
Σ_{w,s,c}  x^peak_{w,s,c,m} · t_c   ≤   n_m · θ_m        ∀ m ∈ M                      (3)
```

*(A.5 writes `μ_m ·` on the left. **M4 omits `μ_m` — it is M5.** `model.py` emits the left-hand side
through a function `_capacity_lhs(m)` whose only M5 change is a scalar multiplier; §11.1.)*

**What it does capture.** Instance counts are present and integral, and the units are honest: rate ×
tokens-per-request ≤ instances × tokens-per-second. `CLAUDE.md`'s phrase "per-task slot consumption"
does not literally fit eq. (3), and this document will not pretend it does —
`development/DESIGN.md` §8.3 already corrected that framing and M4 inherits the correction.

**What it does not capture, precisely.** `t_c` is the token count of the **entire workflow
configuration**. A `D=4, R=4` debate — sixteen LLM invocations, plus test-writing, plus ranking — is
distinguished from a single LLM call **only by the magnitude of `t_c`**. There is:

- **no call count** — the formulation cannot tell one 16,000-token call from sixteen 1,000-token calls,
  though they queue, batch and occupy memory completely differently;
- **no per-node term** — the DAG's nodes are not in the index set at all (M1's finding);
- **no concurrency or queueing** — eq. (3) is a *mean-rate* inequality. It permits a solution in which
  every request arrives simultaneously and each still meets the latency filter, because the filter uses
  a load-independent `ℓ^TPOT_m` (§5.3);
- **no state** — no KV-cache footprint, no memory bound, no per-instance concurrency limit. A model
  instance is a scalar token faucet;
- **no tools** — 11 of the library's 26 executors are `TOOL` and consume exactly zero capacity
  (M3 §12.3). Every `n_m` M4 produces is therefore a **lower bound** on the paper's own deployment.

The comparison against Arno's instance-based provisioning model is not made here and no term is added.
What M4 does is **record the inputs that make the comparison computable later** (§10).

### 5.3 C4/C5 — the SLO filters, eqs. (4)≡(8) and (5)≡(9)

> *Do not route a request to a (configuration, model) pair that cannot meet its promise.*

```
x^peak_{w,s,c,m} = 0     if   a_c  <  τ_{w,s}                          (accuracy)     (4) ≡ (8)
x^peak_{w,s,c,m} = 0     if   ℓ^TTFT_m + t_c · ℓ^TPOT_m  >  τ_{w,s}    (latency)      (5) ≡ (9)
```

Implemented as domain restriction (§4.2). Per A68, each applies only on `s` of matching type.

Read eq. (5) carefully, because it is where the paper's model of latency lives entirely: it is **one
model's TTFT plus that model's per-token time times the whole configuration's tokens**. It does not
sum over tasks. It does not max over branches. It has no critical path. End-to-end latency is modelled
as *a single serialized token-generation stream on one model, as though the workflow were one long
generation*. Tool wall-clock is structurally unrepresentable in it (a tool has no `ℓ`), and so is any
parallelism. Two further inherited defects apply *inside* this one expression: it is a sum of p90s
standing in for the p90 of a sum (M3 §6.2), and `ℓ^TPOT_m` is load-independent though Figure 3 plots
it hooking vertically at saturation (M3 §6.3).

**A37: this constraint is expected to be infeasible for the paper's own chosen configuration.** Table
5's latency-`Best` row is Llava-OneVision-7B at `TPOT = 0.0044 s`; eq. (5) evaluates to ≈2.0 s against
Figure 7b's printed `Best ≤0.5 s`. **M4 must not resolve this by loosening `τ`.** See §7.3 for how it
is detected and reported, and §7.4 for how it is distinguished from a bug in our code.

**A62: eq. (5) is unevaluable for Llava-OneVision-7B** — no TTFT is reported for it anywhere in either
version, and it is the model §4.6's parallelism study runs. It is excluded by §4 (missing data), not
by merit, and that exclusion is printed. The paper demonstrates co-scheduling on a model its own
optimizer could not have screened.

### 5.4 C6 — cost budget, eq. (6)≡(10)

```
Σ_{w,s,c,m}  x^avg_{w,s,c,m} · (t_c / θ_m) · g_m · c_{g(m)}   ≤   Cost_budget         (6) ≡ (10)

where   Cost_budget = Σ_{w∈W} τ_{w,cost} · Σ_s λ^avg_{w,s}
```

**CORRECTED 2026-09-12 against `A5_VERBATIM.md`.** This section previously wrote C6 as
`Σ_m n_m g_m c_g` — objective (12)'s expression. That was wrong. Eq. (6) charges **`x^avg`**, not
`n_m`, and carries a `t_c/θ_m` factor. The two are different quantities and the difference is a
finding (A72):

- **eq. (12) prices PROVISIONING** — what you pay to have `n_m` instances running, whether or not
  they are busy.
- **eq. (6) prices CONSUMPTION** — `x^avg · t_c / θ_m` is GPU-seconds of *work*, times `g_m` GPUs,
  times `$/GPU-s`.

So A.5's cost *constraint* and its cost *objective* measure different things, and nothing ties them
together. A solution may sit far under the consumption budget while provisioning an arbitrarily
expensive fleet, because idle capacity costs nothing in eq. (6) and everything in eq. (12). Combined
with A66 — `x^avg` is unfiltered and never drives `n_m` — the cost budget constrains a quantity that
is nearly free to satisfy. Reproduced as printed; reported, not repaired.

**A57 reproduced:** `c_g` is named "cost per instance per second" in A.5's parameter table, yet
eq. (6), eq. (7) and objective (12) all multiply by `g_m` (GPUs per instance). Under the paper's own
algebra `c_g` is therefore **per GPU per second**, and M3 supplies it as `$/GPU-s` accordingly. M4
writes the equation as printed and the name stays wrong. Active only when a budget is supplied
(A67/Q23); on objectives (11)/(12) with no budget given, C6 is omitted and the omission is recorded
in the result.

### 5.5 C7 — resource budget, eq. (7)

```
Σ_{m ∈ M : GPU(m) = g}  n_m · g_m   ≤   B_g                          ∀ g ∈ G          (7)
```

Same A57 defect: `B_g` is named "maximum available resource *instances*" while the algebra counts
**GPUs** — consistent with §4.5's "2,000 A100 GPUs" and Table 3's "Allocated A100s". Reproduced as
printed. `B_g` handling is §7.2.

---

## 6. The three objectives, and how they are interchangeable

§3.3.1 (p.574) presents the objective as a platform-operator choice, and A.5 gives three.

```
O1  min  Σ_m  n_m · e_m · g_m                                                         (11)
O2  min  Σ_m  n_m · g_m · c_{g(m)}                                                    (12)
O3  max  Σ_{w,s,c,m}  a_c · x_{w,s,c,m}          s.t. C6 (cost budget)                (13)
```

### 6.1 O1 — energy. And what M3 already told us it degenerates to.

`e_m` is `DERIVED` per GPU **type**, not per model profile (M3 §6.5), because Figure 3's "TPS per Wh"
axis is dimensionally undefined (A41) and Table 3 pins only a per-GPU-type average. So **our `e_m`
cannot distinguish two models on the same GPU**, and objective (11) degenerates to *"minimize
GPU-hours weighted by GPU type"*. Declared at M3, inherited here, and printed in the result's
`fidelity_notes` on every energy run. This does not make (11) useless — the A100/H100 ratio is what
drives §4.2's "Murakkab prefers H100 when minimizing energy" — but it makes it blunter than the paper's.

### 6.2 O2 — cost. `c_g` is `EXTERNAL` (Q18), swept ±50% (M3 §9.3). Every cost number carries that.

### 6.3 O3 — accuracy under a cost budget. Two problems, both reported not repaired.

(a) `Cost_budget` does not exist as a paper parameter (A67, §2.3). (b) A.5 writes `x_{w,s,c,m}` here
**without a peak/avg superscript** — Q21(c). If it means `x^avg`, and if A66 holds, then O3 maximizes
an objective over a variable that no capacity constraint touches: the optimizer would assign all
average traffic to the highest-`a_c` configuration for free, and the cost budget would bind only
through `n_m`, which `x^avg` does not drive. The resulting "accuracy" would be a number about nothing.
Both readings are implemented behind `AccuracyWeighting.PEAK | AVG`, defaulting to whichever the
verbatim transcription supports, with the other available for the sensitivity report.

O3 also needs a normalization to be interpretable across runs (the raw sum scales with demand);
`report.py` additionally prints the **demand-weighted mean accuracy** `Σ a_c x / Σ x`, labelled
**[OURS]** and never substituted into the objective.

### 6.4 Interchangeability

One `Objective` enum; one `build_model(inputs, w, s, objective, budgets)` that constructs the
identical constraint set every time and attaches a different sense/expression. **The constraint set
must not vary with the objective**, except for C6, whose presence A.5 itself ties to (13) and to a
supplied budget. A test asserts that the emitted constraint list is byte-identical across the three
objectives given identical budget arguments (§12) — this is the property that makes cross-objective
comparisons (Figures 7-9's Acc./Energy vs Acc./Cost columns) meaningful.

---

## 7. Missing data, absent budgets, and infeasibility

### 7.1 `Unavailable` inputs: exclude and report, never impute

The rule, without exception: **a parameter that is `Unavailable` removes the index element that needs
it from the model, and the removal is recorded with its reason.** Never zero, never a mean, never a
neighbour's value. Zero would be actively flattering — `ℓ^TTFT_m = 0` makes filter (5) *more*
permissive, and `t_c = 0` makes a configuration free in eq. (3).

| Missing | Element removed | Coverage |
|---|---|---|
| `t_c` | all `x_{·,·,c,·}` for that `c` | 14 of 44 |
| `a_c` | all `x` for that `c` (accuracy runs; see A71) | 10 of 44 |
| `θ_m` | `m` leaves `M` entirely | some |
| `ℓ^TTFT_m` or `ℓ^TPOT_m` | `m` leaves `M` **on latency-tier runs only** | 7 of 20 TTFT |
| `e_m` | `m` leaves `M` on objective (11) only | complete |
| `c_g` | `g` — would disable O2/O3/C6; `EXTERNAL` by Q18, so not expected | complete |

**A71 [NEW] — exclusion is objective- and SLO-dependent, and that is a reporting hazard.** A model
profile with no TTFT is admissible under an accuracy SLO and inadmissible under a latency SLO; a
configuration with no `a_c` is admissible under a latency SLO (because A68 makes filter (4) inactive
there) and inadmissible under an accuracy SLO. So **the eight SLO runs of §4.2 are each solved over a
different feasible set**, and their results are not strictly comparable. Per-run `data_excluded` is
mandatory, and `report.py` refuses to emit a cross-run comparison table without an "excluded set
differs" banner when the sets are unequal.

`sets.py` returns an `Admissible` record per (w,s): the surviving index space, plus an
`ExclusionLedger` of `(element, reason, which_parameter, citation)` — the reason distinguishing
**"excluded for lack of data"** from **"excluded by SLO filter"**, which are completely different
claims and must never be summed into one number.

### 7.2 `B_g`: three honest options, one of which must be chosen out loud

`to_milp_inputs()` leaves `B_g` `Unavailable` with `blocks=("eq7",)`. M4's entry point takes a
**required** `budget: BudgetChoice` argument with no default:

| Choice | Meaning | Constraint (7) |
|---|---|---|
| `NO_BUDGET_EQ7_INACTIVE` | §4.2/4.3's headline runs — the paper states no budget | **omitted**, and the omission is recorded in `MilpResult.inactive_constraints` |
| `TABLE_3[name]` | one of the six §4.5 sweep rows via `profile_sets.budget_scenarios()` | active, `PAPER_TABLE` |
| `explicit({...})` | caller's own | active, provenance carried from the caller |

Passing nothing is a `TypeError`. Omitting eq. (7) is safe for O1/O2 (both minimize in `n_m`, so the
optimum is bounded below by eq. (3) and above by nothing it needs) but **not** for O3, where §4.3's
guard applies: `solve()` refuses O3 unless C6 or C7 is active. There is no "unbounded solve" path.

### 7.3 Infeasibility is an expected, reportable outcome

Under `baseline`, **latency-tier runs are predicted to be infeasible** — Q14 fixed `τ` to Figure 7b/8b's
printed labels, and A37 shows those labels are unreachable under eq. (5) with the paper's own Table 5
configuration. M4 must reach that conclusion and stop there. Explicitly forbidden: loosening `τ`,
swapping in `derived_tiers` and calling it the headline, dropping the `α` buffer, substituting p50
tokens, or "falling back" to the nearest feasible tier.

Infeasibility is detected in **two places**, and the distinction is the whole point:

1. **Structural (before the solver runs).** If the admissible index set for some `(w,s)` is empty,
   there is nothing to solve. `sets.py` reports `EmptyAdmissibleSet(w, s, filter_that_emptied_it,
   nearest_miss)`, where `nearest_miss` is the (c,m) pair with the smallest violation and the
   arithmetic that produced it — e.g. `Llava-OneVision-7B: 0.20 + 400×0.0044 = 1.96 s > τ = 0.50 s`.
   That printed line *is* the A37 result, and it is far more useful than a solver status code.
2. **Solver-reported.** Demand (1)/(2) cannot be met within an active budget (6)/(7) — the §4.5 sweep's
   expected failure mode at `a2000_h0`. Reported as `INFEASIBLE` with the binding budget named.

`MilpResult.status ∈ {OPTIMAL, INFEASIBLE_STRUCTURAL, INFEASIBLE_SOLVER, TIME_LIMIT, UNBOUNDED_GUARD}`.
An infeasible run is a **result**, written to the report like any other, not an exception.

### 7.4 Distinguishing "the paper is inconsistent" from "our code is wrong"

Infeasibility is the expected outcome, which makes it the *worst* place to hide a bug. Four
independent checks, run as tests, not as commentary:

- **The self-consistent control.** The same run on the `derived_tiers` profile set — whose `τ` is
  computed from our own space — **must be feasible**. Same code, same data, different `τ`. If
  `derived_tiers` is also infeasible, the fault is ours.
- **A known-feasible synthetic.** A tiny hand-built `MilpInputs` (2 configs, 2 models, hand-computed
  optimum) whose answer is known by arithmetic. If that fails, nothing else is trustworthy.
- **The arithmetic is printed.** `nearest_miss` shows the operands, so a reviewer holding Table 5 can
  check `0.20 + 400 × 0.0044` by eye. A bug in unit conversion shows up here immediately (§3.4).
- **Monotone relaxation probe.** The τ at which each (w,s) would become feasible is computed and
  reported (**not applied**). If that value is absurd (≫ or ≪ the printed tier by orders of magnitude
  rather than the ≈2-4× A37 predicts), suspect our code. A37 predicts ≈4× on Video Q/A `Best`; a
  measured 4× corroborates, a measured 400× indicts us.

---

## 8. Solver choice

**Recommendation: PuLP as the modelling layer, CBC as the default backend, HiGHS as an opt-in
alternate — because PuLP lets A.5's equations be written almost line-for-line in the appendix's own
notation, and it makes the backend a one-word argument, so the "no Gurobi" substitution is provably
confined to the solver and cannot leak into the formulation.**

Rejected, with reasons:

- **OR-Tools CP-SAT.** The wrong tool for this model: CP-SAT is integer-only, and `x^peak`/`x^avg` are
  `R⁺` by A.5's own declaration (§4.1). Using it would force discretizing the request rates — a
  modelling change smuggled in as a backend change, which is exactly what this project must not do.
- **OR-Tools' MPSolver wrapper.** Adequate, but a heavier dependency whose API distance from the
  appendix's notation is greater, for no gain on a model this small.
- **Gurobi.** Forbidden by `CLAUDE.md`.

Confidence that the substitution is sound: the model is ~20 integer and ~3,000 continuous variables
with a tight LP relaxation. CBC solves this class to proven optimality in well under the paper's
limit; this is not a problem where solver strength plausibly changes the answer.

**Time limit: 300 s**, from `sources/tables.py::SOLVER_TIME_LIMIT_S`, which already carries the
citation ("A.5 p.587: solved using Gurobi with a time limit of 300 seconds"). It is imported, not
retyped. `MilpResult` records wall-clock, the MIP gap at termination, and the backend name + version;
a `TIME_LIMIT` status with a non-zero gap invalidates any optimality claim and `report.py` says so in
the run's header rather than in a footnote.

A `Backend` protocol (`build`, `solve`, `status`, `values`, `gap`) keeps CBC swappable. A test solves
the synthetic instance on every installed backend and asserts identical objective values, so a backend
difference surfaces as a test failure and not as a changed headline number.

---

## 9. The result object, and what it must carry

### 9.1 Shape

```python
@dataclass(frozen=True)
class MilpResult:
    # provenance of the answer -- all mandatory, none defaulted
    profile_set_name: str                 # M3 Section 9.1: no result without its set
    operating_point_policy: OperatingPointPolicy   # the ~6.8x lever (A37b)
    token_policy: TokenPolicy                      # p90 by default (A46)
    workflow: str; slo: tuple[str, str]; epoch: int
    objective: Objective
    budget_choice: str; cost_budget: float | None
    solver: str; solver_version: str; time_limit_s: int
    # the answer
    status: MilpStatus
    objective_value: float | None
    n: Mapping[ModelProfileKey, int]
    x_peak: Mapping[tuple[str, tuple[str, str], ConfigKey, ModelProfileKey], float]
    x_avg:  Mapping[...]
    gap: float | None; wall_clock_s: float
    # what the reader must not be allowed to miss
    data_excluded: tuple[str, ...]                 # Q19 -- mandatory beside every number
    exclusion_ledger: ExclusionLedger              # data-lack vs SLO-filter, kept apart (A71)
    inactive_constraints: tuple[str, ...]          # e.g. ("eq7: no budget chosen",)
    equation_map: Mapping[str, str]                # A58: which of the 13 were duplicates
    incoherent_mass: IncoherenceReport             # A51 -- Section 9.3
    support_size: int                              # A70 -- is it really one configuration?
    structural_record: StructuralRecord            # Section 10
    fidelity_notes: tuple[str, ...]                # A57, A66-A71, e_m degeneracy, tool-blindness
```

### 9.2 The data-excluded set is not a footnote

Q19 makes it mandatory. `report.py` has **no code path** that prints an objective value without
printing `profile_set_name`, `operating_point_policy` and the excluded count with a one-line reason
breakdown. A test asserts that (`test_no_headline_number_without_its_caveats`). Every GPU count is
additionally labelled *"for LLM executors only"* — 11 of 26 executors are tools with no profile, and
the two workflows are not affected equally (M3 §12.3), so the number is a lower bound and the
qualifier belongs in the sentence, not the appendix.

### 9.3 The incoherent-mass measurement (A51) — designed, and never a constraint

A.5 has **no constraint linking `c` to `m`**. `x_{w,s,c,m}` may route
`c = (D=4, R=4, model=Gemma-3-27B)` onto `m = (Phi-4, H100, TP=2)` — claiming Gemma's accuracy while
paying Phi-4's throughput, latency and energy. `MilpInputs.coherent(c, m)` exists so M4 can measure
this. **It must never appear in `model.py`.** A test asserts `model.py` contains no reference to it.

What is measured and reported, per run:

```
incoherent_mass_fraction = Σ{x : not coherent(c,m)} / Σ{x}
```

plus the three things that make the number interpretable: the **largest single incoherent flow** with
its (c,m) names; the **accuracy delta** — claimed `a_c` minus the `a_c` of the configuration that
actually names `m` at the same knobs, where that exists — which converts the defect into percentage
points of over-claimed quality; and the **counterfactual cost**, the objective value of the same model
re-solved *with* coherence imposed, run in a separate, clearly-labelled `critique/` path that never
touches the headline result. If the fraction is zero the defect is latent (the optimum did not need to
exploit it); if it is non-zero, the formulation is not merely under-specified but exploitable, and we
will have measured it rather than argued it. **Either outcome is a finding**, and the design must not
prefer one — a zero here is not a vindication of A.5, only of the profile set's coincidences.

---

## 10. The HEFT/precedence critique: what M4 records, and the rule it obeys

### 10.1 The rule, stated as a prohibition

> **M4 may not read `LogicalWorkflow.edges`, node lists, or any DAG structure, for scheduling or for
> any other purpose.** A.5 has no precedence constraint and no makespan term, and M4 adds neither.

This was M1's rule (`development/DESIGN.md` §8.1) and it survives unchanged. `/optimization/milp/`
imports nothing from `/development/`; the existing boundary test is extended to assert it. The rule is
not a stylistic preference — if M4 ever needs precedence to make the MILP feasible, **that is the
finding**, and it goes to `architecture-decisions.md` rather than into `model.py`.

### 10.2 What M4 records so the comparison becomes computable

M3 already built `optimization/profiles/critique/critical_path.py`, which computes the structural
comparison, and it is quarantined from `to_milp_inputs()`. M4's job is only to emit, per run, the
`StructuralRecord` that the comparison needs from *the optimizer's side*:

| Recorded | Why the comparison needs it |
|---|---|
| the winning `(c, m)` pairs and their mass | names the configuration whose critical path is to be computed |
| `ℓ^TTFT_m`, `ℓ^TPOT_m`, `t_c` for each | the three operands of eq. (5), so the single-stream latency can be recomputed by hand |
| `eq5_value` per selected pair | the optimizer's *entire* latency model, as one number |
| `tau` and its slack | how much headroom eq. (5) thinks it has |
| `tool_stages_in_configuration` (count only, from the config key, **not** from DAG edges) | the number of stages contributing zero to `eq5_value` — the size of the blind spot, without reading structure |

The comparison figure — "eq. (5)'s single number vs. the critical path `L_scene + max(L_frames,
L_stt) + L_qa`" — is then produced **outside** M4 by `critique/critical_path.py`, consuming this record.
It is **structural, not numeric**: the paper profiles no tool latency at all, so the magnitudes are
`INVENTED` and quarantined (Q16), and every caption must say so. The defensible claim is about *which
terms exist at all*, and A62 sharpens it — for the model §4.6 actually runs, eq. (5) cannot be
evaluated in the first place.

---

## 11. What M4 deliberately does not do

### 11.1 No `μ_m` — and the one-line seam for M5

Eq. (3) is `μ_m · Σ x^peak t_c ≤ n_m θ_m`. M4 implements it with the multiplier **absent**, which is
`μ_m = 1` numerically but must not be written as a `1.0` constant, because `μ_m` is *undefined in the
paper* (A42) and a hardcoded 1.0 is a value. The seam:

```python
def _capacity_lhs(self, m):            # M4: returns the sum. M5 overrides to scale it.
    return lpSum(self.x_peak[w, s, c, m] * t_c[c] for (w, s, c) in self.admissible_for(m))
```

`MilpResult.fidelity_notes` records `"eq. (3) built without mu_m (M5); the paper never defines it"` on
every M4 run, so no M4 number is ever mistaken for an Opt+Mult number. M5 adds a `mu: Mapping[m,
Value]` argument and overrides this one method; no other file changes. A test asserts M4 emits no
`mu` symbol at all.

### 11.2 Also out of scope

- **No precedence, no makespan** (§10.1).
- **No coherence constraint** (§9.3) — measuring it is in scope, imposing it is not.
- **No `M` re-indexing by operating point** (Q20/A37b) — one operating point per `m`, chosen at M3's
  boundary.
- **No per-DAG-node model assignment.** Table 1 promises it; A.5's index set has no node. M1's
  per-node assignment dead-ends here, as M1 predicted.
- **No CPU resource type.** A.5's `G`, `B_g`, `c_g` and eq. (7) are GPU-only (A13), though §4.6
  evaluates CPU offload. Not added.
- **No auto-scaler, no runtime dispatch** (M6/M7).
- **No numerical validation against Tables 1-6 / Figures 7-14** — that is the explicitly deferred
  later phase in `PROGRESS.md`. M4 produces numbers; comparing them to the paper's is a separate
  milestone with its own design.

---

## 12. Test list

Named for the property defended, in M3's style.

**`tests/test_milp_formulation.py`** — is it A.5, exactly?
- `test_the_ten_distinct_equations_are_emitted_once_each` (A58, with the 13→10 map)
- `test_duplicate_equations_are_recorded_not_silently_dropped`
- `test_constraint_set_is_identical_across_all_three_objectives` (§6.4)
- `test_x_is_continuous_and_n_is_integer_as_A5_declares` (§4.1)
- `test_c_g_is_multiplied_by_g_m_in_both_eq6_and_eq12` (A57 — the defect, reproduced)
- `test_no_precedence_constraint_and_no_makespan_term_exist` (§10.1)
- `test_model_module_never_references_the_coherence_predicate` (A51)
- `test_no_mu_symbol_appears_anywhere_in_milestone_4` (§11.1)
- `test_milp_package_imports_nothing_from_development_or_from_profiles_beyond_MilpInputs`

**`tests/test_milp_filters.py`** — do the SLO filters do what eq. (4)/(5) say?
- `test_an_inadmissible_pair_gets_no_variable_rather_than_a_big_M`
- `test_latency_filter_is_ttft_plus_tc_times_tpot_and_nothing_else` (no summing over tasks)
- `test_each_slo_type_applies_only_the_filter_whose_dimension_matches` (A68)
- `test_a_latency_run_places_no_floor_on_accuracy_and_the_report_says_so` (A68's consequence)

**`tests/test_milp_unavailable.py`** — is missing data ever imputed?
- `test_an_unavailable_parameter_removes_its_index_element_and_never_becomes_zero`
- `test_a_missing_ttft_excludes_the_model_only_on_latency_runs` (A71)
- `test_llava_onevision_is_excluded_from_eq5_for_lack_of_data_not_lack_of_merit` (A62)
- `test_exclusion_ledger_keeps_data_lack_and_slo_rejection_apart`
- `test_zeroing_a_missing_ttft_would_change_the_answer` (proves the rule is load-bearing)

**`tests/test_milp_infeasibility.py`** — is infeasibility a result, and is it ours or the paper's?
- `test_baseline_latency_tier_is_infeasible_and_reports_the_arithmetic` (A37)
- `test_the_same_run_on_derived_tiers_is_feasible` (the control that indicts our code if it fails)
- `test_tau_is_never_modified_by_any_code_path_in_the_milp_package`
- `test_structural_emptiness_is_detected_before_the_solver_is_called`
- `test_a_hand_computed_synthetic_instance_reaches_its_known_optimum`
- `test_the_relaxation_probe_is_reported_and_never_applied`

**`tests/test_milp_budgets.py`** — can a budget be defaulted into?
- `test_omitting_the_budget_argument_is_an_error_not_a_default` (A43)
- `test_no_budget_records_eq7_as_inactive_rather_than_dropping_it_silently`
- `test_table_3_sweep_rows_are_solvable_end_to_end` (§4.5)
- `test_objective_13_refuses_to_solve_without_a_bounding_budget` (A67, §4.3)
- `test_cost_budget_is_relative_and_no_absolute_dollar_figure_is_invented`

**`tests/test_milp_reporting.py`** — can a number escape without its caveats?
- `test_no_headline_number_without_profile_set_operating_point_and_excluded_set` (Q19)
- `test_gpu_counts_are_labelled_llm_executors_only` (M3 §12.3 point 3)
- `test_incoherent_mass_is_measured_and_reported_whether_or_not_it_is_zero` (A51)
- `test_support_size_is_reported_so_a_blend_is_never_printed_as_a_single_row` (A70)
- `test_time_limit_termination_invalidates_the_optimality_claim_in_the_header`

**`tests/test_milp_units.py`** — §3.4.
- `test_capacity_both_sides_reduce_to_tokens_per_second`
- `test_energy_and_cost_objectives_reduce_to_kwh_and_dollars_over_one_epoch`
- `test_request_rates_are_converted_from_per_minute_exactly_once`

**`tests/test_milp_structural_record.py`** — §10.2.
- `test_the_record_carries_eq5s_three_operands_for_every_selected_pair`
- `test_tool_stage_count_comes_from_the_config_key_and_not_from_dag_edges`
- `test_critical_path_comparison_consumes_the_record_without_the_milp_importing_it`

**`tests/test_milp_backend.py`** — §8.
- `test_every_installed_backend_agrees_on_the_synthetic_optimum`
- `test_the_time_limit_is_imported_from_the_paper_constant_not_retyped`

---

## 13. File layout and build order

```
/optimization/milp/
  DESIGN.md .............. this document
  __init__.py ............ public API: solve(), Objective, BudgetChoice, MilpResult
  A5.py .................. the ten distinct equations transcribed VERBATIM from pp.586-587 as
                           docstring constants, with the 13->10 duplicate map (Q21). No logic.
  units.py ............... Quantity + the [OURS] conversions of Section 3.4, one line each
  sets.py ................ W/S/M/C_w/G; admissibility; the ExclusionLedger; EmptyAdmissibleSet
  model.py ............... variables + the seven constraints. Imports MilpInputs and nothing else
                           from the profile layer. _capacity_lhs() is M5's seam
  objectives.py .......... the three objectives + the bounding guard of Section 4.3
  solve.py ............... Backend protocol, PuLP/CBC default, 300 s limit, status mapping
  scenarios.py ........... BudgetChoice; cost_budget_scenarios() [OURS, relative]; epoch sweep
  report.py .............. MilpResult rendering; the caveat gate of Section 9.2
  critique/
    incoherence.py ....... A51 measurement + the coherence-imposed counterfactual (QUARANTINED:
                           never imported by model.py; enforced by test)
    structural_record.py . what Section 10.2 emits for critical_path.py
/tests/
  test_milp_formulation.py  test_milp_filters.py     test_milp_unavailable.py
  test_milp_infeasibility.py  test_milp_budgets.py   test_milp_reporting.py
  test_milp_units.py          test_milp_structural_record.py   test_milp_backend.py
```

**Build order, file by file with confirmation per `CLAUDE.md`:**
`A5.py` (and the Q21 transcription) → `units.py` → `sets.py` → `model.py` → `objectives.py` →
`solve.py` → `scenarios.py` → `report.py` → `critique/` → tests.

`A5.py` first is deliberate, and mirrors M3 putting `provenance.py` first: the verbatim text of what
we claim to be reproducing must exist in the repo *before* the code that claims to reproduce it, so
every later file can be diffed against it by a reviewer who has the PDF open.

---

## 14. Decisions — resolved, with the source each rests on

All five are answered below and the design is implementable as written. Arno overrides any of them
by saying so; nothing here is a fait accompli, but nothing here is left dangling either.

### Q21 — verbatim transcription. **SETTLED, 2026-09-12.**

Done, not deferred. A.5 was extracted from the PDF text layer (pp.586–587) and is transcribed in
**`/optimization/milp/A5_VERBATIM.md`**, which is now this milestone's source of truth for the
algebra. Answers:

- **(a) `α` scopes both.** Eqs. (1) and (2) are both two-sided with the same `α`. No peak/average
  asymmetry.
- **(b) eq. (3) has NO average twin.** Capacity binds `x^peak` only, so `n_m` is provisioned from
  peak load alone and `x^avg` never sizes the fleet.
- **(c) eq. (13) uses `x^avg`.**

**A66 is CONFIRMED and is the strongest finding at M4.** The SLO filters (4)/(5)/(8)/(9) constrain
`x^peak` **only**; `x^avg` appears in eq. (2), eq. (6)/(10) and objective (13), none of which is a
filter. Therefore O3 maximises `Σ x^avg · a_c` with **nothing preventing it selecting configurations
whose `a_c` is below `τ`** — the one objective that optimises quality is the one the quality filter
cannot reach. No constraint ties `x^avg` to `x^peak`, so peak may be served compliantly and average
non-compliantly. **A57, A58 confirmed exactly; A67 refined; A72 newly found (§5.4).**

Consequence for implementation: `AccuracyWeighting` is no longer a fork. Default to `AVG` because
that is what the paper prints; keep `PEAK` available as a **sensitivity variant only**, labelled
`[OURS]`, since selecting it would silently repair A66.

### Q22 — solver. **PuLP + CBC.** Confirmed against the verbatim declarations.

A5_VERBATIM records `n_m ∈ Z⁺` and `x^peak, x^avg ∈ R⁺`. A mixed integer/continuous program is
therefore the paper's own declaration, not our modelling choice, which settles the backend question
on fidelity rather than taste:

- **CBC via PuLP — chosen.** Handles mixed integer/continuous LP natively; A.5's equations transcribe
  near line-for-line; the backend is a one-word argument, so the no-Gurobi substitution
  (`CLAUDE.md`) is provably confined to one call site. `SOLVER_TIME_LIMIT_S = 300` is already in
  `sources/tables.py` from A.5's own "time limit of 300 seconds".
- **HiGHS — opt-in.** Same model object, faster; used to cross-check that CBC's optimum is not a
  solver artifact. A test asserts the two agree on objective value.
- **CP-SAT — rejected.** Integer-only. Using it would force `x` onto a grid, which contradicts
  `x ∈ R⁺` and would smuggle a modelling change in as a backend change. This is the distinction A70
  turns on and it must not be blurred.

### Q23 — `Cost_budget` / `τ_{w,cost}` (A67). **Implement O3; inject the budget as a named experiment coordinate.**

The verbatim text refines the problem: `Cost_budget` **is** defined — `Σ_w τ_{w,cost} · Σ_s
λ^avg_{w,s}` — so the missing thing is `τ_{w,cost}`, a **cost-type SLO threshold**. §3.4 (p.575)
defines four tiers for *quality and end-to-end latency* only, and no table in either version reports
a cost tier. `Cost_total` in (13) is never defined either; eq. (12)'s expression is the only
candidate and is what we use, labelled.

**Recommendation: implement O3, with `τ_{w,cost}` supplied explicitly per run, never defaulted.**
Reasons, in order of weight:

1. **Precedent already set by A43.** `B_g` is in exactly this position — absent from the paper,
   required by a constraint — and M3 resolved it by refusing a default and forcing explicit
   injection (`budget_scenarios()`, with a named `no_budget` case). Doing the same for `τ_{w,cost}`
   makes the two absences behave identically instead of inventing a second convention.
2. **Dropping O3 loses more than it protects.** "Three interchangeable objectives" is a load-bearing
   claim of §3.3.1, and Figures 7–9 report Acc./Energy against Acc./Cost columns. An M4 with two
   objectives cannot reproduce those figures at all.
3. **The honesty cost is payable.** Every O3 result is stamped with its multiplier and listed as
   uninstantiable-from-paper-data in the data-excluded register, so no O3 number can be quoted as
   the paper's.

Express `τ_{w,cost}` as a **multiple of O2's optimum** for the same `(w, s)` — solve O2 first, then
set the budget to `k ×` that cost for `k ∈ {1.0, 1.25, 1.5, 2.0}`. This makes O3 runs comparable
across profile sets, which an absolute dollar figure would not be. The multiplier is `[OURS]` and
appears in `MilpResult`.

### Q24 — the dimensional split of the SLO filters (A68). **Apply only the dimension-matching filter — and this is the LITERAL reading, not a deviation.**

The verbatim text settles this in the paper's favour. A.5 itself scopes each filter to an `s`:

> "For accuracy SLO (**s = max_accuracy**): ... (4)"
> "For latency SLO (**s = min_latency**): ... (5)"

So applying eq. (5) to an accuracy-tier run was never the literal reading — it would compare a
latency in seconds against an accuracy threshold in percent, which is dimensional nonsense. The
design's recommendation stands and is now *strengthened*: it is reproduction, not deviation, and
§5.3 should not describe it as a choice.

**The consequence is still a real defect and is reported:** a latency-tier run has **no quality floor
whatsoever**, and an accuracy-tier run has **no latency ceiling**. A.5 gives each `(w,s)` exactly one
`τ`, so a workflow cannot carry both promises at once. `MilpResult` records, for every run, the
dimension that was *not* constrained and the realised distribution on that dimension — turning the
gap into a measurement.

### Q25 — headline workflow. **Video Q/A**, confirmed on data coverage as well as structure.

Usable configurations (`t_c` **and** `a_c` both available, i.e. admissible to eq. (3) and eq. (4)):

| Workflow | Configs | `t_c` | `a_c` | **Usable** |
|---|---|---|---|---|
| Video Q/A | 24 | 18 | 18 | **18** |
| Code Generation | 20 | 12 | 16 | **12** |

Video Q/A wins on three independent grounds: 50% more usable configurations; it is the only workflow
with a parallel branch, so it carries the §4.6 co-scheduling case and the HEFT/precedence critique
(A59 makes Code Generation's per-node decomposition unavailable *and* it is a total order); and it
carries A37 and A62. **Code Generation still runs in every experiment** — it is the second workflow
M5's multiplexing needs, and dropping it would forfeit Table 2's gain.

---

### Noted, not blocking

**A63** (the `PAPER_FIGURE_LABEL` promotion) — **keep rejected.** From M4's side it is worse than
circular: the four promoted values sit at *exactly* the tier thresholds, so a promoted `a_c` would
land filter (4) on an equality boundary where floating-point comparison decides admissibility.
`a_c < τ` with `a_c == τ` is precisely the case A.5's strict inequality leaves to the last bit.

**A64** (`wide`, `maxthroughput` absent) — neither blocks M4. `maxthroughput` is correctly reachable
as `operating_point=MAX_THROUGHPUT` and M4 reports against it as the sensitivity leader. **Leave
`wide` unbuilt:** it would populate 14 currently-excluded `t_c` values, and populating them by
extrapolation is exactly what Q19 forbade. The exclusions stand.

**Noted, not blocking.** A63 (the `PAPER_FIGURE_LABEL` promotion): I agree with the rejection, and
from M4's side it would be worse than circular — the four promoted values sit at exactly the tier
thresholds, so a promoted `a_c` would land filter (4) on an equality boundary where floating-point
comparison decides admissibility. Keep it rejected. A64 (`wide` and `maxthroughput` absent): neither
blocks M4. `maxthroughput` is correctly reachable as `operating_point=MAX_THROUGHPUT` and M4 will
report against it as the §9.3 sensitivity leader. `wide` would matter to M4 — it would populate 14
currently-excluded `t_c` values and shrink the excluded set — but populating them is exactly what Q19
forbade, so my recommendation is to leave `wide` unbuilt and let the exclusions stand.
