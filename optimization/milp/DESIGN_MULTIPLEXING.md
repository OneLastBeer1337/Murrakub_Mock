# Milestone 5 — Design: Multiplexing (`µ_m`) and the joint-workflow solve

**Phase:** Optimization (paper §3.3.1 p.574; Appendix A.5 eq. (3), p.586; §4.3 p.576; Table 2 p.576)
**Status:** design review pending — **no implementation code exists or should exist yet.**
**Scope:** "Mkb Opt+Mult". Two workflows in one solve; the `µ_m` factor in eq. (3); the
Opt-vs-Opt+Mult comparison. Nothing else in A.5 changes.

**Sources of truth.** `optimization/milp/A5_VERBATIM.md` for all algebra. [OSDI] Chaudhry et al.,
*OSDI '26*, cited `§x.y p.NNN`; [ARXIV] arXiv:2508.18298v2. A.5 is identical in both.

**Standing policy in force (`reproduce-murakkab-literally`):** where the paper is ambiguous,
unsound or silent, **take its reading and record the problem**. M5 is the milestone where that
policy is hardest to keep, because the paper is not ambiguous about `µ_m` — it is *silent*, and a
silence cannot be reproduced. §4 is about how we behave in a silence without filling it.

Conventions: **[DESIGN CHOICE]** fills a paper silence; **[OURS]** marks a step the paper does not
describe; **[INVENTED]** has no paper counterpart at all. Gap numbering continues at **A75**; open
questions continue at **Q26**.

---

## 1. Plain language first

### 1.1 What multiplexing is

Suppose two different workflows both want to talk to a Gemma-3-27B server. Code Generation's traffic
peaks when developers are at their desks; Video Q/A's peaks somewhere else. If you provision a
separate fleet of Gemma servers for each workflow, you buy enough GPUs to cover *each* workflow's own
worst moment, and you buy them twice. If instead both workflows share one fleet, you only need enough
GPUs to cover the worst moment *of the combined stream* — and the combined stream's peak is smaller
than the sum of the two individual peaks, because the peaks do not line up. That difference is the
multiplexing gain. It is the same argument that makes a shared taxi rank need fewer taxis than two
private ones.

The paper claims this is worth a lot: Table 2 (p.576) reports "Murakkab Opt" at 1164 GPUs / 27.7 kWh
/ $57.2 and "Murakkab Opt+Mult" at 912 / 22.1 / 47.2 — a **21.6% / 20.2% / 17.4%** reduction
(`sources/tables.py::MULTIPLEXING_REDUCTION_PCT`, [OSDI] p.576; [ARXIV] p.9 says 21.1/20.2/17.3 —
A47, the validation target is itself version-dependent).

### 1.2 What the paper actually gives us to model it with

One symbol. Eq. (3) reads

```
µ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c  ≤  n_m · θ_m        ∀ m ∈ M
"where µ_m is the model-specific multiplexing factor."
```

and **that sentence is the whole definition** — no value, no bound, no units, no estimation method,
in either version, and `µ_m` does not appear in §3.3's list of what a profile contains. This is
**A42**, and it is not an incidental detail of M5; it is M5's subject.

### 1.3 The shape of this milestone in one paragraph

M5 does three things. (a) It widens `W` from one workflow to two, so that a single solve provisions
one shared fleet for both — this is a real structural change and it is where any *honest* sharing
gain would come from. (b) It introduces `µ_m` as an explicit, never-defaulted experiment coordinate,
with its provenance attached, because the paper gives us no way to derive it. (c) It computes the
Opt vs Opt+Mult comparison in a way that says out loud which part of any gain came from (a) and
which from (b). §5 argues that under A.5's own algebra, (a) can deliver almost nothing — which makes
(b) carry the entire 21.6%, by fiat.

---

## 2. Does M4's "one-line seam" claim survive contact? **No.**

M4's `DESIGN.md` §11.1 and `model.py::_capacity_lhs`'s docstring both assert:

> "**THIS FUNCTION IS MILESTONE 5'S ENTIRE SEAM.** Multiplexing changes `mu` and nothing else — not
> the variables, not the other six constraints, not the objectives."
> — and DESIGN.md §3.1: "M5 widens `W` by passing a list — no rewrite."

I checked this against the code rather than the doc. **The `µ_m` half of the claim holds. The `W`
half does not, and the two are not separable.** Specifically, in `model.py`:

1. **`x` is not keyed by `(w, s)`.** `PairKey = tuple[ConfigKey, ModelProfileKey]`; `x_peak` and
   `x_avg` are `Mapping[PairKey, LpVariable]`. A.5's variable is `x^peak_{w,s,c,m}`, four indices.
   M4 dropped two of them because it solves one `(w,s)` at a time and they were constant.
2. **`build_model()` takes a single `Admissible`,** and `Admissible` carries exactly one `workflow`
   and one `slo` (`sets.py`). One built model = one `(w, s, epoch)`.
3. **Eqs. (1) and (2) are emitted once each,** as `eq1_lower/eq1_upper` over `lpSum(x_peak.values())`
   — a single scalar demand pair, not a family indexed by `(w,s)`.
4. **`solve()` takes `workflow: str` and `slo: tuple[str,str]`** as required scalars, and
   `MilpResult` has scalar `workflow` and `slo` fields, as does the report renderer.

The consequence is decisive: **today, `n_m` is not shared by anything.** Each `(w,s)` gets its own
`LpProblem` with its own `n` variables. Passing a list of workflows is not possible without
re-keying the variables, re-indexing eqs. (1)/(2) as constraint families, merging per-`(w,s)`
`Admissible` records into one index space, and widening the result object and the report. That is
five files, not one function.

**This is not a criticism of M4 — M4's separation was correct and deliberate** (its §3.1 reason, that
an accidental two-workflow solve would pre-empt M5's experiment, was sound). But the doc's claim
that M5 is a one-line change was optimistic, and it matters for a reason beyond scheduling: it
conflates *`µ_m` is one line* (true) with *multiplexing is one line* (false). The fact that the
mechanism which actually shares instances lives in the index space while the paper's only named
multiplexing construct lives in a scalar coefficient is itself the finding of §5.

> **A75 [NEW GAP] — M4's seam claim was half right, and the half that failed is the informative
> half.** A.5's `µ_m` is genuinely a one-scalar change to eq. (3). But instance *sharing* — the thing
> multiplexing means — is not expressed by `µ_m` at all; it is expressed by the fact that eq. (3)
> sums over `w` while `n_m` does not depend on `w`. The paper names the coefficient and never names
> the mechanism.

---

## 3. Widening `W`: what changes, constraint by constraint

### 3.1 The new index space

| Set | M4 | M5 |
|---|---|---|
| `W` | one of `{code_generation}` / `{video_qa}`, required scalar | **both**, `{code_generation, video_qa}` |
| `S` | one `(type, tier)` per solve | **`{(accuracy,good), (latency,good)}`** per solve, per §4.3 (§6) |
| `M` | 20 model profiles | unchanged, 20 — **global, shared across `W`** |
| `C_w` | 20 or 24 | both: 44, partitioned by `w` |
| `G` | `{A100, H100}` | unchanged |

`x^peak`/`x^avg` re-key to the full A.5 four-index form `(w, s, c, m)`, restoring the two indices M4
elided. `n_m` stays keyed by `m` alone — **that is the sharing**.

### 3.2 Effect on each of the seven distinct constraints

| Eq. | Change under `|W| = 2` | Notes |
|---|---|---|
| (1) peak demand | becomes a **family**: one two-sided pair per `(w,s)` — 4 pairs, not 1 | `α = 1.15` scopes both bounds (Q21a) |
| (2) avg demand | same, family over `(w,s)` | unchanged algebra |
| (3) capacity | **unchanged in form, and this is the whole point** — its `Σ_{w,s,c}` already ranges over all workflows. Widening `W` makes it bind a *shared* `n_m`. | §5 |
| (4)/(8) accuracy filter | per `(w,s,c,m)` as before; `τ` is already keyed `(w, type, tier)` in M3, so the two workflows carry **different thresholds in the same solve** | A68 still applies: only the dimension-matching filter is active per `s` |
| (5)/(9) latency filter | same; note the filter depends on `t_c`, hence on `w` through `C_w` | A37 still bites (§7.3) |
| (6)/(10) cost budget | `Cost_budget = Σ_{w∈W} τ_{w,cost} · Σ_s λ^avg_{w,s}` — the `Σ_w` **finally has more than one term**. M5 is the first milestone where this sum is non-trivial. | A67 unchanged: `τ_{w,cost}` still undefined; still a required coordinate |
| (7) resource budget | unchanged in form; now genuinely contested between two workflows | `B_g` still required, never defaulted (A43) |

**Objectives (11), (12), (13) are unchanged in form.** (11) and (12) sum over `m` only and were
never workflow-indexed. (13) normalises by `Σ_{w,s} λ^avg_{w,s}`, which now sums over two workflows
— so the joint accuracy objective is a **demand-weighted blend of two workflows' accuracies**, which
are measured on different benchmarks (Code Gen pass@1 vs Video Q/A QA accuracy, M3). Averaging them
is meaningless as a quantity; A.5 does it anyway.

> **A76 [NEW GAP] — objective (13) averages incommensurable accuracies across workflows.** `a_c` for
> Code Generation and `a_c` for Video Q/A come from different benchmarks with different scales and
> different meanings (M3 §5). Eq. (13)'s numerator `Σ_{w,s,c,m} x^avg · a_c` adds them, and its
> denominator divides by total requests. Under `|W| = 1` this was a scalar per workflow and harmless.
> Under `|W| = 2` — which is §4.3's own experiment — it is a single number formed by averaging two
> incomparable scales, and the optimizer will trade quality in one workflow against quality in the
> other at an exchange rate that has no meaning. Reproduced as written; reported on every O3 run.

### 3.3 The infeasibility coupling [DESIGN CHOICE]

Under `|W| = 1`, a structurally-empty admissible set for one `(w,s)` ended that run. Under `|W| = 2`
in **one** problem, an empty set for `(video_qa, latency-good)` makes the *entire joint solve*
infeasible, taking Code Generation down with it. Given A37 — latency tiers are expected infeasible
under `baseline` — the §4.3 headline run is **predicted to be structurally infeasible before the
solver starts**, because its 30% low-latency share is a hard `≥` in eq. (1).

We do not repair this. `sets.py`'s `EmptyAdmissibleSet` reporting is extended to name **which**
`(w,s)` emptied the joint problem, so the failure is attributed rather than global. The joint run is
then repeated on `derived_tiers` as M4's §7.4 control. **Forbidden, as at M4:** dropping the latency
share, loosening `τ`, or solving the two workflows separately and calling it the joint result.

---

## 4. `µ_m` — the heart of this design

### 4.1 What `µ_m` must mean dimensionally

Eq. (3) has `tokens/s` on both sides (`x^peak` req/s × `t_c` tokens/req vs `n_m` × `θ_m`
tokens/s). `µ_m` therefore **must be dimensionless**. The paper's gloss gives no further constraint.

`µ_m` multiplies the **left** side — demand. So:

- `µ_m < 1` **shrinks** effective demand → **relaxes** the constraint → **reduces `n_m`** → a saving.
- `µ_m > 1` inflates demand → forces more instances → a penalty.
- `µ_m = 1` is the no-op (M4's `NO_MULTIPLEXING`).

**The direction is right for a gain, and `µ_m ∈ (0, 1]` is the only reading consistent with Table 2**,
where Opt+Mult uses *fewer* resources than Opt. We take it. [DESIGN CHOICE, forced]

But the reading has an uncomfortable consequence worth stating plainly. Eq. (3) is the **peak**
constraint and has no average twin (Q21b). So `µ_m · Σ x^peak · t_c` says: *the peak token demand
placed on model `m` is really only `µ_m` of what the peak rates say it is.* That is exactly a
**peak-shaving / peak-to-aggregate-peak deflator** — it asserts that the sum of per-stream peaks
overstates the aggregate peak, which is the correct statistical statement. So the reading is
coherent. The problem is not the direction; it is the *subscript* (§4.4).

### 4.2 Can `µ_m` be inferred from the paper's own data?

Partly — and the partial answer is more informative than either a clean yes or a clean no.

**The inference.** Under objectives (11)/(12) with eq. (7) inactive, eq. (3) binds and
`n_m = ⌈µ_m · D_m / θ_m⌉`, where `D_m` is the peak token demand routed to `m`. Total GPUs are
`Σ_m n_m g_m`. If `µ_m = µ` is **uniform across `m`** and the routing `D_m` is unchanged between the
Opt and Opt+Mult solves, then total GPUs scale linearly in `µ` up to integer rounding, and Table 2's
21.6% GPU reduction gives

```
µ ≈ 1 − 0.216 = 0.784      [OSDI]
µ ≈ 1 − 0.211 = 0.789      [ARXIV]
```

**Why this is DERIVED, not invented — and what it costs.** It uses only published numbers
(`MULTIPLEXING_REDUCTION_PCT`, A47) plus two stated assumptions: *uniformity across `m`* and
*routing invariance between the two solves*. Both are ours, neither is in the paper. It is carried
as `MuProvenance(DERIVED_FROM_TABLE_2, assumptions=(...), version="OSDI"|"ARXIV")`.

**The assumption is then immediately falsified by the paper's own row.** A single uniform `µ` scaling
a fixed routing predicts the *same* percentage reduction in GPUs, energy and cost. Table 2 reports
**21.6 / 20.2 / 17.4** — three different numbers. The spread cannot come from `µ` alone; it requires
the *routing* to change between Opt and Opt+Mult (a shift in the GPU-type mix, since `e_m` and `c_g`
are per GPU type). So either `µ_m` is genuinely heterogeneous across `m`, or the Opt+Mult gain is not
purely a `µ` effect. **Both possibilities are unmodellable from published data**, and the 5-point
spread between the GPU and cost reductions is the measurable size of what we cannot explain.

> **A77 [NEW GAP] — Table 2's three reduction percentages are mutually inconsistent with a uniform
> `µ_m`.** 21.6% GPUs, 20.2% energy, 17.4% cost cannot all follow from one scalar deflator applied to
> a fixed allocation. Recovering all three needs per-model `µ_m` (20 unknowns against 3 equations —
> under-determined by 17) or a routing change the paper does not report. The reproduction can match
> **at most one** of the three by construction, and must say which one it spent.

**Therefore: per-model `µ_m` values are INVENTED** — the system is under-determined and no
combination of published numbers pins them. They are quarantined exactly as M3 quarantined the seven
tool service times (Q16): they live in `critique/`, are unreachable from `to_milp_inputs()` or from
any headline path, and a test enforces it (§9).

### 4.3 The circularity trap — and how one number is spent to avoid it

Calibrating `µ = 0.784` from Table 2's GPU reduction and then "validating" M5 by reproducing Table
2's GPU reduction is **A63's circularity in a new costume**, and it would pass every test while
proving nothing.

**Rule [OURS]:** the GPU-reduction figure (21.6%) is **spent as calibration** and may never be quoted
as a validation result. The energy (20.2%) and cost (17.4%) reductions are then genuine — if weak —
out-of-sample checks, since nothing about them was used to fit `µ`. `report.py` prints
`calibration_target="Table 2 GPU reduction (SPENT — not a validation)"` on every derived-`µ` run, and
a test asserts no report can present the calibrated quantity as a check
(`test_the_calibration_target_is_never_reported_as_a_validation`). Per §4.2 the out-of-sample checks
are *expected to miss*, by roughly the 1.4 and 4.2 percentage points of A77's spread; a miss of that
size corroborates our arithmetic, a miss of 10× indicts it (M4 §7.4's logic).

### 4.4 Is `µ_m` even well-posed as a per-model constant? **No — and this is the central finding.**

Statistical multiplexing gain is a property of an **aggregate**: it depends on how many independent
request streams share an instance, how bursty each is, and how correlated their peaks are. The
textbook form is the peak-to-aggregate ratio

```
µ(A) = peak(Σ_{i∈A} load_i) / Σ_{i∈A} peak(load_i)
```

which is a function of the **set `A` of streams assigned to the instance** — i.e. of the decision
variable `x`. It falls toward `1/√|A|`-ish behaviour as more independent streams join, and it is
exactly `1` when `|A| = 1`. A.5 makes it a **parameter of `m` alone**, fixed before the optimizer
runs, and therefore constant whether one workflow or fifty share the model.

This is a category error, and it has three concrete consequences in the formulation as written:

1. **The gain is asserted, not derived.** `µ_m` is exogenous, so the model receives the multiplexing
   benefit *whether or not any sharing actually occurs*. A single-workflow solve with `µ_m = 0.784`
   gets the full 21.6% saving with nothing to multiplex against — the constraint cannot tell.
2. **The gain does not respond to the decision.** Routing all traffic onto one model (maximum real
   multiplexing) and spreading it across twenty (minimum) give the *same* `µ_m`. The optimizer has no
   incentive to consolidate, which is the behaviour multiplexing is supposed to reward.
3. **It is the wrong variable to be model-specific in.** Making `µ` depend on `m` says the gain comes
   from the model's identity — its batching behaviour, perhaps. That is a defensible but *different*
   effect (continuous batching efficiency), and if it is what the authors meant, the symbol belongs
   in `θ_m` (which is already a measured throughput at an operating point, A37b) rather than as a
   second multiplier on demand. Under that reading `µ_m` and `θ_m` are not independent and the model
   is over-parameterised.

> **A78 [NEW GAP] — `µ_m` is a parameter of the wrong object.** Multiplexing gain is a property of the
> assignment (which streams share an instance), not of the model. A.5 indexes it by `m`, fixes it
> before solving, and thereby makes the headline Opt+Mult saving exogenous: the optimizer is *told*
> the answer rather than finding it. A formulation that actually modelled sharing would need `µ` to
> depend on `x`, which would make eq. (3) non-linear — plausibly why it was not done, and precisely
> the seam where Arno's instance-based provisioning model differs. **Corollary:** because `µ_m` is
> exogenous and uniform in effect, "Mkb Opt+Mult" as A.5 formalises it is arithmetically
> indistinguishable from "Mkb Opt with `θ_m` inflated by `1/µ_m`". The paper's two headline policies
> differ by a change of units on throughput.

### 4.5 The related structural point: eq. (3) cannot express sharing gains anyway

Set `µ_m = 1` and solve two workflows jointly rather than separately. What is saved? Eq. (3) is
**linear and additive in load**: the joint constraint is `D_cg + D_vq ≤ n_m θ_m`, and the separate
ones are `D_cg ≤ n¹_m θ_m`, `D_vq ≤ n²_m θ_m`. Since `⌈(a+b)/θ⌉ ≤ ⌈a/θ⌉ + ⌈b/θ⌉`, the entire saving
from sharing is the **integrality rounding** — at most one instance per model profile, i.e. a handful
of GPUs out of 1164, well under 1%.

**So A.5's capacity model structurally cannot produce Table 2's 21.6%.** There is no term in which
the sum of peaks exceeding the aggregate peak could appear: `λ^peak_{w,s}` is a per-`(w,s)` scalar and
eq. (3) simply adds them. `µ_m` is not a *model* of multiplexing; it is a hand-placed coefficient that
inserts the answer where the model has no mechanism. This is the sharpest available instance of the
standing PATTERN (formulation narrower than the system), and unlike the others it sits on a headline
number rather than on an evaluation section.

**M5 will measure this**, not merely argue it: the joint-vs-separate solve at `µ = 1` (§7, Arm B vs
Arm A) yields the true sharing gain the formulation can express, as a number. My prediction is
**< 1%** against the paper's 21.6%. If it comes out large, the argument above is wrong and I want it
falsified by our own code.

---

## 5. Where `µ` comes from: the `MuChoice` coordinate

Following A43's precedent (`B_g`) and Q23's (`τ_{w,cost}`): **absent from the paper, required by a
constraint ⇒ explicit injection, no default, `TypeError` if omitted.** `solve_joint()` takes a
required `mu: MuChoice`.

| `MuChoice` | Value | Provenance | Reachable from headline? |
|---|---|---|---|
| `NO_MULTIPLEXING` | `1.0` ∀m | the M4 baseline; adds no information | yes — **this is "Mkb Opt"** |
| `UNIFORM_FROM_TABLE_2(version)` | `0.784` [OSDI] / `0.789` [ARXIV] ∀m | **DERIVED** from `MULTIPLEXING_REDUCTION_PCT` + 2 stated assumptions (§4.2) | yes, with calibration stamp (§4.3) — **this is "Mkb Opt+Mult"** |
| `UNIFORM_SWEEP(values)` | caller's, e.g. `{0.6,0.7,0.8,0.9,1.0}` | **[OURS]** sensitivity; no claim of paper fidelity | yes, labelled as a sweep, never as *the* result |
| `PER_MODEL(mapping)` | caller's per-`m` values | **[INVENTED]** — under-determined by 17 (A77) | **NO.** `critique/` only; test-enforced |

`mu.py` holds `MuChoice`, the provenance record, and the derivation with its assumption list in the
docstring. It imports `MULTIPLEXING_REDUCTION_PCT` from `sources/tables.py` rather than retyping
0.784, so the citation travels with the number (M4's rule for `SOLVER_TIME_LIMIT_S`).

`µ_m` is **not** added to `MilpInputs` and **not** added to the profile layer. `MilpInputs`'s field
list is pinned by `test_a5_parameter_list_is_pinned`, M3 guarantees 0% invented values in any
`ProfileSet`, and `µ_m` is absent from §3.3's profile contents (A42) — putting it there would falsify
all three. It is an argument to the solver, like the budgets.

---

## 6. The joint-workflow experiment: §4.3 is the headline, verified

§4.3 (p.576), identical in both versions:

> "we run video Q/A and code generation requests together and assign 70% requests to be
> high-accuracy and 30% requests to low-latency, both with *good* tier"

This is already encoded as `SloMix.section_4_3()` (`optimization/profiles/schema.py:395`), and it is
the paper's **own** joint experiment — two workflows, one solve, a stated SLO mix. It is M5's headline
setup. Confirmed against the source; no interpretation needed.

Three things §4.3 does **not** say, which M5 must therefore choose and label:

1. **The split of demand between the two workflows.** The 70/30 is across SLO *types*, not across
   workflows. §4.3 gives no workflow ratio. **[DESIGN CHOICE]** Use each workflow's own
   `λ^peak/λ^avg` from M3's Figure 19-derived arrival traces at their native magnitudes, rather than
   imposing a ratio — this is the only option that invents nothing. Recorded, and swept (Q28).
2. **Whether Table 2's numbers come from §4.3's setup at all.** Table 2 sits in the same subsection;
   I read it as the same experiment, but the table's caption does not say so. Flagged, not resolved
   — it affects only what we claim we are comparing against.
3. **Which epoch(s).** A69 stands: one independent MILP per epoch, no coupling. The joint run is
   swept across all 24 epochs and reported per epoch; any single-number headline is the
   demand-weighted aggregate, labelled **[OURS]**.

---

## 7. How the Mkb Opt vs Mkb Opt+Mult comparison is computed

The comparison is **three arms**, not two, because the paper's two-way comparison conflates two
different mechanisms (§4.5) and we must separate them to say anything true.

| Arm | Setup | What it isolates |
|---|---|---|
| **A. Separate** | two solves, `|W|=1` each, `µ=1`, results summed | M4's world. No sharing at all. |
| **B. Joint** | one solve, `|W|=2`, `µ=1` | **the sharing gain A.5 can actually express** — pure `n_m` consolidation. Predicted < 1% (§4.5). |
| **C. Joint + µ** | one solve, `|W|=2`, `µ=UNIFORM_FROM_TABLE_2` | "Mkb Opt+Mult" as A.5 defines it. |

**The paper's comparison is C vs (A or B) — and which one is ambiguous.** Table 2's "Murakkab Opt"
row could be either. Nothing in §4.3 or the table caption disambiguates.

> **Q26 [OPEN] — is Table 2's "Murakkab Opt" arm A or arm B?** *Recommendation: report **both**
> (C−A and C−B) and refuse to pick.* They will differ by under 1% if §4.5 is right, so the choice is
> numerically almost free — but stating both is what makes A.5's structural inability to express
> sharing visible, and picking one would hide it. Cost: one extra solve per epoch. Cheap.

`compare.py` emits a `MultiplexingComparison` carrying all three arms' GPU/energy/cost totals, the
two deltas, the `MuProvenance` and the calibration stamp, and the paper's own targets from
`MULTIPLEXING_REDUCTION_PCT` for **both** versions side by side (A47 — the target is
version-dependent and we do not reconcile it).

### 7.1 A74 under multiplexing: worse, better, or merely more visible?

A74 (M4's headline): under `baseline`, video_qa/accuracy-best, **100%** of allocated mass is routed
onto Phi-4 profiles — a model that appears in **no** Video Q/A configuration. A.5's `M` is global and
no constraint ties it to `C_w`.

My expectation, to be tested rather than asserted: **more visible, and probably worse.**

- *Worse, mechanically.* A74 is an exploit of a missing `c`↔`m` link. Joint solving gives the
  optimizer **both** workflows' configuration menus against **one** shared model pool, so a model
  attractive on Code Generation's `θ_m` now competes for Video Q/A's load inside the same problem.
  Cross-workflow incoherence is newly *available*; with `|W|=1` it was cross-configuration only.
- *Worse, economically.* `µ < 1` makes every model cheaper in eq. (3) by the same factor, so it does
  not change the *ranking* — but it lowers the absolute cost of consolidating onto a single
  high-`θ_m` model, and consolidation is exactly what produces incoherent routing.
- *More visible, definitely.* With two workflows the incoherence can be **attributed**: a flow can now
  be labelled "Video Q/A load on a Code-Generation-only model", which is a stronger and more legible
  claim than M4's within-run version.

**Measured, not argued.** `critique/incoherence.py` gains a **cross-workflow** breakdown:
`incoherent_mass_fraction` split into within-workflow and cross-workflow components, plus the new
`foreign_model_mass` — mass on `(c, m)` where `m` appears in **no** configuration of `c`'s workflow
(A74's exact condition). Reported for all three arms, so the trend across A→B→C is a table, not an
opinion. The quarantine is unchanged: `model.py` may not import it; the existing test stands.

---

## 8. What changes in `MilpResult` and in reporting

`MilpResult` is currently single-`(w,s)` (scalar `workflow`, `slo`). Two options:

- **(i) Widen `MilpResult`** — make `workflow`/`slo` tuples. Breaks every M4 consumer and every test
  that reads `r.workflow`.
- **(ii) Add `JointMilpResult`** — a new frozen dataclass for `|W|≥1`, with `MilpResult` unchanged
  and reconstructible from it per `(w,s)` via `.per_slo()`.

**Recommendation: (ii).** M4's 467 tests are the project's regression surface and its single-workflow
guarantees (A71's per-run excluded set, the caveat gate) are worth keeping intact. New fields:

```python
workflows: tuple[str, ...]              # the widened W
slo_mix: SloMix                         # section_4_3() for the headline
mu: MuChoice                            # NEVER defaulted
mu_provenance: MuProvenance             # DERIVED | OURS | INVENTED + assumptions + version
calibration_spent: str | None           # "Table 2 GPU reduction" -- not a validation (Section 4.3)
n: Mapping[ModelProfileKey, int]        # SHARED across workflows -- the point
x_peak: Mapping[tuple[str, tuple[str,str], ConfigKey, ModelProfileKey], float]   # 4 indices again
x_avg:  Mapping[...]
per_workflow_share: Mapping[str, float] # of GPUs, by attributed token mass [OURS] -- Section 8.1
foreign_model_mass: Mapping[str, float] # A74, per workflow
emptied_by: tuple[EmptyAdmissibleSet, ...]   # which (w,s) killed a joint run (Section 3.3)
```

Every M4 reporting rule survives unweakened and two are added: **no headline number without its
`MuChoice` and `MuProvenance`**, and **no `µ ≠ 1` result printed without the calibration stamp**.
`fidelity_notes` gains `"eq. (3)'s mu_m is undefined in the paper (A42); this run's value is
<provenance>"` unconditionally.

### 8.1 A GPU cannot be attributed to a workflow, and that is the point [OURS]

Once `n_m` is shared, "how many GPUs did Video Q/A use?" **has no answer in the formulation** — that
is what sharing means. `per_workflow_share` apportions by token mass (`Σ_{s,c} x^peak_{w,s,c,m} t_c /
Σ_{w'} …`), which is a reasonable convention and **not** in the paper. Labelled `[OURS]` everywhere it
appears, and `report.py` prints the disclaimer inline rather than in a footnote. It exists because
M3's tool-blindness skew is unequal between the two workflows (Video Q/A has three tool stages, Code
Gen one), so any per-workflow figure is a lower bound *by a different amount for each workflow* — a
caveat that must ride with the number.

---

## 9. Test list

Named for the property defended, in M3/M4 style.

**`tests/test_milp_multiplexing.py`** — is `µ_m` handled honestly?
- `test_omitting_the_mu_argument_is_an_error_not_a_default` (A43's precedent)
- `test_mu_equals_one_reproduces_milestone_4_exactly_on_a_single_workflow` (the regression anchor)
- `test_mu_below_one_relaxes_capacity_and_reduces_instance_counts` (§4.1's direction, pinned)
- `test_mu_above_one_is_permitted_and_reported_as_a_penalty_not_rejected` (we do not bound what the
  paper does not bound)
- `test_mu_is_never_a_field_of_MilpInputs_or_of_any_ProfileSet` (A42 — it is not a profile)
- `test_the_derived_mu_carries_its_two_assumptions_and_its_paper_version`
- `test_per_model_mu_is_unreachable_from_any_headline_path` (INVENTED quarantine, Q16's pattern)
- `test_mu_scaling_is_indistinguishable_from_scaling_theta` (A78's corollary, as executable algebra)

**`tests/test_milp_joint.py`** — does widening `W` do what A.5 says?
- `test_x_is_indexed_by_all_four_of_w_s_c_and_m` (A75 — restores what M4 elided)
- `test_demand_constraints_are_a_family_one_per_workflow_slo_pair`
- `test_n_m_is_shared_across_workflows_and_appears_once_per_model`
- `test_cost_budget_sums_over_both_workflows` (eq. (6)'s `Σ_w` is finally non-trivial)
- `test_each_workflow_keeps_its_own_tau_in_the_same_solve`
- `test_an_empty_admissible_set_for_one_workflow_names_itself_when_the_joint_solve_fails` (§3.3)
- `test_no_precedence_constraint_and_no_makespan_term_exist` (§10 — restated, not inherited)
- `test_the_milp_still_imports_nothing_from_development` (M4's boundary, unweakened)

**`tests/test_multiplexing_comparison.py`** — is the gain attributed or asserted?
- `test_joint_at_mu_one_saves_only_integrality_rounding` (**§4.5's prediction, falsifiable**)
- `test_all_three_arms_are_reported_and_neither_delta_is_presented_alone` (Q26)
- `test_the_calibration_target_is_never_reported_as_a_validation` (§4.3's circularity guard)
- `test_both_paper_versions_targets_are_shown_side_by_side` (A47)
- `test_a_uniform_mu_cannot_reproduce_all_three_table_2_reductions` (**A77, as a test**)
- `test_single_workflow_with_mu_below_one_still_gets_the_full_saving` (**A78.1 — the exogeneity
  defect, demonstrated: a multiplexing gain with nothing multiplexed**)

**`tests/test_milp_incoherence_joint.py`** — A74 under sharing.
- `test_foreign_model_mass_is_measured_per_workflow_whether_or_not_it_is_zero`
- `test_cross_workflow_and_within_workflow_incoherence_are_reported_separately`
- `test_incoherence_is_measured_for_all_three_arms_so_the_trend_is_visible`
- `test_model_module_still_never_references_the_coherence_predicate`

**`tests/test_milp_reporting_joint.py`**
- `test_no_headline_number_without_mu_choice_and_mu_provenance`
- `test_per_workflow_gpu_share_is_labelled_ours_and_carries_the_tool_blindness_caveat` (§8.1)
- `test_accuracy_objective_across_two_workflows_prints_the_incommensurability_warning` (A76)

---

## 10. What M5 deliberately does not do

- **No precedence, no makespan. Restated as a prohibition, not inherited silently.** A.5 has neither,
  and two workflows in one solve is exactly the situation where adding them would be tempting —
  Video Q/A's parallel branch is now in the same problem as Code Generation's total order. **M5 may
  not read `LogicalWorkflow.edges`, node lists, or any DAG structure.** If precedence were ever needed
  to make the joint solve feasible, *that is the finding* and it goes to `architecture-decisions.md`,
  not into `model.py`. (M4 §10.1, M1 `development/DESIGN.md` §8.1.)
- **No coherence constraint.** Measuring A74 is in scope; imposing a `c`↔`m` link is not.
- **No `µ` that depends on `x`.** §4.4 says that is what a real multiplexing model would need. Adding
  it would make eq. (3) non-linear and would repair the paper. It belongs to Arno's comparison
  system, not to this reproduction.
- **No instance-based provisioning model.** M5 makes the gap *demonstrable* (§4.5's arm B measures
  exactly what A.5's capacity model can express); it does not close it.
- **No inter-epoch coupling** (A69), **no CPU resource type** (A13), **no per-DAG-node assignment**,
  **no `M` re-indexing by operating point** (A37b) — all as M4.
- **No numerical validation against Tables 1–6 / Figures 7–14.** Still the explicitly deferred later
  phase. §7's comparison produces the arms and prints the paper's targets beside them; it does not
  adjudicate agreement.

---

## 11. File layout and build order

```
/optimization/milp/
  DESIGN_MULTIPLEXING.md ... this document
  mu.py .................... MuChoice, MuProvenance, the Table 2 derivation with its assumptions.
                             Imports MULTIPLEXING_REDUCTION_PCT; retypes no number. No solver logic.
  sets.py .................. EXTENDED: JointAdmissible over (W x S); merged ExclusionLedger;
                             EmptyAdmissibleSet now names the offending (w,s)
  model.py ................. EXTENDED: x re-keyed to (w,s,c,m); eqs. (1)/(2) become families;
                             _capacity_lhs() takes the per-model mu. NO_MULTIPLEXING retained.
  objectives.py ............ EXTENDED: (13)'s denominator now sums over W (A76 warning emitted)
  joint.py ................. solve_joint(profile_set, workflows, slo_mix, objective, budget, mu, epoch)
  compare.py ............... the three arms of Section 7; MultiplexingComparison
  report.py ................ EXTENDED: JointMilpResult rendering + the two new caveat gates
  critique/
    incoherence.py ......... EXTENDED: cross-workflow split + foreign_model_mass (A74). Quarantined.
    mu_per_model.py ........ [INVENTED] per-model mu experiments. Quarantined; test-enforced.
/tests/
  test_milp_multiplexing.py   test_milp_joint.py   test_multiplexing_comparison.py
  test_milp_incoherence_joint.py   test_milp_reporting_joint.py
```

**Build order, file by file with confirmation per `CLAUDE.md`:**
`mu.py` → `sets.py` (joint) → `model.py` (re-key) → `objectives.py` → `joint.py` → `compare.py` →
`report.py` → `critique/` → tests.

`mu.py` first mirrors M4 putting `A5.py` first and M3 putting `provenance.py` first: **the record of
what `µ_m` is and is not must exist in the repo before any code multiplies by it.**

Regression discipline: after each file, M4's 467 tests must still pass. `µ = 1` on a single workflow
must reproduce M4's numbers **bit for bit** — that is the anchor that proves the re-keying in
`model.py` changed the index space and nothing else.

---

## 12. Open decisions for Arno

**Q26 — is Table 2's "Murakkab Opt" the separate-solve arm (A) or the joint-solve arm (B)?**
*Recommendation: report both deltas, refuse to pick.* They differ by <1% if §4.5 is right, so the
choice costs almost nothing numerically — and showing both is what makes A.5's inability to express
sharing visible. Picking one would hide the finding at no benefit.

**Q27 — which `µ` is the headline?**
*Recommendation: `UNIFORM_FROM_TABLE_2` at the **[OSDI]** version (0.784), with the arXiv value
(0.789) reported beside it, and the `{0.6…1.0}` sweep as the sensitivity band.* Rationale: [OSDI] is
the version `CLAUDE.md` names as the paper, and A47 already requires both to be shown. **Alternative
worth considering:** make `NO_MULTIPLEXING` the headline and treat every `µ<1` run as a labelled
sensitivity — the most conservative option, and the one that claims least. I lean to the first
because the milestone's job is to reproduce Opt+Mult, but I would not argue hard.

**Q28 — the workflow demand ratio §4.3 never states.**
*Recommendation: native magnitudes from M3's arrival traces, nothing imposed, plus a ratio sweep in
the sensitivity report.* Any fixed ratio would be invented; native magnitudes invent nothing.

**Q29 — `MilpResult` widening: (i) mutate or (ii) add `JointMilpResult`?**
*Recommendation: (ii).* Preserves 467 passing tests and M4's single-workflow guarantees; the cost is
one extra dataclass and a `.per_slo()` adapter.

**Q30 — does the expected §4.3 infeasibility (A37, via the 30% latency-good share) block the headline
run?**
*Recommendation: run it, report `INFEASIBLE_STRUCTURAL` naming the offending `(w,s)`, then produce
the full three-arm comparison on `derived_tiers` as the reportable headline — clearly labelled as the
control set, never as the paper's tiers.* This is M4 §7.4's discipline applied to a joint run. **This
is the decision I am least sure of**, because it means the milestone's headline number comes from
`derived_tiers` rather than `baseline`, which is a larger claim than M4 ever made from that set.

**Q31 — should `µ > 1` be permitted?**
*Recommendation: yes, permit and report.* The paper places no bound on `µ_m`. Rejecting `µ > 1` would
be us adding a constraint A.5 does not have, on the strength of our own reading of Table 2's
direction. Permit it, never use it in a headline, and let the test pin that we did not silently bound
an unbounded symbol.

**Q32 — do A75–A78 go into `architecture-decisions.md` now, or after implementation confirms them?**
*Recommendation: A75 and A78 now* — both are settled by reading the code and the appendix, and A78 is
the strongest claim in the milestone. *A76 and A77 now as well* (both are arithmetic on published
numbers). **§4.5's <1% prediction waits for the measurement** — it is currently an argument, and the
project's standard is that findings of that weight are measured before they are filed.
