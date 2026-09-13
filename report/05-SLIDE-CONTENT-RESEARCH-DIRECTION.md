# Murakkab reproduction and research direction — slide content draft

**Status:** discussion draft, 2026-09-13. This is slide *content* in Markdown, not a claim that the reproduction is complete or a selected thesis topic. Paper anchors refer to the local OSDI 2026 PDF, `C:/Users/darkn/Downloads/osdi26-chaudhry (1).pdf`. The authors' source and experimental infrastructure are unavailable here. Use [Part 1](01-WHAT-MURAKKAB-DOES.md) for the full system description and the [direct fidelity map](02A-DIRECT-FIDELITY-MAP.md) for current repository evidence.

The narrative should be: **recreate the described Murakkab as far as the paper allows → expose decisions the paper leaves open → change one decision method → compare fairly**. A limitation of the printed Appendix A.5 is not automatically a limitation of the authors' running system.

## 1. What Murakkab does

### Slide 1 — Murakkab's system boundary

**On slide**

- Developer submits a task and dependency specification; the platform chooses executors.
- Profiles connect workflow quality and token load to model latency, throughput and resource use.
- An optimizer chooses configurations and instances for SLOs; a registry and runtime serve requests and adapt to changing load.

**Presenter note.** Keep this to one architecture slide because [Part 1](01-WHAT-MURAKKAB-DOES.md) already develops it. Show the three phases from Table 1: development, optimization, execution. The research question is about decisions *inside* these components, not about replacing Murakkab with an unrelated architecture.

**Paper anchors:** §3.1–3.4; Table 1; Figs. 5–6.

## 2. What the paper does not specify deeply enough

### Slide 2 — Have we recreated everything the paper gives?

**On slide**

- **No, not yet.** We have a structural reproduction and an Appendix A.5 audit, but no author-equivalent serving stack or independent profiling measurements.
- Some published behaviors are described outside A.5: per-executor choices, load-dependent profiles, dynamic composition, CPU placement and runtime scaling.
- We need a paper-behavior baseline before treating deviations in our implementation as Murakkab's gaps.

**Presenter note.** “Covered” has three levels: represented in an interface, exercised in an end-to-end test, and matched to a published outcome. The current repository has many of the first, some of the second, and has not established the third across Tables 1–6 and Figures 7–14. The existing [fidelity chapter](02-REPRODUCTION-FIDELITY.md) is mainly a printed-A.5-to-code audit; it does not certify complete paper-behavior fidelity.

**Paper anchors:** Table 1; §3.3–3.4; §4.3, §4.6; Fig. 12; Appendix A.5. **Repo:** [direct map](02A-DIRECT-FIDELITY-MAP.md).

### Slide 3 — The coverage gate before making research claims

**On slide**

| Paper component | Minimum evidence before we call it reproduced | Current state |
|---|---|---|
| Development | Listing 2 DAG, executor assignment, type feedback, developer preferences | DAG and feedback represented; real LLM selection and preference consumption unpaired |
| Profiling | Same configurations, benchmark quality, token distributions, load-level model curves | Values reconstructed from plots; no independent measurements |
| Optimization | Feasible per-executor choices, SLO rules, resource units, per-tier plans | Printed A.5 implemented; broader paper behavior partly unpaired |
| Execution | Registry, request routing, batching, CPU/GPU placement, scaling | Registry and simulator exist; serving and Figure 12 placement unpaired |
| Outcomes | Same scenarios and metrics as §4 | Numerical comparison ledger still needed |

**Presenter note.** “Unpaired” means we have not yet created a same-conditions paper-versus-reproduction result; it is not a verdict against the paper. Use the [direct map](02A-DIRECT-FIDELITY-MAP.md) to trace each row to code.

**Paper anchors:** Listing 2; Table 1; §3.2–3.4; §4; Figs. 2–4, 12.

### Slide 4 — Open methods in development and profiling

**On slide**

| Paper tells us it can do this | What to confirm or choose to recreate it |
|---|---|
| Map new natural-language tasks to a finite executor library | Exact LLM and prompt/tool schema; choice and no-match criteria; retry limit and assignment-quality evidence |
| Build workflow profiles | Sample count, prompt set, benchmark version, treatment of dynamic paths, profile refresh rule |
| Build model profiles across load levels | How operating points are sampled and joined; when a profile is stale or unsafe to reuse |
| Compose new requests from existing workflows | Search space, compatibility checks, duplicate work, stopping rule and SLO estimate |

**Presenter note.** These are **implementation questions**, not claims that Murakkab cannot do them. §3.2 says the LLM receives available executors, descriptions and interfaces; it also specifies type checking, regeneration and developer onboarding. Candidate retrieval is a possible *improvement*, not a missing baseline step. See the [first paper confirmation](06-TOPIC-2-PAPER-CONFIRMATIONS.md). §3.3 names benchmark families and profile types; its full experiment protocol is the next claim to check.

**Paper anchors:** §3.2–3.4; Figs. 2–4, 5c; Appendix A.2–A.4.

### Slide 5 — Open methods in optimization and runtime

**On slide**

| Paper tells us it can do this | What to confirm or choose to recreate it |
|---|---|
| Jointly share capacity across workflow–SLO pairs | How `μ_m` is estimated, when sharing is safe, and how per-request routing realizes fractions |
| Meet latency while changing model/load/placement | How whole-workflow latency is estimated from executor paths and load-dependent profiles |
| Keep spare capacity and scale on short windows | How spare pools, thresholds, hysteresis, readiness and early reoptimization triggers are sized |
| Schedule heterogeneous branches | Placement and dispatch rule behind Figure 12's CPU/GPU choice; contention and batching policy |

**Presenter note.** A.5 explicitly gives equations and a named `μ_m`, but not a reproducible calibration procedure. §3.4 says thresholds follow performance-throughput curves and §4.7 supplies EWMA α=0.5 and a 20-minute provisioning assumption; those are *given* and should enter the baseline. Figure 12 proves that the paper considers CPU placement, even though A.5 does not fully encode it.

**Paper anchors:** §3.3.1; §3.4; §4.6–4.7; Table 1; Fig. 12; Appendix A.5 eq. (3).

### Slide 6 — How we handle missing detail without inventing Murakkab

**On slide**

1. **Specified:** implement and verify it as written, including details outside A.5.
2. **Described, method open:** implement a named baseline choice and record alternatives.
3. **Not reported or not measurable here:** mark it unavailable; bound conclusions accordingly.
4. **New method:** compare it against the paper-behavior baseline, not just against a weak or incomplete surrogate.

**Presenter note.** A deterministic simulator can test control logic and reveal sensitivities. It cannot establish the paper's production SLO or energy results without real serving measurements. Plot digitization checks transcription, not independent reproduction. This is the provenance discipline already used in [PROFILES.md](../PROFILES.md), extended to algorithms and experiments.

**Paper anchors:** §3.3–3.4; §4.1–4.8; Appendix A.5.

## 3. What we could improve inside Murakkab

### Slide 7 — Baseline completion versus improvement

**On slide**

| Baseline completion: make our replica do what Murakkab claims | Research improvement: change how Murakkab decides |
|---|---|
| Add CPU placement shown in Figure 12 | Choose CPU/GPU placement with a deadline-aware contention model |
| Honor the basic accuracy floor stated in §4.3 | Adapt quality spending per request while preserving the floor |
| Retain load-level profile points described in §3.3 | Profile selectively and optimize with uncertainty bounds |
| Connect logical DAG, chosen plan and runtime | Reuse plans or schedule branches to reduce response time and transition cost |

**Presenter note.** Several items in [Part 4's old improvement list](04-IMPROVEMENTS.md) are essential fidelity repairs or baseline completion, not yet research contributions. Keep them in engineering work; do not present them as the project's novelty. Improvements below are hypotheses until evaluated.

**Paper anchors:** §3.3–3.4; §4.3, §4.6; Fig. 12.

### Slide 8 — Candidate methods: workflow choice and answer quality

**On slide**

| Method to test inside Murakkab | Scenario where it may help | Main measurement |
|---|---|---|
| Confidence-aware executor selection with typed and semantic checks | New task descriptions that match several library executors | Assignment success, retries, onboarding time |
| Reuse/caching of validated workflow fragments | Repeated dynamic requests with similar subtasks | Composition latency, answer quality, avoided work |
| Per-request quality allocation across workflow nodes | Only one branch strongly affects the final answer | Quality at fixed cost and latency |
| Selective verification or fallback execution | Difficult requests where a cheap configuration may fail | Quality-floor violations and extra resource cost |

**Presenter note.** The baseline still needs the §3.2 orchestrator and §3.4 dynamic composition. The proposals change *ranking, reuse or selective execution*, rather than claiming to invent those components. “Confidence” requires a calibrated signal and must not be an untested LLM self-score.

**Paper anchors:** §3.2; §3.3.1; §3.4; Figs. 5c, 12.

### Slide 9 — Candidate methods: profiling and demand prediction

**On slide**

| Method to test inside Murakkab | Scenario where it may help | Main measurement |
|---|---|---|
| Active profiling: measure candidates near SLO or Pareto boundaries first | Large model/hardware/knob catalogue | Profiling GPU-hours at equal decision quality |
| Uncertainty-aware configuration selection | Sparse or noisy profile data | SLO violations and cost under held-out loads |
| Drift-triggered profile refresh | Model versions, traffic or serving stack change | Stale-profile duration, refresh cost, SLO risk |
| Error-aware forecast margin over paper's EWMA | Bursty or strongly seasonal arrivals | Forecast error, spare GPUs, dropped requests |

**Presenter note.** The baseline uses the paper's profiling categories and §4.7 EWMA. These methods aim to make profiling cheaper or decisions safer without discarding Murakkab's profile-guided architecture. Compare against equally fresh baseline profiles and use training/held-out trace splits.

**Paper anchors:** §3.3–3.4; §4.7; Figs. 2–4, 13, 19.

### Slide 10 — Candidate methods: joint optimization

**On slide**

| Method to test inside Murakkab | Scenario where it may help | Main measurement |
|---|---|---|
| Trace-aware multiplexing with a learned coincidence model | Workflows peak at different times | GPU-hours and tail SLOs on held-out traces |
| Deadline-aware DAG cost instead of a single token stream | Parallel branches and heterogeneous tools | End-to-end latency at fixed resource budget |
| Robust or chance-constrained allocation | Token and arrival distributions have heavy tails | Cost versus violation probability |
| Switching-aware plan optimization | Demand changes every epoch but provisioning is slow | Cost, churn, readiness and drops |
| Fairness-aware multi-tenant objective | One tenant otherwise takes scarce fast GPUs | Per-tenant SLOs and efficiency loss |

**Presenter note.** These are changes to the optimizer *after* its current paper-described decisions are represented coherently. Trace-aware multiplexing is not “fix missing `μ`”: it is a proposed alternative estimation/control method. DAG-aware allocation is different from merely walking the DAG correctly at runtime. Do not report a benefit until baseline and variant use the same profile and trace inputs.

**Paper anchors:** §3.3.1; §3.4; §4.3, §4.6–4.7; Table 2; Fig. 12; Appendix A.5.

### Slide 11 — Candidate methods: runtime and heterogeneous resources

**On slide**

| Method to test inside Murakkab | Scenario where it may help | Main measurement |
|---|---|---|
| Critical-path-aware branch scheduling | Mixed CPU/GPU tasks with slack in one branch | Makespan, GPU-hours, tool contention |
| Adaptive spare-pool and prewarming policy | Provisioning delay exceeds spike duration | Tail latency, drops, idle resource-time |
| SLO-aware batching and request routing | Mixed short and long requests share an instance | Throughput and per-tier tail latency |
| Plan reuse and staged rollout | Frequent reoptimization changes models or tools | Transition cost and SLO violations |
| Hosted/local model routing with rate-limit awareness | Accelerator scarcity or variable provider limits | Cost, quality, rate-limit failures |

**Presenter note.** Murakkab already has routing, batching, scaling, heterogeneous placement and a hosted-model extension in the paper. The proposals change *policies* for those capabilities. Real serving measurements are needed for claims about batching, power and tail latency; the simulator can screen candidates first.

**Paper anchors:** Table 1; §3.3.1–3.4; §4.6–4.7; Appendix A.5 hosted-model paragraph.

### Slide 12 — Which improvements help under which workload?

**On slide**

| If the main pressure is… | Most relevant method families | What might get worse |
|---|---|---|
| Many new workflows | Active profiling; executor retrieval; reusable fragments | Profiling and catalog maintenance |
| Bursty arrivals | Forecast margins; adaptive spare pool; prewarming | Idle GPUs and energy |
| Tight end-to-end deadlines | DAG-aware allocation; critical-path scheduling; batching control | Cost or quality if choices are too conservative |
| Multiple tenants | Robust allocation; fairness-aware objective; trace-aware sharing | Peak efficiency for the largest tenant |
| Frequent model/resource changes | Drift refresh; switching-aware plans; hosted/local routing | Transition overhead and instability |

**Presenter note.** This slide prevents a single “best improvement” claim. Select a workload assumption, then pick the policy designed for it. Each method should be tested on scenarios where it may help *and* where it may hurt.

**Paper anchors:** §2.5; §3.3–3.4; §4.3–4.7.

## 4. What we may actually tackle — decision still open

### Slide 13 — Four possible project cores

**On slide**

| Candidate project core | Clear change inside Murakkab | Key prerequisite | Feasible first experiment |
|---|---|---|---|
| **A. Uncertainty-aware profiling** | Select which configurations/load points to measure, then allocate with confidence bounds | Reconstruct profile and SLO joins faithfully | Hide selected profile points; compare profiling cost and decisions on held-out points |
| **B. Trace-aware multiplexing** | Estimate sharing from workload coincidence rather than a fixed fitted factor | Match §4.3's separate-pair and joint baselines | Train on one trace segment; compare GPU-hours and SLOs on another |
| **C. Deadline-aware scheduling** | Choose node placement/order using critical path and resource contention | Recreate Figure 12 choices and tool service profiles | Composite Video Q/A + Code Generation, then vary CPU/GPU contention |
| **D. Adaptive spare capacity** | Size and prewarm reserve from forecast error and startup delay | Match baseline EWMA, thresholds and provisioning behavior | Burst replay with fixed budget; compare tail latency, drops and idle GPU-hours |

**Presenter note.** These are **discussion candidates**, not selected conclusions. A may be easiest to evaluate without a full serving engine; C is closest to the workflow-architecture theme but needs tool and hardware measurements. B and D fit the multi-tenant runtime story. Do not rank them solely from our current simulator numbers.

**Paper anchors:** §3.3–3.4; §4.3, §4.6–4.7; Table 2; Figs. 12–13.

### Slide 14 — Decision rule for the project focus

**On slide**

Choose the focus only after asking:

1. Can we recreate a credible paper-behavior baseline for this component?
2. Can we change **one** method while holding workloads, profiles, hardware assumptions and SLOs fixed?
3. Can we measure the proposed benefit with available data or hardware?
4. Does the method help in a named scenario without unacceptable loss in another?

**Presenter note.** Record a before/after result for quality, end-to-end latency, SLO violations, GPU-hours, energy/cost, and overhead where each is measurable. Separate real measurements from reconstructed or simulated values. The project should emerge from that evidence, not from assuming the paper's unspecified details are defects.

**Paper anchors:** §4.1–4.8 for evaluation setups and metrics.

## Evidence work required before finalizing these slides

### Paper recheck queue for slides 4–5

| Statement we can make now | Detail that still needs a second source check |
|---|---|
| Appendix A.5 names `μ_m` as a model-specific multiplexing factor but gives no calibration procedure there. | Search the full OSDI text, appendices and any author artifact for a separate measurement or fitting procedure before calling it paper-wide unspecified. |
| §3.2 describes LLM tool-calling, type feedback and onboarding when no executor matches. | Checked paper-wide for the first [confirmation](06-TOPIC-2-PAPER-CONFIRMATIONS.md): the concrete model/prompt, choice criteria, retry limit and assignment evaluation remain unreported in the OSDI text. Recheck any separate author artifact if one becomes available. |
| §3.3 gives profile categories and benchmark examples, with load-level model curves. | Check appendices and benchmark setup for exact sample counts, prompts, model versions, load-point selection and profile-refresh rules. |
| §3.4 describes dynamic composition, spare resources and early reoptimization; Table 1 names batch composition. | Check whether a search algorithm, reserve size, trigger threshold or batching policy is specified elsewhere in the paper. |
| §4.6 evaluates three CPU/GPU placements and reports a chosen one. | Check whether the authors specify a general scheduler or only describe this evaluated choice. |

The slide wording should become firmer only after these checks. If a method is specified elsewhere, move it into the baseline reproduction checklist; do not present it as an open method.

| Evidence pair | Why it comes first | Completion condition |
|---|---|---|
| Listing 2 ↔ parsed DAG and executor assignments | Establishes development semantics | Same nodes, edges and request boundary; identify mock-selector substitutions |
| Figures 2–4 and Tables 5–6 ↔ reconstructed profile ledger | Establishes candidate quality/load/latency inputs | Every compared configuration and operating point has source, units and uncertainty/missingness |
| Table 1 and §3.3.1 ↔ optimizer output and executable plan | Establishes that all described decisions are represented | Per-node choices, tier floors, resource counting and plan materialization can be traced |
| Figure 12 ↔ composite request placement and timeline | Tests paper-described CPU/GPU scheduling | Same branch structure and viable placements; real timing if available, otherwise clearly simulated |
| Table 2 / §4.3 ↔ separate and joint 24-hour experiments | Tests the sharing baseline | Four separate workflow–SLO pairs; same objective, 70/30 mix, trace horizon and GPU accounting; no target-fitted validation |
| Figure 13 / §4.7 ↔ epoch/auto-scaling experiment | Tests runtime adaptation | Past-only EWMA, 20-minute provisioning assumption, explicit spare capacity and transition accounting |

**Revision rule:** when a paper or repository check changes one row, update the slide claim and its evidence pair together. Do not promote a proposed improvement into a measured finding until the baseline and ablation exist.
