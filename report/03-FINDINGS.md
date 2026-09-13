# Part 3 — What Implementing Murakkab Revealed

*Five findings. Each states the claim, shows the measurement, and separates what is structural
(robust) from what is numeric (banded).*

---

## Finding 1 — A.5's structure produces zero multiplexing gain

### The claim

Murakkab's headline result is that multiplexing cuts GPUs by 21.6%. **Appendix A.5's formulation
cannot produce that gain.** Sharing model instances across workflows — which is what the paper
says multiplexing *is* — saves exactly nothing. The entire reported benefit enters through a
coefficient the paper defines in one clause and quantifies nowhere.

### What the paper says multiplexing is

Two statements, and they point at different things.

§3.3.1, Decision 4, describing what the optimizer produces:

> *"**Routing map**: the fraction of load from each (workflow, SLO)-pair routed to each
> provisioned instance, **encoding cross-workflow multiplexing**."*

So multiplexing is *colocation via the routing map* — packing several workflows' traffic onto
shared instances.

Appendix A.5, equation (3):

```
   μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c  ≤  n_m · θ_m        ∀m ∈ M
```

> *"where `μ_m` is the model-specific multiplexing factor."*

That clause is the paper's complete definition of `μ_m`. No value, no bound, no units, no
estimation method, in either the OSDI or arXiv version. It does not appear in §3.3's list of what
a profile contains.

### The measurement

We separated the two mechanisms the paper reports as one number. Three arms, on the §4.3 setup
(both workflows, 70/30 accuracy/latency, `good` tier), minimising energy:

```
   A. SEPARATE      each (workflow, SLO) solved alone, summed        μ = 1
   B. JOINT         all four solved together, sharing n_m            μ = 1
   C. JOINT + MULT  same problem                                     μ = 0.784

   ┌─────────────────────────────┬──────────┬────────────────────────────┐
   │ A. separate (4 solves)      │  418     │                            │
   │ B. joint, μ=1               │  418     │  sharing gain    +0.00%    │
   │ C. joint, μ=0.784           │  326     │  μ contribution +22.01%    │
   └─────────────────────────────┴──────────┴────────────────────────────┘
                                              combined        +22.01%
                                              paper reports    −21.6%
```

**Arm B minus arm A is exactly zero.** And the zero is not vacuous: in the joint solution,
Phi-4/H100/TP=1 genuinely carried load from *both* workflows simultaneously (n=89). Sharing
happened. It just saved nothing.

### Why it is zero — the structural argument

This is the part that would hold on real hardware, because it follows from the algebra.

Equation (3) is **linear in both `x` and `n`**. The instances a model needs are directly
proportional to the token demand landing on it. So:

```
   SEPARATE:   n = ceil(d₁/θ)  +  ceil(d₂/θ)
   JOINT:      n = ceil((d₁ + d₂)/θ)

   difference ≤ 1 instance per shared model  ── integrality rounding, nothing more
```

There is no statistical smoothing term, no queueing model, no burstiness parameter. Pooling two
workflows' demand onto one instance count saves only the fractional instance you would otherwise
round up twice. At this scale that is under one percent, and here it happened to be exactly zero.

**So A.5 has no mechanism by which colocation produces a resource saving.** The structure the
paper describes in §3.3.1 (routing map encoding multiplexing) is present, and it does nothing.

### Where the 21.6% comes from, and the circularity

If the structure cannot produce the gain, `μ_m` must. And `μ_m` is undefined — so we had to obtain
it somehow. The only source in the paper is Table 2 itself:

```
   Table 2 (verified cell by cell):
     Murakkab Opt        1164 GPUs    27.7 MWh    $57.2k
     Murakkab Opt+Mult    912 GPUs    22.1 MWh    $47.2k
                        −21.6%       −20.2%      −17.5%

   Under three stated assumptions, n_m scales with μ, so:
     μ = 1 − 0.216 = 0.784   [OSDI]
     μ = 1 − 0.211 = 0.789   [arXiv]
```

This is a legitimate `DERIVED` value — it is inferred from a published number under stated
assumptions, not invented. **But the calibration is then spent.** Reproducing 21.6% using a `μ`
fitted to 21.6% is arithmetic, not validation. Our implementation stamps every such result
`CALIBRATION SPENT` and refuses to present it as a reproduction.

We measured 22.01% against a fitted target of 21.6%; the 0.4-point gap is integrality rounding,
and it confirms only that the arithmetic is consistent.

### The deeper problem: `μ_m` is a parameter of the wrong object

Statistical multiplexing gain depends on **how many independent streams share an instance and how
bursty they are**. Those are properties of the *assignment* — of `x` — not of the model. A.5 makes
`μ` a parameter of `m` alone, so the gain is **exogenous**: the optimizer is told the answer rather
than deriving it from the sharing it chooses.

And there is an algebraic identity that makes this sharp:

```
   μ_m · Σ(...)  ≤  n_m · θ_m          is identical to
        Σ(...)  ≤  n_m · (θ_m / μ_m)
```

**Scaling `μ` is indistinguishable from scaling throughput.** Multiplexing, in A.5, is a
throughput bonus under a different name. We have a test that demonstrates this: setting μ = 0.5
halves the fleet exactly as doubling θ would.

### One more inconsistency

Table 2 reports three reductions: 21.6% GPUs, 20.2% energy, 17.5% cost. **No single uniform `μ`
reproduces all three.** If one coefficient explained the gain, all three would move together. They
do not, and the spread measures how much of the reported benefit is *not* capacity sharing.

### Confidence

- **Structural (robust):** eq. (3) is linear ⇒ colocation saves only integrality rounding. `μ`
  is algebraically a throughput scalar. Both follow from the text.
- **Measured (banded):** the 418 → 418 → 326 figures come from reconstructed profiles.
- **Verified:** Table 2's cells, §4.1's definitions of the two policies, eq. (3) verbatim.

---

## Finding 2 — eq. (5)'s blind spot is worth 0.3% or 69%, depending entirely on token count

### The claim

Equation (5) is Murakkab's *entire* model of end-to-end latency. It omits several real sources of
delay. **How much that matters varies by two orders of magnitude between the paper's own two
workflows**, and the discriminator is `t_c`. A single claim about "Murakkab's latency model" is too
coarse to be useful.

### What eq. (5) is

```
   x^peak = 0   if   ℓ^TTFT_m + t_c · ℓ^TPOT_m  >  τ_{w,s}
                     └────────┬──────────────┘
                     one model's time-to-first-token
                     plus its per-token time times the
                     WHOLE configuration's token count
```

What it contains: one prefill, one token stream, on one model.

What it does not contain: a sum over sub-tasks, a max over parallel branches, any term a tool
could occupy, or any notion of queueing.

### The measurement

We ran one request end to end through each workflow, walking the DAG and recording per-node
timings, then set the observed span beside what eq. (5) charged.

```
   VIDEO Q/A  (NVLM-D-72B/H100/TP=8, STT on, t_c = 194 tokens)

     scene_detect   ██                            2.0 s   TOOL  ← free to A.5
     frame_extract    █                           1.0 s   TOOL  ← free
     stt              ████                        4.0 s   TOOL  ← free
                          ▲ these two overlap; q_a waits for max(1,4)
     q_a                  ███                     2.74 s  LLM   ← all A.5 sees
     ──────────────────────────────────────────────────
     observed span                                8.74 s
     eq. (5) sees                                 2.74 s
     ══════════════════════════════════════════════════
     BLIND SPOT                                     69%


   CODE GENERATION  (DeepSeek-Qwen-32B/H100/TP=4, D=4 R=4, t_c = 39,969 tokens)

     propose_solutions  ████████████████████████ 16 LLM calls
     write_tests        ██                        1 LLM call
     execute_tests      ·                         0.8 s  TOOL  ← free to A.5
     rank_solutions     █                         1 LLM call
     ──────────────────────────────────────────────────
     observed span                             1550.69 s
     eq. (5) sees                              1547.02 s
     ══════════════════════════════════════════════════
     BLIND SPOT                                   0.24%
```

### Why the difference — and why this is the interesting part

The omissions are the *same* in both cases: the tool stages cost nothing, and eq. (5) charges one
prefill where the request pays many. What differs is the size of the term that *is* modelled.

```
   eq.(5)  =  ℓ^TTFT  +  t_c · ℓ^TPOT
              └──┬──┘     └─────┬────┘
              ~0.2 s       dominates when t_c is large

   Video Q/A:     0.24  +    194 × 0.0129  =  2.74 s   ← small; omissions dominate
   Code Gen:      0.22  + 39,969 × 0.0387  = 1547 s    ← huge; omissions vanish
```

When a configuration generates forty thousand tokens, a few seconds of tool time and seventeen
extra prefills disappear into rounding. When it generates two hundred, they are most of the
latency.

**This is why the choice of demonstration workflow matters so much**, and why Code Generation —
the workflow originally scoped for our end-to-end milestone — is the worst possible case for
showing the defect.

### Robustness

Video Q/A's 69% rests partly on tool service times that have **no paper source** and are marked
`INVENTED` in a quarantined module (the paper profiles no tool latency at all). So we tested the
conclusion across the full ±3× band those values carry:

```
   tool times ÷ 3   →  blind spot 42%
   tool times × 3   →  blind spot 87%
```

The conclusion survives the entire band. It rests on the *structure* — small `t_c`, three tool
stages — not on the magnitudes we chose.

### The sub-finding: the prefill undercount

Equation (5) charges exactly one `ℓ^TTFT_m`. A `D=4, R=4` Code Generation request makes 16 debate
calls plus test-writing plus ranking — **18 LLM invocations**, each paying a prefill.

```
   ttft_undercount = (invocations − 1) × ℓ^TTFT_m = 17 × 0.216 s = 3.67 s
```

This is the cleanest defect in the comparison: integers times a profiled value, no invented
magnitude anywhere. It is also **0.2%–2.6%** of eq. (5) across every Code Generation profile, for
the same reason as above. Real, exact, and not worth leading with — we corrected an earlier draft
that called it the milestone's strongest result.

### Confidence

- **Structural (robust):** eq. (5) has no per-node sum, no max over branches, no queueing term,
  and charges one prefill. These are facts about the equation.
- **Measured (banded):** 69% and 0.24%. The 69% survives ±3× on invented inputs.
- **Corrected:** the parallel-branch overlap is real (Listing 2) but §4.6's "full overlap"
  sentence describes two composed *workflows*, not these two nodes.

---

## Finding 3 — The auto-scaler cannot do what §3.4 claims

### The claim

§3.4 describes an auto-scaler that reacts on a seconds-to-minutes timescale. §4.7 assumes
provisioning takes twenty minutes. **These cannot both be true of a component that absorbs
short-term variance**, and the paper never reconciles them.

### The two sentences

> §3.4: *"an auto-scaler that monitors per-model instance load over **short windows (seconds to
> minutes)** and **rapidly scales out** when needed."*

> §4.7: *"Provisioning new instances (i.e., VM allocation, software setup, and model transfer to
> GPUs) is assumed to take **20 minutes** [31, 38, 62]."*

### The measurement

Same deployment plan, same load, same thresholds. Only the provisioning delay changes. The load is
a 2.5× spike lasting 200 seconds — shorter than the delay, which is the *normal* case for the
Azure traces the paper uses.

```
   load  ────┐                    ┌────────────────────────
             │                    │
             │   2.5× spike       │
             └────────────────────┘
             ▲          ▲         ▲
             │          │         └── spike ends
             │          └── autoscaler detects (60 s window), orders capacity
             │
             └── t = 200 s
                        └──────────── 20 minutes ─────────────► capacity arrives
                                                                (spike long over)

   ┌────────────────────────────────┬───────────────────────┐
   │ 20-min provisioning (§4.7)     │  81.5% SLO violations │
   │ instant provisioning (not the  │  36.5% SLO violations │
   │   paper's assumption)          │                       │
   └────────────────────────────────┴───────────────────────┘

   In the 20-minute case the scaler DID react:
     7 scale-out events · 49 instances requested and granted
     141,680 GPU-seconds burned on capacity that arrived too late to help
```

**During any spike shorter than twenty minutes, the auto-scaler is worse than useless.** It pays
for capacity that is never used.

### The only reconciliation, and why it does not close

The gap can only be bridged by capacity that already exists — pre-warmed spare. §3.4 names it:

> *"Murakkab also **maintains spare resources** to absorb demand spikes..."*

And never sizes it. There is no spare-capacity parameter in A.5: `B_g` is a hard budget and `α` is
a demand buffer, neither of which is idle standby capacity. So the auto-scaler's entire
responsiveness claim rests on a quantity that appears once in prose and nowhere in the model.

We default spare to **zero**, because zero is the formulation's own answer and any other value
would be repairing the contradiction rather than exhibiting it.

### A second runtime finding from the same experiment

In the same run, violations attributable to **queueing** outnumbered those attributable to token
variance by more than ten to one:

```
   violations from queueing        12,451
   violations from token variance   1,119
```

Equation (5) admits a configuration on `ℓ^TTFT + t_c·ℓ^TPOT ≤ τ` with **no queueing term at
all**. So the dominant cause of SLO violation at runtime is latency the optimizer structurally
cannot model. A plan can be feasible on paper and violate its SLO in the run purely through
waiting.

### Confidence

- **Structural (robust):** 20 minutes > 60 seconds. A.5 has no spare-capacity parameter. eq. (5)
  has no queueing term. All verifiable from the text.
- **Measured (banded, simulated):** 81.5% vs 36.5%. This is a simulator with an `[OURS]` FIFO
  queueing model and no batching or KV cache. The *ratio* between the two arms is the finding; the
  absolute violation rate is not a prediction about production.

---

## Finding 4 — The appendix is systematically narrower than the paper

### The claim

This is the most reusable observation from the project. It is not one defect but a **pattern**:
six distinct capabilities are described in the paper's prose and exercised in its evaluation, and
none of them can be written in Appendix A.5.

### The table

| What the paper describes | Where | What A.5 encodes | Gap |
|---|---|---|---|
| Agents *"may employ the same or different LLMs"* | §2.2 | one `m` per configuration | no per-node index |
| *"the chosen model or tool **for each executor**"* | §3.3.1, Decision 2 | one `m` per configuration | same |
| Executor assignment *"refined per SLO tier by optimizer"* | Table 1 | same | same |
| *"throughput envelope at which the profile satisfies the latency SLO"* | §3.3.1, Constraint 3 | `θ_m` is a **constant** | SLO-dependence lost |
| *"routing map … encoding cross-workflow multiplexing"* | §3.3.1, Decision 4 | a coefficient `μ_m` | mechanism unnamed (Finding 1) |
| *"We guarantee a basic accuracy tier even for latency SLO requests"* | §4.3 | one `τ` per `(w,s)` | cannot express two floors |
| CPU offload of Whisper and OmDet | §4.6, Figs 12b/12c | `G` is GPU-only | no CPU resource type |
| Transition overhead dominates Zone 1 | §4.7 | no switching cost | no inter-epoch coupling |

### Three of these in detail

**Per-node model assignment.** Three separate places promise it, including the paper's own
description of its flagship workflow: *"Each agent plays a unique role (e.g., algorithm developer,
unit tester) and **may employ the same or different LLMs**."* Against that: `x_{w,s,c,m}` has one
model index, and Table 6 prints one Model column per row — four debating agents, one model. The
capability is described three times and delivered zero times.

The reason is deeper than a missing index. **Murakkab decides at executor granularity and profiles
at configuration granularity.** Accuracy `a_c` is measured for a whole configuration running on
one model (Figure 2c, Table 6). There is no data for a mixed assignment, and there are 5³
combinations to measure for Code Generation alone. The profiling methodology cannot supply what
the decision requires — which is why our own reproduction was forced to fold the model *into* the
configuration knobs.

**SLO-dependent throughput.** §3.3.1 says the capacity envelope is *"the throughput envelope at
which the profile satisfies the latency SLO."* That makes `θ` a function of the tier. A.5 makes it
a constant `θ_m`. The consequence is measurable: Tables 5 and 6 report the *same*
`(model, GPU, TP)` at up to four different `(TPOT, TPS)` operating points — Phi-4/H100/TP=1 appears
at (0.0373, 757), (0.0165, 248), (0.0253, 552) and (0.0372, 755). A.5 can hold one. Choosing
which collapses a 6.8× throughput range on one profile, and every GPU count moves with it.

**Inter-epoch coupling.** §4.7 builds an entire sensitivity analysis on transition overhead —
*"Zone 1 (10–60 minutes): Buffer-dominated. Frequent reoptimization induces high transition
overhead… Frequent model and tool changes can also reduce KV cache efficiency."* A.5 has no
switching cost, no warm-start term, no minimum instance lifetime. Our optimizer will legally tear
down an entire fleet between two adjacent hours at zero modelled cost, and we measure the churn
because the formulation cannot see it.

### Why this framing is better than a list of bugs

Calling these "errors in the appendix" understates them. The paper's *system* is richer than its
*model of the system*. Every one of these is a place where the authors clearly understood
something — they evaluated it — and the formulation they published cannot represent it.

For anyone building on Murakkab, this is the most actionable finding in the report: **the
improvements are not new ideas, they are making A.5 encode what Sections 2–4 already say.** Part 4
develops that.

### Confidence

- **Structural (robust).** Every row is a comparison between two pieces of the paper's own text.
  Verified verbatim on 2026-09-13.

---

## Finding 5 — The `c`/`m` decoupling is exploited, not latent

### The claim

A.5 has no constraint linking a workflow configuration to the model profile serving it. This is
not a theoretical gap. Under the baseline profile set, **100% of allocated mass exploited it** —
and in the worst way available.

### The mechanism

```
   x^peak_{w,s,c,m}
                ▲ ▲
                │ └── model profile:  (Phi-4, H100, TP=1)
                └──── configuration:  (F=10, model=Gemma-3-27B, STT on)

   Nothing requires these to name the same model.
   The optimizer claims Gemma's accuracy a_c while paying Phi-4's θ, ℓ and e.
```

### The measurement

On `baseline`, video_qa, accuracy-`best`, minimising energy:

```
   incoherent mass: 100.0% of allocation
     62.69 req/s of video_qa(F=10, model=Gemma-3-27B, STT on)
       routed onto Phi-4/H100/TP=1
```

And it is worse than an accuracy mismatch. **Phi-4 appears in no Video Q/A configuration at all** —
it is a Code Generation model. A.5's `M` is a global set with nothing tying it to the workflow's
own `C_w`, so the formulation permits serving a video question-answering workflow on a text-only
LLM while claiming the multi-modal model's accuracy.

### Why the optimizer does this

Because it is rewarded for it. Phi-4/H100/TP=1 delivers 757 tokens/s **per GPU**;
DeepSeek-Qwen-32B/H100/TP=4 delivers 347.5. A cost- or energy-minimising objective will take the
cheaper throughput and keep the expensive accuracy every time, because no constraint connects
them.

### What we did about it

Nothing — deliberately. Adding `c.model == m.model_id` is a one-line fix and it is improvement #3
in Part 4. Under the standing policy we built a *measurement* instead, quarantined from the
optimizer by test, so that the defect is quantified rather than absorbed.

**Either outcome would have been a finding.** A zero would have meant the defect is latent under
this profile set — not that A.5 is sound. That it is 100% means the formulation is not merely
under-specified but actively exploitable by its own objectives.

### Confidence

- **Structural (robust):** A.5 contains no such constraint; `M` is global. Verifiable from the
  appendix.
- **Measured:** the 100% figure depends on our reconstructed throughput values. The *direction* —
  that a cost-minimising optimizer will exploit the gap — follows from the objective's shape.

---

## Summary: what the implementation bought us

Reading the paper gives you the architecture. Implementing it gives you five things reading cannot:

1. **The multiplexing result has no mechanism behind it.** You cannot see this by reading eq. (3);
   you see it by building the joint solve and measuring zero.
2. **The latency-model defect is workload-dependent by two orders of magnitude.** Reading gives
   you "eq. (5) is too simple"; implementing gives you "and it matters enormously here and not at
   all there, and here is why."
3. **The auto-scaler's two timescales are incompatible.** Both numbers are in the paper, in
   different sections, and nothing connects them on the page.
4. **The appendix is narrower than the paper** — visible only when you try to write code for the
   prose and find there is no variable for it.
5. **The `c`/`m` gap is exploited, not latent** — a fact about the optimum, obtainable only by
   solving.

Every one of these came from the discipline of *refusing to fix things*. An implementation that
repaired eq. (5), linked `c` to `m`, and picked a sensible `μ` would be a better system and would
have found none of this.
