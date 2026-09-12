# Progress Tracker

Read this file first every session. Update it whenever a milestone's status changes.
Do not skip ahead based on what "should" be next — only this file's status is authoritative.

## Status legend
- `not started`
- `design in progress`
- `design review pending` — a DESIGN.md exists, waiting on Arno's approval
- `design approved` — cleared to implement
- `implementation in progress`
- `execution review pending` — code exists, waiting on Arno's confirmation
- `done`

## Milestones

| # | Milestone | Phase | Status | Design doc | Notes |
|---|-----------|-------|--------|-------------|-------|
| 1 | Declarative spec + Workflow Orchestrator (Code Gen) | development | done | `/development/DESIGN.md` | Uses mock LLM client + mock Executor Library |
| 2 | Executor Library (mocked models/tools for Code Gen) | development | done | `/development/executor_lib/DESIGN.md` | Depends on M1's executor interface |
| 2b | Video Q/A executors + spec (M2 addendum) | development | done | `/development/executor_lib/DESIGN_VIDEO_QA.md` | Un-deferred 2026-09-10. Needs new types, a catalogue module, Listing 2's spec, and a resolution to A18 (existence knobs). Must precede M3 |
| 3 | Workflow Profiles + Model Profiles | optimization | done | `/optimization/profiles/DESIGN.md` | Profiles **both** workflows. Sourced from paper Tables 4–6, Figs 2–4. Design Q13–Q20 resolved and design approved by Arno 2026-09-11. §14 build order complete: all modules + `critique/` + 9 test files + generated `PROFILES.md`. 350 tests pass; 0 invented values in any `ProfileSet`. **Amended 2026-09-12 during M4:** A73 fixed `derived_tiers`, which was a copy of `baseline` (latency tiers were never derived) |
| 4 | MILP Optimizer (single-workflow) | optimization | done | `/optimization/milp/DESIGN.md` | Open-source solver (PuLP+CBC), Appendix A.5 formulation. A.5 transcribed verbatim in `/optimization/milp/A5_VERBATIM.md`; Q21 settled, A66/A57/A58 confirmed against source, A72 found. **Design approved by Arno 2026-09-12**; all five decisions Q21–Q25 resolved in DESIGN.md §14. Built in §13 order: 11 modules + 9 test files. **467 tests pass.** Findings: A66 confirmed, A72/A73/A74 new |
| 5 | MILP Optimizer (multiplexing / μ_m) | optimization | execution review pending | `/optimization/milp/DESIGN_MULTIPLEXING.md` | Mkb Opt+Mult — in scope from the start, not deferred. **Q26–Q32 decided by Claude 2026-09-12 on Arno's instruction ('your call, stay close to Murakkab')**; Q30 sharpened — the headline FINDING is `baseline`'s joint infeasibility (A37), with `derived_tiers` numbers always labelled control, never the headline |
| 6 | Workflow Registry + Auto-Scaler | execution | not started | — | Section 3.4 |
| 7 | End-to-end single-request run (Code Gen) | execution | not started | — | First point real numbers can be sanity-checked |
| — | Numerical validation vs. paper (Tables 1–6, Figs 7–14) | — | deferred | — | Explicitly a later phase, not part of M1–M7 |
| — | OS-log-analysis workflow (custom extension) | — | deferred | — | Own design session after Code Gen is solid |
| — | Math Q/A workflow | — | deferred | — | Video Q/A un-deferred 2026-09-10 (now M2b); Math Q/A still deferred |

## Gaps/improvements found so far

Keep in sync with entries added to Arno's `architecture-decisions.md` memory file.

- **M3** — A62 → added to `murakkab-formulation-narrower-than-system` as instance 5: eq. (5) is
  unevaluable for Llava-OneVision-7B, the model §4.6's parallelism study runs (no TTFT in either
  version). Sharpens the HEFT/precedence critique from "A.5 cannot express the overlap" to "A.5
  could not have screened this configuration at all".
- **M1** — MILP has no per-executor index: Table 1 and §3.3.1 Decision 2 promise per-DAG-node model
  assignment, but A.5's `x_{w,s,c,m}` has none. M1's per-node assignments therefore dead-end at M4.
- **M1** — Tool executors are unrepresentable in A.5 (no model profile, no tokens); Fig 1b's Python
  interpreter contributes zero cost/energy/latency/capacity. Generalizes the eq (5)/(9) latency gap.
- **M1** — `c` and `m` are unlinked in A.5: no constraint forces `a_c`/`t_c` and `θ_m`/`ℓ_m`/`e_m`
  to refer to the same model. Reproduced as-is per the "reproduce literally" policy.
- **M1** — §4.6 demonstrates DAG-parallel co-scheduling empirically, yet A.5 has no precedence
  constraint and no makespan term. Strongest evidence for the HEFT critique.
- **M1** — Code Generation is a total order (no parallel branch), so the precedence gap cannot be
  demonstrated on it; §4.6's own example needs Video Q/A. Scoping issue, see M5 note below.
- **Open (pre-M3)** — multiplexing (M5) cannot reproduce Table 2's gain with one workflow; `μ_m`
  is undefined in the paper; all M4 numbers rest on mocked profiles. Decide before M3 starts.
  *Status after M3's design:* the second workflow exists (M2b); `μ_m` stays undefined and out of
  M3 by A42, still M5's problem; the mocked-profile threat is answered by provenance enforcement
  plus swappable `ProfileSet`s and a seeded Monte-Carlo sweep (§9), not eliminated.
- **M2** — the paper's knob taxonomy contradicts itself (A12): §2.5 p.570 calls frame count an
  *agent-level* knob; §3.3.1 p.574 lists frames/STT/debaters/rounds together as the *workflow
  configuration*. Same knob, two levels, in a three-level taxonomy the paper presents as a finding.
- **M2** — A.5 has no CPU resource type at all (A13): `G`, `B_g`, `c_g` and constraint (7) are
  GPU-only, so the `cores` knob §3.2 exposes can never reach the MILP — yet §4.6 Figs 12b/12c
  *evaluate* CPU offload and report it meeting the latency SLO while cutting GPU usage.
- **M2** — A14: `llm_debate_testers` gives one Code Gen workflow two independent `(D,R)` pairs,
  while Table 6 has exactly one `Agents` and one `Rounds` column. Either testers don't debate
  (M1's A2) or Table 6 under-reports. Pinned by an executable test; **resolved at M3 by A45** — the
  column is `D`.
- **M2** — A18: on/off "existence" knobs (`stt_enabled`, §3.3.1) have no owner in the `ExecutorSpec`
  model — knobs attach to nodes, but this knob decides whether a node exists. Blocking for Video Q/A.
- **PATTERN (M1+M2)** — §4.6's evaluation systematically exercises capabilities Appendix A.5 cannot
  express: parallel co-scheduling with full overlap (no precedence/makespan term), CPU/GPU placement
  (no CPU resource type), and Tool execution (formulation is token-denominated throughout). The
  optimizer's formulation is narrower than the system the authors demonstrate. Strongest single
  framing for the senior-project comparison.
- **M2b** — A18/A24: **the paper cannot express its own knob.** §3.3.1 p.574 names STT on/off as a
  workflow-level decision and Fig 2a plots it, but §3.2 p.572 attaches knobs to models/tools and
  `stt_enabled=False` deletes a node — no executor can own the knob that annihilates it. Resolved by
  Option 5 (a configuration IS a DAG variant). Extends the PATTERN above from the MILP layer to the
  specification layer. Corroboration: Table 5's `STT` column is `Y` in every reported row (A28).
- **M2b** — A22: the paper describes Video Q/A three incompatible ways — Fig 1a + §2.2 (5 agents,
  incl. Object Detector), Listing 1 (5 nodes, `scenes, audio = …`), Listing 2 (4 sub-tasks, no object
  detection). Listing 2 taken as canonical; object detection folded into `frame_extract`.
- **M2b** — A25: Whisper/OmDet/CLIP are `TOOL` per §3.2, hence invisible to A.5 — yet §4.1 provisions
  them on GPUs and §4.6 offloads them to CPUs. A31: §3.3.1 Decision 2 promises "model **or tool** for
  each executor" per epoch, but tool identity is fixed at Phase 1 and A.5 has no tool variable.
- **M2b** — **Mock-selector bias, affects M7 credibility.** `MockLLMClient.keyword` scores overlap ÷
  candidate description length, so longer, more discriminating descriptions lose. It picks the
  invented `fixed_interval_segmenter` over the paper's `opencv_scene_detector` (7th), and nothing
  catches it — both type-check identically. Contrast its cross-workflow `q_a` error, which the type
  check does catch. Any M7 end-to-end number is driven by this selector over a half-invented
  catalogue. Fix is a real LLM client, not description tuning.
- **M3 OBLIGATION (from Q6/Option 5)** — `C_w` enumeration must prune the `stt` node. The paper
  describes no such step; label it as ours, not as reproduction. Also disclose that §3.2 says the
  orchestrator produces *a* logical workflow, singular, while M3 derives a second.
  *Discharged in M3's design as A50; `prune_stt()` is labelled `[OURS]`.*
- **M3** — A37: **the paper's printed latency SLO tiers are unreachable under its own eq. (5).**
  Table 5's `Best` row (Llava-OneVision-7B, F=1, H100, TP=4, TPOT 0.0044 s) against Figure 7b's
  printed `Best ≤0.5 s` needs `t_c ≲ 68` tokens; Figure 2b puts Video Q/A at 250-1000. Even at
  TTFT = 0 and the token floor the tier is missed (1.1 s). Code Gen shows the same ≈2× gap
  (11.3 s printed vs ≈20 s computed), and Figure 4a's leftmost plotted latency is ≈1.0 s, never 0.5.
  Not repaired: printed labels remain `baseline` (Q14), so M4's latency runs are *expected* to
  reject the configuration Table 5 says Murakkab chose.
- **M3** — A37b: **new PATTERN instance, and the cleanest.** Tables 5/6 report the same
  `(model, GPU, TP)` at 2-3 different `(TPOT, TPS)` operating points across SLO tiers, and A.2
  says so explicitly — but `θ_m` and `ℓ^TPOT_m` are constants of `m` in A.5. Two of the paper's own
  tables against its own appendix. Moves `n_m` by up to 4×. Resolved Q20: `M` is *not* re-indexed;
  one operating point per `m`, ties broken toward higher `θ_m` so any reported gap is a lower bound.
- **M3** — ~~A38~~ **WITHDRAWN 2026-09-12, replaced by a stronger result.** The §3.4 tier rule
  reproduces the printed tiers on **both** workflows — 8/8 values inside the ±0.5 pp digitization
  band (Code Gen +0.21/+0.33/+0.22/+0.27; Video +0.29/+0.30/−0.03/−0.08) — once the percentile is
  taken as `lower` (the largest profiled value at or below the position) rather than interpolated.
  That convention is forced by §3.4's own words, "values **available among the set of** all
  configurations": an interpolated tier is one no configuration achieves. The original claim (that
  a TP-feasibility-weighted population was required) was an artifact of interpolation in our
  reconstruction. Three corroborations fall out: the expansion is a no-op under uniform coverage;
  NVLM-D-72B's Figure 4b readings are **required** (without them `basic` misses by +10.04);
  and admitting DeepSeek-Llama-70B **breaks** two tiers, independently confirming Q13 and A54.
  Pinned by `tests/test_slo_tiers.py` (10 tests).
- **M3** — A53: **Phi-4 has four Figure 3 (GPU,TP) tuples, not eight** — the panel plots only
  diamonds (TP=1) and triangles (TP=2), verified at 22×, corroborated by every Phi-4 row in Table 6.
  Corrects DESIGN.md §6.1. **Load-bearing:** under the design's erroneous ×8 weighting the tier
  reconstruction fails (`basic` −2.87 pp).
- **M3** — A54/A55: **10 of 44 `a_c` values are Unavailable.** Figure 4b plots exactly ONE
  DeepSeek-Llama-70B marker (not 4×8), and Llama-3.2-90B is separable at only three levels in
  Figure 4a with STT hatching below resolution. Contradicts DESIGN.md §3.2's "every one of the 20
  has an accuracy source".
- **M3** — A56: the Figure 2b **tail** disagrees with §3.4's prose (p99 ≈1400 read vs 1200 stated,
  +17%, while p50 matches to −2.5%). No affine rescale fixes both, and `t_c`'s p90 lives in that tail.
- **M3** — A57: **`c_g` is per GPU, not per instance**, despite A.5 naming it "Cost per instance per
  second" — eqs. (6) and (12) both multiply it by `g_m`, as eq. (11) does to `e_m`. Same defect in
  `B_g` ("available resource *instances*" vs eq. (7)'s `Σ n_m·g_m ≤ B_g`, GPUs).
- **M3** — A58: **A.5 states four constraints twice** — eq. (4)≡(8), eq. (5)≡(9) verbatim, and
  eq. (6)≡(10) up to inlining `Cost_budget`. Its 13 numbered equations are 10 distinct ones.
- **M4** — A66 **CONFIRMED verbatim (Q21 settled, 2026-09-12): A.5's SLO filters constrain
  `x^peak` ONLY.** `x^avg` appears in exactly three places — eq. (2), eq. (6)/(10) and objective
  (13) — and **none is an SLO filter**. So: (i) objective (13) maximises `Σ x^avg·a_c` with nothing
  stopping it selecting configurations whose `a_c` is *below* `τ_{w,s}` — the one objective that
  optimises quality is the one the quality filter cannot reach; (ii) the cost budget charges
  possibly-SLO-violating average load; (iii) no constraint ties `x^avg` to `x^peak`, so a solution
  may serve peak on a compliant configuration and average on a cheaper non-compliant one. Also
  settled: `α` scopes both (1) and (2); eq. (3) has **no** average twin, so `n_m` is provisioned
  from peak alone; eq. (13)'s superscript is `avg`. Transcription in
  `/optimization/milp/A5_VERBATIM.md`. **A57 and A58 also confirmed exactly** against the source.
- **M5** — A80 **(MEASURED — the milestone's strongest result): A.5's structure produces ZERO
  multiplexing gain; the entire 21.6% enters through `μ`.** Three arms on `derived_tiers`,
  §4.3 setup, objective (11): separate-and-summed = **131 GPUs**; joint with `μ=1` (sharing `n_m`
  across both workflows) = **131 GPUs**, a gain of **+0.00%**; joint with `μ=0.784` = **102 GPUs**,
  −22.14%. And the zero is not vacuous — Phi-4/H100/TP=1 genuinely carries load from *both*
  workflows (n=89). The reason is structural: eq. (3) is linear in `x` and `n`, so pooling demand
  saves only `ceil((d1+d2)/θ)` vs `ceil(d1/θ)+ceil(d2/θ)` — at most one instance per shared model.
  **Table 2's headline is therefore not a property of the formulation but the value of a
  coefficient the paper never defines**, and which we could only obtain by fitting it to that same
  21.6% (calibration spent, A63's circularity in new clothes). Confirms §4.5's prediction, which
  said <1%; measured 0.00%.
- **M5** — A78: **`μ_m` is a parameter of the wrong object.** Multiplexing gain depends on how many
  independent streams share an instance and how bursty they are — properties of the *assignment*,
  not the model. A.5 makes it a parameter of `m` alone, so the gain is exogenous. Worse,
  `μ_m·Σ(...) ≤ n_m·θ_m` is algebraically identical to `Σ(...) ≤ n_m·(θ_m/μ_m)`: **scaling `μ` is
  indistinguishable from scaling `θ_m`.** Multiplexing, in A.5, is a throughput bonus under another
  name. Demonstrated by test (μ=0.5 halves the fleet exactly as doubling θ would).
- **M5** — A77: the three reported reductions (21.6 / 20.2 / 17.4) are **mutually inconsistent with
  any single uniform `μ`**. One aggregate number also under-determines 20 per-model unknowns by 17,
  so per-model `μ` is INVENTED and quarantined to `critique/` like Q16's tool times.
- **M5** — A76: **objective (13) averages incommensurable accuracies across workflows.** `a_c` is
  HumanEval pass@1 for Code Generation and VideoMME for Video Q/A; eq. (13) adds them and divides
  by total requests, so the optimizer trades quality across workflows at a meaningless exchange
  rate. Harmless at `|W|=1`; live in §4.3's own experiment.
- **M5** — A75: **M4's "one-line seam" claim held only half.** The `μ` scalar was a one-line change
  to `_capacity_lhs()`; the *mechanism* was not — M4 keyed `x` as `(c,m)`, eliding A.5's `w` and
  `s`, and emitted eqs. (1)/(2) as scalars rather than families. Restoring the full four-index form
  needed a new module. The failure mirrors the paper: **A.5 names the coefficient and never names
  the mechanism.**
- **M5** — **Q30 decided: the headline stays `baseline`.** §4.3's own experiment is
  **structurally infeasible on the paper's own printed SLO tiers** — its 30% low-latency share hits
  A37, and eq. (1)'s `for all` takes Code Generation down with Video Q/A even though Code Gen alone
  is feasible. That infeasibility IS the headline finding. `derived_tiers` runs the three arms as a
  clearly-labelled control and never as the paper's numbers.
- **M5 (design)** — A79 **(bug in the A73 fix, found while verifying M5's design, fixed):
  derived latency tiers were POOLED across workflows.** `_latency_population()` ignored the
  `workflow` argument its caller was looping over, so `derived_tiers` assigned Video Q/A and Code
  Generation the identical 2.938 s threshold — simultaneously too loose for one and impossible for
  the other. Figures 7b/8b print visibly different ladders (0.5–5.8 s vs 11.3–78.2 s), so a shared
  tier is wrong on its face. **Consequence before the fix:** the §4.3 joint experiment — M5's own
  headline setup — was unrunnable on the latency arm under *either* profile set. After the fix both
  workflows are feasible under `derived_tiers` (τ = 2.738 s / 74.368 s). Accuracy tiers were always
  per-workflow; only latency was pooled.
- **M4** — A74 **(headline result): A51 is EXPLOITED, not latent — 100% of allocated mass.** Under
  `baseline`, video_qa/accuracy-best, the optimizer routes **all** load from a Gemma-3-27B
  configuration onto **Phi-4** model profiles. And it is worse than an accuracy mismatch: Phi-4
  appears in **no Video Q/A configuration at all** — it is a Code Generation model. A.5's `M` is
  global and no constraint ties it to the workflow's own `C_w`, so the formulation permits serving
  a video workflow on a text-only LLM while claiming the video model's accuracy. Measured by
  `milp/critique/incoherence.py`, which the MILP cannot import (test-enforced).
- **M4** — A73 **(M3 defect found by M4, fixed): `derived_tiers` was a byte-for-byte copy of
  `baseline`.** `_slo_thresholds()` read `use_printed_latency` and then wrote the printed Figure
  7b label unconditionally; `derive_latency_tiers()` existed in `slo_tiers.py` and was never
  called. So DESIGN §7.4's control — "same code, same data, different `tau`" — **did not exist**,
  and every A37 claim rested on an unchecked assumption. Now derives latency tiers from the set's
  own eq. (5) population over coherent `(c,m)` pairs. Result: derived `best` = 2.551 s vs printed
  0.5 s, and latency/`best` is feasible under `derived_tiers` while infeasible under `baseline` —
  a 5.1× ratio, inside the 2–5× A37 predicted, which **corroborates our code rather than indicting
  it**.
- **M4** — implementation note: a **factor-60 arrival-rate bug** was caught by the §3.4 units
  guard. `sets.demand()` re-applied Figure 19's req/min→req/s conversion that M3's `arrivals.py`
  had already done, producing 1–2 GPUs instead of ~68 — a plausible small integer that nothing
  else would have flagged. `_as_req_per_second()` now reads the unit tag and refuses to guess.
- **M4** — A72: **A.5's cost CONSTRAINT and cost OBJECTIVE measure different things.** Eq. (6)/(10)
  charges `x^avg·(t_c/θ_m)·g_m·c_g` — GPU-seconds of *work consumed*. Objective (12) minimises
  `n_m·g_m·c_g` — the *fleet provisioned*, busy or idle. Nothing ties them together, so a solution
  can sit far under the consumption budget while provisioning an arbitrarily expensive fleet: idle
  capacity costs nothing in (6) and everything in (12). Compounded by A66 (`x^avg` is unfiltered and
  never drives `n_m`), the cost budget constrains a quantity that is nearly free to satisfy. Caught
  by checking M4's DESIGN.md against the verbatim source — the doc had written eq. (6) over `n_m`,
  i.e. objective (12)'s expression; corrected.
- **M4** — A67 **refined:** `Cost_budget` IS defined (`Σ_w τ_{w,cost}·Σ_s λ^avg_{w,s}`), but depends
  on **`τ_{w,cost}`** — a cost-type SLO threshold that §3.4 never defines (it gives four tiers for
  quality and latency only) and no table reports. Objective (13) and eqs. (6)/(10) remain
  uninstantiable from paper data; the blocker is one level deeper than first identified.
  `Cost_total` in (13) is also never defined.
- **M3** — A65 **(flow audit, fixed): `to_milp_inputs()` under-reported the data-excluded set.**
  It listed only configuration-side gaps (`t_c`, `a_c`, `theta_m`), so the **7 model profiles with
  no TTFT were invisible** — including Llava-OneVision-7B (A62). M4 would have applied eq. (5) to
  them and met an `Unavailable` mid-constraint. Now covers `l^TTFT_m`, `l^TPOT_m` and `e_m` too;
  the register went from 14 to 21 entries.
- **M3** — A64 **: two of DESIGN.md §9.2's seven named profile sets do not exist.** `maxthroughput`
  is deliberate — A37b put the operating-point collapse at the `to_milp_inputs()` boundary, so
  it's reachable as `operating_point=MAX_THROUGHPUT` and making it a set too would give one knob
  two homes. **`wide` needs Arno's decision:** §9.2 defines it as "baseline + the 14 extrapolated
  `t_c` of §5.4 with ±8× bands", but **Q19 superseded §5.4** — those 14 are `Unavailable` precisely
  so nothing is extrapolated. `profile_sets.py` separately claimed it enabled the aliased
  DeepSeek-Llama-70B profile (Q13/A34), a different thing. Neither is implemented and the
  `ASSUMED_ALIAS` provenance level is unused. Docstring corrected to state reality; a test pins
  the five that exist.
- **M3** — A63 **: DESIGN.md §5.2's `PAPER_FIGURE_LABEL` promotion would make two validations
  circular — NOT implemented, pending Arno's decision.** §5.2 proposes promoting four Code Gen
  `a_c` values to the *printed tier label values* (91.4 / 88.9 / 87.1 / 75.5) on the grounds that
  "the label prints the number the bar approximates". But §7.3's tier reconstruction *derives*
  those same labels from the `a_c` population. Feeding labels in makes the reconstruction
  self-fulfilling — `best` would go to residual 0.00 pp by construction — and the §5.2 check would
  compare four numbers against themselves. The two strongest validations in M3 would both become
  vacuous while still passing. Kept at `PAPER_FIGURE_READ`; `test_profile_contradiction.py`
  asserts no `a_c` carries `PAPER_FIGURE_LABEL`. **Second problem with §5.2 as written:** the tier
  label is a *threshold* (a population percentile, §3.4) while Table 6 names the configuration
  *chosen* there, which must CLEAR the threshold, not equal it. Equality only holds at `best`,
  where the threshold is the population max. Confirmed empirically — all four residuals are
  positive (+0.21, +0.33, +0.82, +0.27 pp), never negative.
- **M3** — A62: **eq. (5) is unevaluable for Llava-OneVision-7B** — the model §4.6 runs for its
  parallelism study (Figure 12a). No Figure 3 panel exists for it (A35) and no table in either
  version reports its TTFT (A36), so `l^TTFT_m` is `Unavailable` and the latency filter cannot be
  applied to it at all. A35/A36 recorded the missing data; this records the *consequence*: the
  paper demonstrates co-scheduling on a model its own optimizer could not admit under a latency
  SLO. Surfaced by `test_critical_path.py`, which had to stop naming that model and pick whichever
  pair the data supports.
- **M3** — A60: **two digitized CDF series came back non-monotone** — Figure 2d Gemma-3-27B D=2
  (p90 2069 > p95 2038) and Figure 2b Llava-OneVision-7B F=10 (p95 1271 > p99 1198). These are
  digitization artifacts, not findings: a percentile function is non-decreasing *by definition* of
  the CDF being plotted. Corrected by a running maximum on the point estimate only, clipped into
  each percentile's own band (inversions were 1.5% and 5.7%, both far inside the bands); the note
  on every moved value records its original. Caught by `test_token_distributions.py`, not by eye.
- **M3** — A61: **token count is NOT monotone in `F` for NVLM-D-72B**, and Figure 2b does not claim
  it is — its F=1 band [188, 199] and F=5 band [163, 195] overlap, which is why the model is
  recorded `inseparable`. Answer length is driven by the question, not the frame count. The test
  asserts monotonicity only across frame counts the figure actually separates; a blanket
  monotonicity assumption would have been a claim the source does not support.
- **M3** — A59 **corrects DESIGN.md §12.1**: that section's table lists `node_tokens` as `DERIVED`
  for both workflows ("code gen: split across debate/tests/rank"). **No such split is published.**
  Figure 2d's CDFs are per *request*, totalling every LLM call in the configuration, and Code
  Generation has three LLM nodes (`propose_solutions`, `write_tests`, `rank_solutions`) with no
  reported apportionment — any ratio would be INVENTED, which Q19 forbids outside `critique/`. Only
  Video Q/A decomposes exactly, and only because three of its four nodes are tools: the zeros are
  `DERIVED` and the remainder lands wholly on `q_a`, so `sum(node p90) == total p90` with no
  invented ratio. Code Gen's three LLM nodes are `Unavailable`. **Consequence:** the §12.1
  makespan-vs-eq.(5) comparison is structural on Video Q/A (as planned) and *not computable at all*
  on Code Generation — which is the milder loss, since Code Gen is a total order with no parallel
  branch. `rank_solutions` compounds it: it may be served by the `test_pass_rate_ranker` TOOL (zero
  tokens) or an LLM Ranker, and `C_w`'s knobs do not determine which (§12.3, point 5).
- **M3** — A45 **resolves M2's A14**: [OSDI] Table 6's column is `Agents`, [ARXIV] Table 5's is
  `Debaters`. The column is `D` — one `(D,R)` pair per Code Gen configuration, and
  `llm_debate_testers` is not representable in `C_w`. Closed by evidence, not judgement.
- **M3** — A46: the "90th percentile token generation load" sentence exists **only** in [OSDI]
  (p.576), with no arXiv counterpart. The `t_c = p90` rule shapes every capacity number in the
  reproduction and rests on one sentence in one version.
- **M3** — **all M4 resource numbers will be lower bounds, unequally.** 11 of 26 executors are
  tools with no profile (A25/A31), and the workflows are not affected equally — Video Q/A has three
  tool stages, Code Generation one. Any cross-workflow comparison inherits that skew and must say so.
- **M3** — A39/A40/A41: prompt tokens have no A.5 parameter and no data for either workflow; `c_g`
  is reported nowhere and Table 2 implies two different values for one cluster; Figure 3's
  "TPS per Wh" is dimensionally undefined, so `e_m` comes from Table 3 per GPU *type* and objective
  (11) cannot distinguish two models on the same GPU.
- **M3** — provenance outcome: of ~230 MILP-facing values, **0% invented**, ~14% `Unavailable`
  (accepted, Q19) — M4 must print the data-excluded set beside every headline number. The only
  invented values in the milestone are seven tool service times, quarantined from `to_milp_inputs()`
  by test (Q16), and the Video Q/A critical-path comparison is therefore **structural, not numeric**.

## Session resumption note

If you are starting a new session or continuing after a context/usage-limit reset:
1. Re-read `CLAUDE.md` and this file.
2. Find the first row above that is not `done`.
3. If its status is `design review pending` or `execution review pending`, do not proceed —
   surface that to Arno and wait, even if a long time has passed.
4. Otherwise, resume exactly at that row's status per the Milestone process in `CLAUDE.md`.
