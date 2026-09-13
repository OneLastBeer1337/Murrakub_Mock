# Direct fidelity map: Murakkab vs this reproduction

**Purpose.** This is the reading map before we try to reproduce a result or propose an improvement. For each component, it puts the *system described by Murakkab* beside the *behavior implemented here*. A missing detail in Appendix A.5 is not evidence that the authors' runtime lacked that behavior.

**Reference.** Chaudhry et al., *Murakkab: Resource-Efficient Agentic Workflow Orchestration in Cloud Platforms*, OSDI 2026, local source `C:/Users/darkn/Downloads/osdi26-chaudhry (1).pdf`. Section, listing, table, and figure numbers below refer to that version. The authors' implementation is not available here; "Murakkab" below means the **published design and measurements**, not inspected author code. Repository observations are as of 2026-09-13. The earlier [context review](../MURAKKAB_CONTEXT_REVIEW.md) was written before some execution and reporting code changed, so this map uses current code where they differ.

**At a glance:** the reproduction has a credible *shape* of Murakkab's three phases, but it is strongest as a structural and A.5 audit. The largest fidelity gaps are (1) reconstructed rather than measured profiles, (2) optimization choices that do not yet represent all paper-described per-executor and load-level behavior, and (3) a simulated runtime instead of the paper's serving stack. Published outcome comparisons remain to be paired.

```text
Paper:   specification → executor DAG → measured profiles → optimizer → deployment → serving
Repo:    specification → mock-assigned DAG → reconstructed profiles → A.5 MILP → registry → simulator
          D1–D2              O1–O3                    O4–O5         E1          E2–E3
```

## The three things being compared

| Layer | What it can tell us | What it cannot tell us |
|---|---|---|
| **P — paper-described Murakkab** | Intended components, interfaces, behavior, evaluation setup and reported outcomes (§3, §4, Table 1). | Exact hidden implementation or an unreported algorithm. |
| **A — printed Appendix A.5** | The variables and constraints the paper explicitly writes down. | All decisions in the running system; Table 1 and Figure 12 describe behavior outside these equations. |
| **R — this reproduction** | What this repository actually computes or simulates. | Whether Murakkab's production system would produce the same runtime, quality, energy or costs. |

Read each row as **P → R**, with **A** called out only when it explains a choice or limitation. Status describes *reproduction fidelity*, not whether the paper's design is good. **Represented** means a structural interface or rule exists; **partial** means an important paper behavior is unimplemented or simulated; **unpaired** means no comparable outcome has yet been established.

## Component-by-component comparison

| ID | Component and paper anchor | P: Murakkab as described | R: what is present here | Fidelity and next check |
|---|---|---|---|---|
| D1 | Declarative specification, Listing 2; §3.2 | Developer states tasks and data dependencies, omitting model, frame count and hardware defaults; preferences may be supplied.f | [Video Q/A](../development/specs/video_qa.py) and [Code Generation](../development/specs/code_generation.py) specs are parsed into a DAG. [OrchestrationResult](../development/orchestrator.py) carries preferences alongside it. | **Represented structurally.** Compare the parsed Video Q/A edges and request boundary with Listing 2; then trace whether preferences affect optimization (currently no verified consumer). |
| D2 | Executor library and orchestrator, §3.2; Table 1 | A finite library of LLMs, compositions and tools; an LLM with tool calling assigns an executor per node, type checks, retries with feedback and asks for onboarding if no match exists. | [Executor catalog](../development/executor_library.py), [orchestrator](../development/orchestrator.py), [type checker](../development/type_check.py) and an abstract client exist. The exercised client is [MockLLMClient](../shared/llm_client.py), including keyword and fixture modes. | **Partial.** Control flow is represented; selection quality and author-like tool calling are unpaired. Separate paper-grounded catalog fixtures from invented diagnostic candidates before measuring assignment fidelity. |
| O1 | Workflow profiles, §3.3; Figs. 2a–d, 4a–b | Measure quality and executor-level token load for each workflow configuration; these measurements inform SLO and capacity decisions. | [Workflow profiles](../optimization/profiles/workflow_profiles.py), configuration enumeration and a [provenance ledger](../PROFILES.md) reconstruct values from printed figures; missing fields remain unavailable. | **Partial, reconstructed.** The profile data structure exists, but quality and token load have not been independently measured. See [O1 explained](#o1-explained-workflow-profiles). |
| O2 | Model profiles, §3.3, A.2–A.3; Tables 5–6 | Profile TTFT, TPOT, throughput, energy and cost across model/GPU/parallelism **and load levels**; operating point changes with SLO. | [Model profile builder](../optimization/profiles/model_profiles.py) retains curve information but selects one table operating point for each model/GPU/TP key for MILP input. | **Partial.** Compare all reported operating points for the same tuple and check the TTFT/TPOT/TPS join at one load before using profile-based numerical claims. A.5's profile set does not by itself require discarding these points. |
| O3 | Forecast and epoch, §3.4, §4.7; Fig. 19 | Previous epochs predict next-epoch demand; the paper evaluates EWMA α=0.5 and a 60-minute default epoch. | [EwmaProjector](../execution/projection.py) is past-only. [build_arrivals](../optimization/profiles/arrivals.py) also computes same-epoch maxima/means from the digitized trace for offline optimization inputs. | **Partial.** Keep the oracle replay and forecast experiment separate. A paper-aligned prediction pair must show which past samples were visible at each decision time. |
| O4 | Configuration, SLO and resource optimization, §3.3.1; Table 1; A.5 | Choose workflow knobs, final model/tool per executor, GPU type/parallelism, instance counts and routing while meeting demand and SLOs. | [MILP](../optimization/milp/) implements printed A.5 over reconstructed profiles. Its `(workflow,SLO,configuration,model-profile)` allocation lacks an explicit per-node model index; the reproduction allows independent `c × m` combinations. | **Partial.** This is a faithful *formula audit*, not a complete paper-behavior baseline. Test configuration/model compatibility, preferences, tier floors, units and per-node decisions against §3.3.1 before comparing outcomes. Do not infer that the author runtime used incoherent pairs. |
| O5 | Sharing/multiplexing, §3.3.1, §4.3; Table 2 | `Mkb Opt` optimizes **each workflow–SLO pair** separately; `Mkb Opt+Mult` jointly optimizes across pairs. Table 2 reports GPU, energy and cost reductions over the trace. | [Comparison](../optimization/milp/compare.py) has separate, joint and coefficient-adjusted arms. Its "separate" arm currently groups both SLOs of a workflow in one solve; `μ` may be fitted from Table 2. | **Unpaired.** Rebuild the paper's pair-separated arm, use the same 24-hour cost objective and SLO mix, and calibrate any `μ` without using the held-out target. One snapshot or fitted target is not a Table 2 reproduction. |
| E1 | Executable plan and registry, §3.3–3.4; Fig. 6 | The optimizer generates executable workflows for valid SLO tiers; requests use the registry rather than rerunning optimization. | [Registry](../execution/registry.py) stores a solved plan and routing fractions by workflow/SLO/tier; [dispatch](../execution/dispatch.py) turns fractions into request choices. | **Represented structurally, partial operationally.** Check that chosen configuration, node executors, profile, SLO and deployment readiness survive the full logical-workflow → plan → registry handoff. |
| E2 | DAG execution and scheduler, §3.4, §4.6; Fig. 12 | Execute dependencies with overlapping branches; Figure 12 compares placements and picks OmDet on GPU, Whisper on CPU, Gemma on GPU for a composite request. | [workflow_run](../execution/workflow_run.py) walks dependencies and simulates sibling overlap. It fixes `(c,m)` before the walk, uses typed stubs and has no real tool/LLM execution or resource-aware placement. | **Partial.** Dependency structure is testable; Figure 12 placement, CPU use, makespan and measured energy are unpaired. The missing DAG terms in A.5 do **not** mean Murakkab lacks runtime scheduling. |
| E3 | Serving, batching and auto-scaling, Table 1; §3.4, §4.7 | Per-instance batch composition and per-request routing run continuously; a short load window, spare capacity and reactive scaling sit alongside hourly reoptimization. | [Runner](../execution/runner.py), [auto-scaler](../execution/autoscaler.py) and [simulated fleet](../execution/sim/fleet.py) exercise control rules with model-based service times and a provisioning delay. There is no serving engine, real batching, KV cache, GPU measurement or network. | **Partial, simulated.** Validate control events and capacity accounting first. SLO violation rates from this simulator are counterfactuals, not measurements of Murakkab's runtime. |
| V1 | Evaluation coverage, §4; Tables 1–6; Figs. 7–14 | The paper evaluates single-workflow SLOs, multi-workflow sharing, changing budgets, dynamic composition/scheduling and epoch sensitivity. | The repository centers on Video Q/A and Code Generation; Math Q/A, the OS-log extension and dynamic coding study are not reproduced. Existing tests mainly establish internal consistency and selected structural behavior. | **Unpaired.** Build a published-result ledger before using the existing findings as comparative evidence. |

## O1 explained: workflow profiles

A **workflow configuration** is one set of application choices. For Video Q/A, this includes the model, number of frames (`F`), and whether speech-to-text (`STT`) is used. For Code Generation, it includes the model, number of debaters (`D`), and debate rounds (`R`). The repository [enumerates](../optimization/profiles/enumerate_cw.py) 24 Video Q/A and 20 Code Generation configurations. This is a chosen, finite reconstruction of the configuration space, not proof that it contains every configuration the authors tested.

For each configuration, Murakkab's §3.3 workflow profiling asks two practical questions: **How good is the answer?** and **how much work does the configuration generate?** Quality comes from running benchmark examples against ground truth (VideoMME for Video Q/A; HumanEval for Code Generation). Load includes prompt and completion tokens at the executor level. Keeping these separate matters: a configuration can improve quality while producing more tokens, which increases the serving capacity it needs. The *model profile* in O2 answers a different question—how quickly and at what resource cost a chosen model/hardware setup handles those tokens.

This repository stores a configuration's quality as `a_c` and a completion-token distribution. For the printed A.5 optimizer, it takes the distribution's **90th percentile** as `t_c` (the OSDI paper says allocation uses p90 in §4.1). `a_c` is used for accuracy eligibility or objectives; `t_c` helps convert request rate into token demand and estimated latency. The distribution remains in the profile because p50, p90 and p99 are different workload questions. A single token average would hide spikes.

Here is one **paper-to-repository reading pair**, not an independent performance experiment:

| Same configuration | Paper source | Repository value | Meaning |
|---|---|---|---|
| Video Q/A, Gemma-3-27B, `F=5`, `STT=on` | Figure 2a accuracy bar | `a_c = 64.7%`, figure-reading band `64.2–65.2%` | Estimated answer accuracy of that configuration on the paper's benchmark. |
| Same configuration | Figure 2b completion-token CDF | `t_c (p90) = 639` completion tokens, reading band `603–648` | Estimated token load that 90% of plotted requests do not exceed. |

Both numbers come from **reading the published plots**, as recorded in [PROFILES.md](../PROFILES.md). The bands express graph-reading resolution; they are not statistical confidence intervals for a new benchmark run. No Gemma inference, VideoMME scoring or token logging was rerun here. Thus matching the plot shows **transcription fidelity**, while matching Murakkab's measured behavior remains untested.

The missing-data ledger makes this boundary visible. In the current `baseline` set, `a_c` is unavailable for **10 of 44** enumerated configurations and `t_c` for **14 of 44** because the figures do not resolve or show those exact combinations. Prompt-token distributions are unavailable for all 44, even though §3.3 says workflow profiles include them. For example, Figure 2d has no Code Generation completion-token CDF for NVLM-D-72B; assigning it another model's token count would silently manufacture a profile. [WorkflowProfile.to_milp()](../optimization/profiles/schema.py) therefore passes the absence through for exclusion and reporting instead of using zero.

**What to compare next for O1:** first audit each enumerated `(workflow, model, knobs)` against its exact plot point or CDF and its reading band, marking absent combinations. Then run the same benchmark/configuration independently with recorded model version, prompts, examples and scoring rule, and compare accuracy and token percentiles with the paper. If those experimental details cannot be matched, report the new run as a **related measurement** rather than a reproduction of the paper's profile. Keep Table 5/6 latency and throughput checks in O2 so workflow load and hardware performance are not mixed.

## What these rows mean for the current report

The [existing fidelity chapter](02-REPRODUCTION-FIDELITY.md) is valuable as an **A → R audit**: it explains deliberate adherence to the printed formulation and the consequences of no GPUs. Its language should not be read as a full **P → R comparison**. In particular:

- "A.5 has no DAG makespan or CPU resource" means the *printed model* does not spell out those decisions. §3.4 and Figure 12 show scheduling and CPU placement in the *paper-described system*. Implementing them would complete the paper-behavior baseline before it counts as an improvement.
- An incoherent `c × m` allocation is a reproducible property of this unrestricted formulation. The paper describes feasible model/profile choices; author-runtime behavior is unknown.
- A one-point throughput collapse is a repository choice. Multiple load operating points are described in §3.3 and A.2–A.3, even though A.5 leaves their encoding unclear.
- The statement that `μ=1` gives zero sharing is an observation from one experiment, not a general algebraic impossibility; integer rounding can create a gain. A `μ` fitted to Table 2 cannot validate Table 2.
- The 2026-09-12 [context review](../MURAKKAB_CONTEXT_REVIEW.md) caught a GPU-count bug; [MILP result](../optimization/milp/report.py) and [joint result](../optimization/milp/joint.py) now multiply instances by tensor parallelism. [Registry.total_gpus](../execution/registry.py) still sums instances, so GPU totals must be checked at the reporting boundary used by each experiment.

These distinctions leave three legitimate tracks: **printed-A.5 audit**, **paper-behavior baseline**, and **component improvement**. Results from one track should not be labeled as results from another.

## How the next finding pairs should be built

For each row above, make one small evidence pair before making a broad claim. Each pair needs:

1. **Same question:** paper figure/table/claim and the exact reproduction output being compared.
2. **Same conditions:** workflow, SLO, objective, time horizon, traffic, model candidates, hardware and resource budget. Put mismatches in the table, not a footnote.
3. **Source and implementation:** precise paper section/row, code path, command/fixture and profile provenance.
4. **Comparable quantities:** units and counting rule (especially instances vs GPUs, rate vs epoch cost, measured vs simulated latency).
5. **Observed difference and explanation:** numerical delta only when the first four items permit it; otherwise state **unpaired** and name the missing input.
6. **Improvement experiment:** change one component in a paper-behavior baseline, retain conditions and measure the same outcomes on held-out inputs.

Start with three concrete pairs: **Listing 2 ↔ parsed Video Q/A DAG**, **Table 5/6 rows ↔ profile operating points**, then **Figure 12 ↔ dependency and placement trace**. These expose interface fidelity before attempting Table 2. After the profile and SLO inputs are reconciled, pair **Table 2 ↔ four workflow–SLO solves vs joint solve over 24 hours**. A pair can establish a structural match even when hardware-dependent metrics remain unavailable.

Suggested record for the next document:

```text
Pair ID / component:
Paper anchor and exact target:
Reproduction command, output and code:
Conditions held equal:
Conditions different or unavailable:
Result: matched / divergent / unpaired
Explanation supported by evidence:
Baseline completion required:
One-component improvement hypothesis (only after baseline):
```

The first work product is this comparison map. It does **not** claim that Tables 1–6 or Figures 7–14 have been numerically reproduced.
