# Appendix A.5, transcribed verbatim — the settlement of Q21

**Source:** [OSDI] Chaudhry et al., *OSDI '26*, pp.586–587 (PDF pages 20–21 of
`osdi26-chaudhry.pdf`, page offset +566). Extracted from the PDF text layer on 2026-09-12, not
retyped from memory. A.5 is identical in [ARXIV].

This file exists because M4's design could not be finished without it: three modelling forks
(Q21 a/b/c) turned on the exact superscripts A.5 uses, and every prior transcription in this repo
was partial. **It is a reference, not code.** `/optimization/milp/` implements from here.

---

## Sets and Indices

- `W`: workflows
- `S`: SLO types
- `M`: model profiles
- `C_w`: workflow configurations for `w`
- `G`: resource types

## Parameters

| Symbol | Paper's gloss |
|---|---|
| `λ^peak_{w,s}` | Peak request rate for workflow `w` with SLO `s` |
| `λ^avg_{w,s}` | Average request rate for workflow `w` with SLO `s` |
| `α` | Unified buffer factor (default 1.15) |
| `τ_{w,s}` | SLO threshold for workflow `w` and SLO type `s` |
| `a_c` | Accuracy of workflow configuration `c ∈ C_w` |
| `t_c` | Tokens per request for workflow configuration `c` |
| `θ_m` | Token throughput (tokens/sec) for model profile `m` |
| `ℓ^TTFT_m` | Time to first token for model profile `m` |
| `ℓ^TPOT_m` | Time per output token for model profile `m` |
| `g_m` | Parallelism for model `m` |
| `e_m` | Energy consumption (kWh) for model profile `m` |
| `c_g` | Cost per instance per second for resource type `g ∈ G` |
| `B_g` | Maximum available resource instances of type `g` |

## Decision Variables

- `n_m ∈ Z⁺` — Number of instances of model profile `m`
- `x^peak_{w,s,c,m} ∈ R⁺` — Peak load allocation from `(w,s,c)` to model `m`
- `x^avg_{w,s,c,m} ∈ R⁺` — Average load allocation from `(w,s,c)` to model `m`

## Constraints, verbatim

```
(1)  Demand Satisfaction (Peak):
     λ^peak_{w,s} ≤ Σ_{c∈C_w, m∈M} x^peak_{w,s,c,m} ≤ α · λ^peak_{w,s}      ∀w∈W, s∈S

(2)  Demand Satisfaction (Average):
     λ^avg_{w,s}  ≤ Σ_{c∈C_w, m∈M} x^avg_{w,s,c,m}  ≤ α · λ^avg_{w,s}       ∀w∈W, s∈S

(3)  Capacity Constraint with Multiplexing:
     µ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c  ≤  n_m · θ_m                    ∀m∈M
     "where µ_m is the model-specific multiplexing factor."

(4)  SLO Filtering, accuracy (s = max_accuracy):
     x^peak_{w,s,c,m} = 0    if a_c < τ_{w,s}

(5)  SLO Filtering, latency (s = min_latency):
     x^peak_{w,s,c,m} = 0    if ℓ^TTFT_m + t_c · ℓ^TPOT_m > τ_{w,s}

(6)  Cost Budget Constraint (if cost SLO is specified):
     Σ_{w,s,c,m} x^avg_{w,s,c,m} · (t_c / θ_m) · g_m · c_{g(m)}  ≤  Cost_budget
     where Cost_budget = Σ_{w∈W} τ_{w,cost} · Σ_s λ^avg_{w,s}

(7)  Resource Budget Constraint:
     Σ_{m : GPU(m)=g} n_m · g_m  ≤  B_g                                      ∀g∈G

(8)  x^peak_{w,s,c,m} = 0    if a_c < τ_{w,s}                       (accuracy)
(9)  x^peak_{w,s,c,m} = 0    if ℓ^TTFT_m + t_c ℓ^TPOT_m > τ_{w,s}   (latency)
(10) Σ_{w,s,c,m} x^avg_{w,s,c,m} (t_c/θ_m) g_m c_{g(m)} ≤ Σ_w τ_{w,cost} Σ_s λ^avg_{w,s}
```

## Objectives, verbatim

```
(11) Minimize Energy:   min Σ_m n_m e_m g_m
(12) Minimize Cost:     min Σ_m n_m g_m c_{g(m)}
(13) Maximize Accuracy Under a Cost Budget:
     max  ( Σ_{w,s,c,m} x^avg_{w,s,c,m} a_c ) / ( Σ_{w,s} λ^avg_{w,s} )  −  ε · Cost_total
     where ε = 0.001
```

## Solution Method

> "The formulated Mixed Integer Linear Program (MILP) is solved using Gurobi [37] with a time
> limit of 300 seconds. The solution yields an allocation of model instance counts `n*_m` and
> load distributions across model instances for all workflows."

---

## What this settles

**Q21(a) — does `α` scope both (1) and (2)? YES.** Both are two-sided with the same `α`. No
asymmetry between peak and average demand satisfaction.

**Q21(b) — does eq. (3) have an average-rate twin? NO.** The capacity constraint binds
`x^peak` only. `n_m` is therefore provisioned entirely from peak load; average load never sizes
the fleet.

**Q21(c) — eq. (13)'s superscript is `avg`.** The accuracy objective is a weighted mean of `a_c`
over the AVERAGE allocation.

**A66 — CONFIRMED, and it is worse than the unverified version suggested.** The SLO filters
(4)/(5) and their duplicates (8)/(9) constrain `x^peak` **only**. `x^avg` appears in exactly three
places — eq. (2), eq. (6)/(10), and objective (13) — and **none of them is an SLO filter**.
Consequences, all following directly from the text above:

1. **The accuracy objective is unfiltered.** Objective (13) maximises `Σ x^avg · a_c` with no
   constraint preventing `x^avg` from selecting configurations whose `a_c` is below `τ_{w,s}`.
   The one objective that optimises quality is the one the quality filter does not reach.
2. **The cost budget is unfiltered.** Eq. (6)/(10) charges `x^avg`, which may sit on
   SLO-violating configurations.
3. **Peak and average allocations are never tied to each other.** No constraint requires
   `x^avg ≤ x^peak`, nor that they use the same `(c,m)` support. A solution may serve peak load
   on an SLO-compliant configuration and average load on a cheaper non-compliant one.

**A58 — CONFIRMED exactly.** (4)≡(8) and (5)≡(9) are verbatim duplicates; (6)≡(10) differs only
by inlining `Cost_budget`. Thirteen numbered equations, ten distinct.

**A57 — CONFIRMED.** Eq. (12) is `Σ n_m g_m c_{g(m)}` and eq. (11) is `Σ n_m e_m g_m`: both
multiply by `g_m`, so `c_g` and `e_m` are **per GPU**, despite `c_g`'s gloss saying "per
instance". Eq. (7) is `Σ n_m g_m ≤ B_g`, so `B_g` counts **GPUs**, despite its gloss saying
"resource instances".

**A67 — REFINED, not withdrawn.** `Cost_budget` IS defined by the paper:
`Σ_w τ_{w,cost} · Σ_s λ^avg_{w,s}`. But it depends on **`τ_{w,cost}`**, a cost-type SLO threshold.
§3.4 (p.575) defines four tiers for *quality and end-to-end latency* only, and no table in either
version reports a cost tier. So objective (13) and constraints (6)/(10) remain uninstantiable
from the paper's data — the blocker is `τ_{w,cost}`, one level deeper than first thought.
`Cost_total` in (13) is likewise never defined; eq. (12)'s expression is the only candidate.

**µ_m — CONFIRMED present in eq. (3) and defined nowhere.** The paper says only "where µ_m is the
model-specific multiplexing factor". No value, bound, or estimation method appears in either
version, and §3.3's list of what a profile contains does not include it (A42). M4 sets `µ_m = 1`;
M5 owns the problem.
