# Milestone 6 — Workflow Registry, Auto-Scaler, and Runtime Dispatch

**Phase 3 (paper Section 3.4, pp.574–575; Figure 5c, p.572; Table 1 "Phase 3", p.572).**
This is the first execution-phase milestone in the project. Nothing in `/execution/` exists yet.

Status: **design review pending.** No implementation code is written. Ambiguity numbering
continues at **A81**; open decisions continue at **Q33**.

Conventions carried forward from M3/M4/M5: `[OURS]` = our construction, faithful in spirit but
not stated by the paper; `[DESIGN CHOICE]` = a fork we picked, with the alternative recorded;
`[INVENTED]` = a number or mechanism with no paper source, quarantined to `critique/` or to an
explicitly-named experiment coordinate. Standing policy (`reproduce-murakkab-literally`): where
the paper is ambiguous, unsound, or silent, keep its reading and RECORD the problem.

---

## 1. Plain language first — what these two things are, and why they exist

### 1.1 The registry

The optimizer (M4/M5) decides, once per hour, how to run each workflow: which knob settings,
which model, which GPU type, how many instances, and what fraction of load goes where. That
answer is a **deployment plan**. The registry is simply the place the plan is written down so
that an arriving request can be served without re-running a MILP.

The paper is explicit that the plan stops short of the individual request (§3.3.1, p.574,
verbatim):

> "The deployment plan does not prescribe per-request dispatch, which remains a runtime
> responsibility (Section 3.4). Once an executable workflow is generated for all valid SLO tiers
> of an onboarded workflow, it is added to the Murakkab workflow registry and is ready to serve
> requests."

So the registry holds **one executable workflow per (workflow, SLO tier)** — not one per
workflow. Onboarding Video Q/A does not put one entry in the registry; it puts one entry per
valid tier.

### 1.2 The request path

§3.4, p.574, verbatim:

> "At runtime, Murakkab receives incoming requests from end-users with a payload that contains
> the identifier of the agentic workflow being invoked, any input query/data, and the SLOs.
> Murakkab looks up the registry to obtain the corresponding executable workflow and submits it
> for execution."

And the second request shape (§3.4, "Dynamic Workflow Requests", p.574, verbatim):

> "End-users can either invoke a particular agentic workflow or send a request with a natural
> language query (Figure 5c), any input data to operate on, and SLOs, without specifying an
> agentic workflow to use. The workflow orchestrator parses the query into one or more sub-tasks,
> mapping each to an appropriate executor or an existing workflow."

M6 accepts both shapes. It does **not** re-implement the orchestrator: for the dynamic shape it
calls M1's `WorkflowOrchestrator` (`development/orchestrator.py`), which already turns a
specification into a `LogicalWorkflow` through the abstract LLM client. M6's only new obligation
is the *branch* — decide which shape arrived, and route accordingly.

### 1.3 The auto-scaler

The optimizer sizes the fleet from an hour-scale *projection*. Real load does not obey a
projection, and — this is the paper's own motivation — agentic workflows are uniquely
unpredictable because token counts are input-dependent (§3.4, p.575, verbatim):

> "Predicting end-to-end resource usage in agentic workflows is difficult, as input-dependent
> control flow and intermediate outputs propagating along data flows determine actual demand
> (e.g., Figures 2b and 2d). For example, a video Q/A workflow with 10 frames and STT on
> Llava-OneVision-7B [47] produces 600 and 1200 tokens in the 50th and 99th percentile,
> respectively, highlighting high variance."
>
> "To handle such variability, Murakkab includes an auto-scaler that monitors per-model instance
> load over short windows (seconds to minutes) and rapidly scales out when needed. The optimizer
> can be configured to be conservative (i.e., consider the tail percentile and provision more
> resources) or optimistic (i.e., consider a more common case and let the auto-scaler handle
> variations in the short-term)."
>
> "We set thresholds for auto-scaling based on the performance-throughput characteristic in
> executor profiles. This mechanism prioritizes avoiding SLO violations over short-term
> allocation optimality. Murakkab also maintains spare resources to absorb demand spikes and,
> when it detects significant deviations in workload or resource usage, triggers early
> re-optimization to adapt quickly."

In plain terms: the MILP sizes for the hour; the auto-scaler patches the minute. That pair *is*
the "key design choice" §3.3.1 states — "decouple peak provisioning from average utilization" —
and M6 is the half that has never been built here.

### 1.4 Why M6 is a simulator, and what that costs

There are no GPUs (CLAUDE.md, non-goals). Nothing in M6 launches a process, loads weights, or
serves a token. **"Scaling out" means incrementing an integer in a `SimulatedFleet` and changing
which integer subsequent simulated arrivals are charged against.** Every module that touches this
is named `Simulated*` or lives under `sim/`, and a test asserts that no identifier in `/execution/`
implies real serving. §11 states precisely what the simulation can and cannot establish; read it
before quoting any M6 number.

---

## 2. What the registry stores, and how it is keyed

### 2.1 The `ExecutableWorkflow`

The paper never enumerates the contents of an executable workflow. Figure 5b (p.572) shows the
optimizer emitting "Executable Workflows" into the registry from "Logical Workflows (SLOs +
Demand)" plus "Model-to-H/W Allocation"; §3.3.1's four "Decisions" (p.574) are what the MILP
produces. Composing the two gives the minimum viable content, all of it already produced upstream:

| Field | Source | Paper anchor |
|---|---|---|
| `logical_workflow` | M1 `LogicalWorkflow` | §3.2, p.573 |
| `config` (`ConfigKey`: knobs, incl. the DAG variant that resolves A18/Q6) | M3 `enumerate_cw` | §3.3.1 Decision 1 |
| `node_executors` | M1 assignment, refined per tier | Table 1, Phase 1 row 2: "Refined per SLO tier by optimizer" |
| `model_assignment` (which `m` serves the LLM work) | M4/M5 | §3.3.1 Decision 2 |
| `routing` — the normalized `x` fractions over `(c, m)` | M4/M5 `x_peak`/`x_avg` | §3.3.1 Decision 4 |
| `instance_targets` — `n_m` | M4/M5 `n` | §3.3.1 Decision 3 |
| `tier` / `slo_type` / `tau` | M3 `slo_tiers` | §3.4, p.575 |
| `provenance` — `MilpResult.caveats()`, `data_excluded`, `structural_record` | M4 | our discipline |

The last row is non-negotiable: an `ExecutableWorkflow` that has lost its caveat block would let
an M7 end-to-end number be quoted without the exclusion ledger behind it. `caveats()` rides along.

**A81 [NEW] — per-DAG-node model assignment cannot be filled in.** `model_assignment` is a single
`m` for the whole workflow, not one per node, because A.5's `x_{w,s,c,m}` has no executor index —
this is the M1 gap the tracker records ("MILP has no per-executor index... M1's per-node
assignments therefore dead-end at M4"). Table 1's Phase 1 promises per-node assignment "refined
per SLO tier by optimizer"; the optimizer has no variable with which to refine it. M6 stores the
M1 per-node assignment *unrefined*, and records that the refinement Table 1 promises never happens.
This is not a new defect — it is the first place its consequence is *visible at runtime*, because
the dispatcher must decide which instance a given node's call lands on and the plan does not say.

### 2.2 The key, and a problem with it

Natural key: `(workflow_id, slo_type, tier)` — e.g. `("video_qa", "latency", "good")`. "For all
valid SLO tiers" (§3.3.1) means the registry is populated by iterating the tiers M3 derives, and
**skipping the infeasible ones**: under `baseline`, A37 says latency tiers are structurally
infeasible, so those keys must be *absent*, not present-and-broken. A request for an absent tier
is rejected at admission with the nearest-miss arithmetic from `sets.py` — it must never silently
fall back to a looser tier (`solve.py` already forbids that at the MILP layer; the same prohibition
holds here).

**A82 [NEW] — the registry key is under-determined by the request.** §3.4, p.574–575: "Each
request has the option to specify a quality, latency and cost SLOs. We assign four SLO tiers for
quality and end-to-end latency." A request may therefore carry *two or three* SLOs at once, while
A.5 indexes by a single `s ∈ S` and M4 already recorded (A68) that the accuracy and latency
filters are dimensionally different objects applied to the same index. So a request saying
"quality ≥ good AND latency ≤ good" has no registry entry, because no MILP run ever solved that
conjunction. §4.3's own experiment sidesteps this by splitting the population (70% high-accuracy,
30% low-latency) rather than conjoining SLOs on one request. And cost has no tier at all (A67:
`τ_{w,cost}` is undefined), so a cost SLO on a request cannot be keyed. Recommendation in Q41.

---

## 3. The request path, end to end

```
Request
  ├── NamedRequest(workflow_id, inputs, slo)
  │     └── registry.lookup(workflow_id, slo)  ──► ExecutableWorkflow
  └── DynamicRequest(query, inputs, slo)
        └── WorkflowOrchestrator (M1, mock LLM client)  ──► LogicalWorkflow
              └── registry.lookup_by_logical(...)  ──► ExecutableWorkflow | OnboardingRequired
                              │
                              ▼
                    Dispatcher (§4) — picks ONE (c, m) per request from the routing fractions
                              │
                              ▼
                    SimulatedFleet — charges the request's token draw to a chosen instance
                              │
                              ▼
                    LoadWindow / Monitor (§5) ──► AutoScaler (§6) ──► instance count changes
                              │                                └──► EarlyReoptTrigger (§8)
                              ▼
                    RequestRecord (served | queued | violated | dropped)
```

Two honest notes on the dynamic branch. First, §3.4 says the orchestrator maps sub-tasks "to an
appropriate executor **or an existing workflow**", i.e. dynamic composition may produce a DAG that
is *not* any onboarded workflow — for which no profile and therefore no executable workflow can
exist. M6's behaviour: raise `ExecutorOnboardingRequired` (M1's existing escalation), exactly as
§3.2's "If none is found, Murakkab prompts the developer to onboard a suitable one". We do **not**
invent an on-the-fly profiling path. Second, the M2b tracker entry about **mock-selector bias**
applies with full force here: the dynamic branch's workflow identification is driven by
`MockLLMClient.keyword`, which is known to pick an invented executor over the paper's. Any M6
number produced through the dynamic branch inherits that. The named branch does not, and is
therefore the default for all measurement.

---

## 4. Dispatch — the tension the paper creates and does not resolve

### 4.1 The contradiction, stated plainly

§3.4, p.575, verbatim: "**While request dispatch is deterministic given the selected workflow**,
achieving efficient execution under dynamic, multi-tenant conditions requires continuous
adaptation."

But A.5 declares `x^peak_{w,s,c,m} ∈ R⁺` and `x^avg_{w,s,c,m} ∈ R⁺` — **continuous**. §3.3.1
Decision 4 calls the output "the fraction of load from each (workflow, SLO)-pair routed to each
provisioned instance". M4 already measures how spread that is and reports it as `support_size`
(A70). A fraction over several `(c, m)` pairs is not a deterministic per-request choice; it is a
distribution. Somewhere between the plan and the request, a *policy* converts one to the other,
and the paper names no such policy.

**A83 [NEW] — the fraction→request conversion policy is unspecified, and the choice is not
neutral.** Three defensible policies, with materially different tail behaviour:

| Policy | Per-request rule | Behaviour |
|---|---|---|
| Weighted random | sample `(c,m)` ∝ `x` | fractions honoured in expectation; realized split has O(√N) error, so short windows deviate — which is precisely the variance the auto-scaler then reacts to |
| Deterministic round-robin (stride/Bresenham) | deterministic cycle with frequencies `x` | matches §3.4's "deterministic" word; near-zero split error; but correlates consecutive requests with instances, so a burst of long requests lands in lock-step |
| Hash of request ID | `hash(rid) mod` cumulative `x` | deterministic AND stateless (needed if dispatch is ever replicated); same split error as random; pathological for adversarial/correlated IDs |

None is "the paper's". M6 implements all three behind one `DispatchPolicy` Protocol and makes the
choice a named experiment coordinate that travels in the result object, exactly as
`OperatingPointPolicy` does in M3/M4. Recommendation: Q33.

### 4.2 Two further things the plan does not determine

- **A84 [NEW] — which *instance* of `m`.** The plan gives `n_m` and a fraction to `m`; Table 1's
  dispatch scope is "Request" and the auto-scaler's scope is "Model". Nothing chooses among the
  `n_m` identical instances. Any real system uses queue-aware least-loaded; the paper says
  nothing. M6 defaults to **least-outstanding-tokens** `[OURS]` and records that the choice is
  ours, because the alternative (uniform) measurably worsens simulated tail latency and would
  make the auto-scaler look worse for a reason the paper never specified.
- **The per-node problem (A81) again.** A Code Generation request touches three LLM nodes; the
  plan supplies one `m` and one token total `t_c` for the whole request (A59: no published
  apportionment). So M6 charges `t_c` **once per request to one `m`**, not per node. This is A.5's
  own accounting — eq. (3) is `Σ x·t_c`, request-denominated — and reproducing it literally is
  correct here. It has a consequence for §10.

---

## 5. Monitoring — what is measured, over what window, in what unit

The paper: "monitors per-model instance load over short windows (seconds to minutes)". It does not
say what "load" is.

**A85 [NEW] — "load" has no unit in §3.4, and the candidates disagree.** A.5's capacity constraint
is token-denominated (`x·t_c ≤ n·θ_m`, tokens/s). Arrivals are requests/s (`arrivals.py`, unit-tagged
after M4's factor-60 bug). Figure 3's profile curves are indexed by throughput in tokens/s. Queue
depth, the quantity a real auto-scaler watches, appears nowhere. **M6 measures in tokens/second**,
because that and only that is commensurable with `θ_m` — which is what §3.4 says the thresholds
come from. Requests/s and queue depth are recorded alongside as diagnostics but never thresholded.

Design:

- `SimClock` — simulated seconds. Fixed tick (default 1 s), sliding windows on top.
- `LoadWindow` — per `(m, instance_id)` ring buffer of tokens admitted per tick, with a
  configurable window length. Default **60 s** (the top of the paper's "seconds to minutes"
  range; conservative w.r.t. thrash). Window length is a swept coordinate, not a constant.
- A **cold-start guard**: a window with fewer than `min_samples` ticks cannot trigger scaling.
  Without it the first tick of every epoch triggers a scale event, which would be an artifact of
  our tick model, not a property of Murakkab.

Note the interaction with the token distribution: a window's measured token rate is a *draw*, and
M6 draws per-request token counts from M3's `TokenDistribution` (the full percentile ladder, §7),
which is why the tail matters and why the p90-collapsed `MilpInputs` is the wrong input here.

---

## 6. Thresholds from the profile curve — the one mechanism §3.4 actually specifies

"We set thresholds for auto-scaling based on the performance-throughput characteristic in executor
profiles." That characteristic is exactly `ModelProfile.curve`: a sequence of `LoadPoint(throughput,
ttft_p90, tpot_p90)` read from Figure 3 (M3). This is the single most faithfully-reproducible
sentence in §3.4 and M6 should lean on it hard.

Derivation, per model profile `m`, given the request's tier threshold `τ`:

1. **SLO-feasible throughput ceiling** `θ^slo_m(τ)` = the largest curve throughput at which
   eq. (5)'s latency expression `ℓ^TTFT + t_c·ℓ^TPOT` still clears `τ`. This *is* §3.3.1
   Constraint 3 in words — "per-instance load stays within the throughput envelope at which the
   profile satisfies the latency SLO" — evaluated on the curve rather than on one collapsed point.
2. **Scale-out threshold** = `scale_out_ratio × θ^slo_m(τ)`, default ratio 0.8.
3. **Scale-in threshold** = `scale_in_ratio × θ^slo_m(τ)`, default 0.4, with hysteresis (a
   sustained-below requirement of `k` consecutive windows) so the two thresholds cannot oscillate.

`OperatingPointPolicy.KNEE` — "last point before TPOT exceeds 1.5× its floor" — is the
tier-independent fallback for accuracy-tier requests, where no latency `τ` exists to evaluate
step 1 against. Two knobs, two provenances, both labelled: the *ceiling* is `PAPER_FIGURE_READ`
(it is the curve); the *ratios* are `[INVENTED]` and swept, since §3.4 gives no numbers at all.

**A86 [NEW] — the thresholds cannot be derived for models whose curve cannot be evaluated.**
7 model profiles have no TTFT (A65), and Llava-OneVision-7B — the model §3.4's *own auto-scaler
motivating example* runs ("a video Q/A workflow with 10 frames and STT on Llava-OneVision-7B")
— is one of them (A62). So §3.4 motivates the auto-scaler with a model for which §3.4's own
threshold rule is unevaluable in the paper's published data. This extends the PATTERN entry
(formulation narrower than the system) into Phase 3, which is a new instance, not a restatement:
the previous instances were about A.5, this one is about the prose mechanism. For these `m` M6
falls back to the KNEE ceiling and marks the threshold `DERIVED_WITHOUT_LATENCY`, never imputing
a TTFT.

### 6.1 Conservative vs optimistic — the paper's own knob

§3.4 attributes the mode to the **optimizer**, not the auto-scaler: "The optimizer can be
configured to be conservative (i.e., consider the tail percentile ...) or optimistic (i.e.,
consider a more common case and let the auto-scaler handle variations in the short-term)."

So the mode is realized *upstream*, as M3's `TokenPolicy(percentile=…)` feeding `t_c`:

| Mode | `t_c` percentile | Paper anchor |
|---|---|---|
| conservative | p99 | "consider the tail percentile and provision more resources" |
| paper default | p90 | §4.1/4.2 boundary p.576 (A46 — one sentence, one version) |
| optimistic | p50 | "consider a more common case" |

This makes the p50/p90/p99 sweep **paper-sanctioned**, not our invention (A46's sibling). M6's
experiment harness therefore runs the same trace three times with three `TokenPolicy` values and
one auto-scaler, and the interesting output is *how much work the auto-scaler has to do* in each.
Crucially the *arrivals* are the same in all three; only the provisioning belief changes.

---

## 7. Scale-out / scale-in mechanics (simulated)

`SimulatedFleet` holds, per `m`: `n_planned` (from `MilpResult.n`), `n_active`, `n_pending`
(provisioning), and a per-instance `LoadWindow`. Scaling is integer arithmetic over these; nothing
is launched.

Loop, once per control interval (default 10 s):

1. Recompute each instance's windowed token rate.
2. If the mean rate over instances of `m` exceeds the scale-out threshold → request
   `ceil(excess / θ^slo_m)` additional instances.
3. Satisfy the request from **spare** first (§8), then from unallocated budget under eq. (7)'s
   `B_g`, then fail (§9).
4. New instances enter `n_pending` and become active after `provisioning_delay` (§7.1).
5. Scale-in only after `k` consecutive windows below the scale-in threshold, and never below
   `n_planned × floor_ratio` — a floor, because tearing down below the optimizer's plan inside an
   epoch would fight the optimizer rather than patch it.
6. Re-normalize routing: the plan's fractions are over `m`, not over instances, so only the
   intra-`m` instance choice (A84) changes. **The fractions across `m` are NOT recomputed** — that
   would be re-solving the MILP, which is the epoch's job.

**A87 [NEW] — "rapidly scales out" is contradicted by the paper's own provisioning assumption.**
§4.7, p.579, verbatim: "Provisioning new instances (i.e., VM allocation, software setup, and model
transfer to GPUs) is assumed to take **20 minutes** [31, 38, 62]." §3.4 says the auto-scaler
"monitors ... over short windows (seconds to minutes) and **rapidly** scales out when needed". A
20-minute cold start cannot answer a 60-second window. The only reconciliation is that scale-out
is served from *pre-warmed spare* — which makes the auto-scaler's entire responsiveness claim
rest on the spare pool, a quantity the paper never sizes (A88). This is the sharpest gap in §3.4
and M6 must make it *measurable*: with `spare = 0` and a 20-minute delay, the auto-scaler cannot
prevent an SLO violation inside one window, by construction. That is a reproduction result, not a
bug to be tuned away.

### 7.1 Provisioning delay

Default **1200 s** (§4.7's 20 minutes), configurable, and settable to 0 only under an explicitly
named coordinate `instant_provisioning` so that any run using it is self-labelling. A.5 has no
transition cost at all (A69: no inter-epoch coupling — fleets rebuild hourly at zero modelled
cost); M6 is where that free rebuild becomes visible, because a 20-minute delay against a
60-minute epoch means **a third of every epoch is spent arriving at the plan**.

---

## 8. Spare resources

**A88 [NEW] — "maintains spare resources" has no parameter in A.5, and three distinct paper
quantities are commonly mistaken for it:**

- `α = 1.15` (A.5 parameter list) is a **demand buffer** on the right-hand side of eqs. (1)/(2) —
  an allowance to *over-serve projected demand*, not idle capacity held back. §3.3.1 Constraint 2
  says it explicitly: "leaving headroom for short-term variance that the auto-scaler absorbs".
- `B_g` (eq. 7) is a **hard budget ceiling**, the opposite of a reserve.
- Figure 13a's "**Buffer Cost**" (§4.7) is *transition* overhead during re-optimization, not spike
  absorption.

None of the three is a spare pool. M6 introduces `spare_fraction` `[INVENTED]`, **defaulting to
0.0** so that the paper's formulation is what runs unless an experiment names otherwise, with the
sweep `{0, 0.05, 0.10, 0.20}` reported as sensitivity. The default of zero is deliberate: it makes
A87's contradiction visible rather than hiding it behind a tuned reserve.

---

## 9. When the auto-scaler cannot meet demand

§3.4: "This mechanism prioritizes avoiding SLO violations over short-term allocation optimality."
Eq. (7) is a hard constraint: `Σ n_m·g_m ≤ B_g`. Under a `B_g` that binds, "prioritize avoiding
SLO violations" is not implementable — there is nothing left to scale into.

**A89 [NEW] — the paper states a priority it gives no mechanism to honour, and names no degradation
policy.** No admission control, no queueing discipline, no tier downgrade, no shedding rule appears
anywhere in §3.4. §4.7 mentions dropped requests only as a *counterfactual metric* ("requests that
would be dropped without auto-scaling"), never as a runtime behaviour.

M6's behaviour, chosen to be maximally legible rather than maximally good: requests that cannot be
admitted within threshold are **queued FIFO**, and a request whose simulated completion exceeds its
`τ` is recorded as `SLO_VIOLATED` and still completed (never silently dropped, never silently
retried). A separate `DROPPED` outcome exists only when the queue exceeds a named bound. Outcome
counts are first-class in the report. **A simulator that reports zero violations because it
silently queued forever would be worthless**; the tests in §13 defend against exactly that.

---

## 10. Load projection and the epoch boundary

### 10.1 What the paper actually supplies

§3.4 says only: "The state of the previous epochs is used to project the load for each workflow in
the next epoch." No method. But §4.7, p.579, does supply one, verbatim: "We use an exponentially
weighted moving average (EWMA) [18], with **α = 0.5**, to predict workload demand at every epoch."

So the predictor is paper-sourced after all — it just lives in the evaluation section, not the
design section. M6 implements EWMA(α=0.5) over the per-epoch `(λ^peak, λ^avg)` that
`arrivals.epoch_statistics` already computes from Figure 19.

**A90 [NEW] — `α` denotes two different things in one paper.** A.5's parameter list: "α: Unified
buffer factor (default 1.15)". §4.7: "EWMA ... with α = 0.5". The auto-scaler needs both
simultaneously. M6 never uses the bare name: `alpha_buffer` and `ewma_alpha`, enforced by test.

### 10.2 Replay is not prediction — keep them apart

M3 replays Figure 19's digitized trace. Replaying a known trace is **the paper's experimental
setup**; predicting the next epoch from prior epochs is **a component**. Confusing them would let
M6 "predict" perfectly by peeking. Therefore:

- `projection.py` receives **only epochs `< e`** and returns `(λ̂^peak_e, λ̂^avg_e)`. A test
  enforces the signature and asserts that a permutation of future epochs cannot change its output.
- The trace's true epoch `e` is used for two things and no others: generating the actual arrivals,
  and computing **under-prediction** — the Figure 13b metric (`max(0, λ_true − λ̂)/λ_true`), which
  M6 can reproduce directly and which is the honest measure of the projector.

### 10.3 Epoch boundary and churn

At each 60-minute boundary M6 calls M4 (or M5's `solve_joint`) with the *projected* demand, gets a
new plan, and installs it. `epoch_minutes` is a **parameter**, not a constant — §4.7 sweeps
20–360 minutes and M6 should be able to reproduce Figure 13a/13b's shape (not its absolute values;
see §11).

A69 (M5's measurement: A.5 has no inter-epoch coupling, so fleets can be torn down and rebuilt
hourly at zero modelled cost) becomes observable here as **churn**: `|n_m^{e} − n_m^{e−1}|`
summed over `m`, plus the GPU-seconds spent in `n_pending`. That second quantity is exactly
Figure 13a's "Buffer Cost", which A.5's objectives (11)/(12) do not contain. M6 records both and
neither feeds back into the optimizer — because in the paper it does not.

---

## 11. What this simulation can and cannot establish

Stated up front, because a simulated auto-scaler that "meets SLOs" proves nothing unless what it
simulates is stated precisely.

**What is simulated:** arrival times (Figure 19 replay), per-request token counts (drawn from M3's
`TokenDistribution` percentile ladder), per-instance service as a token-rate server whose latency
comes from the profile curve via eq. (5), integer instance counts, and a provisioning delay.

**What is NOT simulated, and therefore what M6 cannot claim:**

1. **No batching engine.** See A91 below. Latency comes from a static curve point, so the actual
   queueing/batching dynamics vLLM exhibits are absent.
2. **No KV cache, no memory limits, no preemption.** §4.7's remark that "frequent model and tool
   changes can also reduce KV cache efficiency" is unmodelled, so M6 *understates* the cost of
   short epochs — Figure 13a's Zone 1 will be shallower here than in the paper.
3. **No tool execution cost.** 11 of 26 executors are tools with no profile (A25/A31), unequally
   distributed across the two workflows (M3 tracker entry). Simulated end-to-end latency is a
   **lower bound**, unequally so — Video Q/A more understated than Code Generation.
4. **No network, no data movement, no cold model load beyond the flat 20-minute delay.**
5. **Accuracy is not simulated at all** — `a_c` is a profile constant, so a "quality SLO met"
   result in M6 is a tautology (the filter selected a configuration whose profiled `a_c` clears
   `τ`), not a measurement. This must be said wherever M6 reports quality.

**Consequence, stated bluntly:** M6 can establish *relative* statements — conservative vs
optimistic provisioning, spare = 0 vs 0.2, epoch 20 vs 60 vs 360, dispatch policy A vs B — because
those share every unmodelled term. It **cannot** establish that Murakkab's auto-scaler meets SLOs
in reality, and no M6 output may be phrased that way. A `fidelity_notes` tuple on the result object
carries this list, as `MilpResult.caveats()` does for M4.

**A91 [NEW] — "batch composition" is named once and described nowhere.** Table 1, p.572, lists it
as a Phase 3 decision: frequency "Continuous", scope "Instance". It does not appear in §3.4's text
or anywhere else in either version. The only oblique trace is A.2, p.585, verbatim: "For the
latency SLO requests, Murakkab keeps the same workflow- and model-level knobs but changes GPU type
and **increases the allowed load per model instance to increase batching** as the SLO is relaxed."
That sentence puts batching under the *optimizer's* control, through the choice of operating point
on the profile curve — which is precisely A37b, the multi-operating-point collapse that A.5 cannot
represent because `θ_m` and `ℓ^TPOT_m` are constants of `m`. **So Table 1's "continuous, per-instance"
batch composition and A.2's "per-epoch, per-model-profile" batching are two different mechanisms
with one name, and the formulation supports neither.** M6 reproduces the A.2 reading (batch level =
operating point, fixed for the epoch) and implements no continuous per-instance batcher, recording
that Table 1's row is unreproducible from the paper's own description.

---

## 12. Contact with the two standing critiques

### 12.1 Capacity model — where `α = 1.15` stops being an assumption

M6 is the first place `α` is *falsifiable*. The measurement: for each `(TokenPolicy, epoch, trace)`
combination, compute the **realized peak-to-projected ratio**
`R = max_window(actual token demand) / (projected peak demand)`. `α = 1.15` is "right" iff the
auto-scaler needs no scale-out beyond the plan, i.e. iff `R ≤ 1.15` for essentially all windows.
Report the full distribution of `R`, its p50/p90/p99, and the fraction of windows where
`R > 1.15` — the second is the direct answer to "is 1.15 enough?", and it will differ sharply
between conservative (p99 `t_c`) and optimistic (p50 `t_c`) provisioning. Paired with the
under-prediction metric of §10.2, this gives the two halves of Murakkab's stated design choice
("decouple peak provisioning from average utilization") their first quantitative check in this
repo. Expected finding, to be confirmed not assumed: under optimistic provisioning `R` exceeds
1.15 routinely, and with `spare = 0` plus a 20-minute delay the auto-scaler cannot close the gap
(A87).

### 12.2 HEFT / precedence — a prohibition and a recording obligation

**Prohibition, in the same form M4 §10.1 states it:** M6 adds **no precedence constraint and no
makespan term**. The dispatcher does not schedule by the DAG, does not compute earliest-finish
times, does not overlap parallel branches deliberately, and does not use critical-path order to
choose instances. Murakkab has none of this, and adding it would make the baseline better than the
paper.

**But** — and this is new at M6 — a dispatcher *does* execute a DAG in some order, so the real
critical path becomes observable at runtime for the first time. M6 therefore **records**, per
served request:

- per-node simulated start/finish times in simulated seconds, in whatever order the naive
  executor happened to run them (topological order, ties broken by declaration order — stated so
  it is not mistaken for a scheduling policy);
- the sum-of-stages latency A.5's eq. (5) would have predicted for the same request;
- the realized end-to-end span.

`profiles/critique/critical_path.py` consumes these. The comparison remains **structural on Video
Q/A and not numerically computable on Code Generation** (A59: Code Gen's three LLM nodes have no
published token apportionment, and M6 charges `t_c` once per request per §4.2). M6 does not repair
that; it supplies the timestamps and lets the critique module say what the data supports. A test
asserts `/execution/` never imports the critique module — the same one-way dependency M4 enforces
for `milp/critique/incoherence.py`.

---

## 13. File layout and build order under `/execution/`

Build in this order; each file is confirmed before the next (CLAUDE.md, file-by-file).

```
/execution/
  DESIGN.md                 this file
  __init__.py               public surface only
  requests.py               Request, NamedRequest, DynamicRequest, SloSpec, RequestOutcome
  registry.py               ExecutableWorkflow, WorkflowRegistry (keying, tier population, A82)
  build.py                  MilpResult/JointResult -> ExecutableWorkflow (carries caveats())
  sim/clock.py              SimClock -- simulated seconds, explicit
  sim/fleet.py              SimulatedInstance, SimulatedFleet (n_planned/active/pending)
  sim/service.py            token-rate service model from ModelProfile.curve + eq. (5)
  dispatch.py               DispatchPolicy Protocol + weighted-random / round-robin / hash
  monitor.py                LoadWindow, per-instance token-rate metering (tokens/s, A85)
  thresholds.py             theta^slo(tau) from the curve; scale-out/in ratios (Section 6)
  autoscaler.py             control loop, spare, hysteresis, provisioning delay
  projection.py             EWMA(ewma_alpha=0.5); past-only signature enforced
  epoch.py                  epoch loop; re-solve; install plan; churn accounting
  trigger.py                early re-optimization trigger (Section 8 / A92)
  report.py                 ExecutionReport + fidelity_notes (Section 11)
  runner.py                 the 24-hour trace experiment harness
  critique/dispatch_gap.py       realized vs planned routing split (A83)
  critique/observed_dag.py       per-node timestamps for critical_path.py (Section 12.2)
```

`critique/` is import-forbidden from the rest of `/execution/`, by test.

**A92 [NEW] — "significant deviations in workload or resource usage" has no threshold anywhere.**
No number, no window, no metric. M6's `trigger.py` uses `|λ_observed(window) − λ̂_epoch| / λ̂_epoch
> deviation_threshold` sustained for `k` windows, with `deviation_threshold` `[INVENTED]`,
defaulting to **off** (never triggering) so the paper's 60-minute cadence is what runs unless an
experiment names otherwise, and swept `{0.25, 0.5, 1.0}` as sensitivity. Note the trap: early
re-optimization *costs* a 20-minute transition (A87/§7.1), so a low threshold makes things worse —
which is Figure 13a's Zone 1 arriving through a different door, and worth reporting as such.

---

## 14. Test list — each named for the property it defends

Following M3/M4 style: the test name states the claim, not the function under test.

| File | Defends |
|---|---|
| `test_registry_tier_coverage.py` | an onboarded workflow has an entry for **every valid** tier, and infeasible tiers are ABSENT rather than silently loosened (A37) |
| `test_registry_key_rejects_conjunction.py` | a request carrying two SLO types is rejected with the A82 message, not served by guessing |
| `test_executable_workflow_carries_caveats.py` | no `ExecutableWorkflow` can be constructed without the `MilpResult` provenance block |
| `test_request_shapes.py` | both request shapes are accepted; the dynamic shape goes through M1's orchestrator and escalates on no-match rather than inventing a workflow |
| `test_dispatch_honours_fractions.py` | over N requests each policy's realized split converges to `x`; round-robin's error is bounded, random's is O(√N) — the A83 difference is *measured*, not asserted |
| `test_dispatch_is_a_named_choice.py` | the policy travels in the result object; no default is applied silently |
| `test_no_precedence_scheduling.py` | the dispatcher contains no critical-path/EFT logic and no makespan term (the §12.2 prohibition, enforced as M4 does) |
| `test_autoscale_thresholds_from_curve.py` | thresholds are derived from `ModelProfile.curve`, and models without TTFT (A86, incl. Llava-OneVision-7B) fall back to KNEE and are MARKED, never imputed |
| `test_autoscale_hysteresis.py` | no oscillation: a load oscillating around the threshold produces bounded scale events |
| `test_autoscale_cannot_exceed_budget.py` | eq. (7)'s `B_g` is respected even when SLOs are being violated — the A89 finding is produced, not avoided |
| `test_provisioning_delay_is_real.py` | scale-out with `spare = 0` and the 20-minute delay CANNOT prevent a within-window violation (A87), and `instant_provisioning` is self-labelling |
| `test_spare_defaults_to_zero.py` | `spare_fraction` is 0 unless named (A88) |
| `test_projection_is_past_only.py` | `projection` cannot see epoch `e` or later; permuting the future changes nothing |
| `test_alpha_is_two_symbols.py` | no bare `alpha` identifier exists in `/execution/` (A90) |
| `test_underprediction_metric.py` | the Figure 13b quantity is computed from the true trace and never fed back into the projector |
| `test_no_silent_success.py` | violated and dropped requests are counted and surfaced; an infinite queue cannot masquerade as zero violations (§9) |
| `test_fidelity_notes_present.py` | every `ExecutionReport` carries §11's limits; a report without them fails |
| `test_simulation_is_labelled.py` | no identifier in `/execution/` implies real serving; `sim/` is the only place instance counts change |
| `test_execution_never_imports_critique.py` | the one-way dependency |
| `test_churn_is_recorded.py` | A69 becomes a number: per-epoch `Σ|Δn_m|` and pending GPU-seconds are reported and never fed back |

---

## 15. Open decisions for Arno (Q33–Q42) — with a recommendation for each

**Q33 — Dispatch policy (A83).** Which fraction→request rule is the default?
*Recommend:* implement all three; default **weighted random**, because it is the only one whose
error structure *creates* the short-term variance §3.4 says the auto-scaler exists to absorb — so
it exercises the component under test. Round-robin is the closest to §3.4's literal word
"deterministic" and is the control arm. Report both in any headline.

**Q34 — Monitoring unit (A85).** *Recommend:* **tokens/second**, the only unit commensurable with
`θ_m`. Requests/s and queue depth recorded as diagnostics only.

**Q35 — Threshold ratios.** `scale_out = 0.8·θ^slo`, `scale_in = 0.4·θ^slo`, window 60 s,
hysteresis `k = 3`. All `[INVENTED]` (§3.4 gives no numbers) and swept.
*Recommend:* accept as defaults, sweep `scale_out ∈ {0.7, 0.8, 0.9}`, and never quote a number
without the ratio beside it.

**Q36 — Spare capacity (A88).** *Recommend:* `spare_fraction = 0.0` by default. Zero is the
formulation's own answer, and it keeps A87's contradiction visible.

**Q37 — Early re-optimization trigger (A92).** *Recommend:* **off** by default, swept as
sensitivity, and always reported together with the transition cost it incurs.

**Q38 — Load projection (§10).** *Recommend:* **EWMA with `ewma_alpha = 0.5`**, citing §4.7 —
paper-sourced, not invented. Past-only by construction. Report Figure 13b's under-prediction.

**Q39 — Unmet demand (A89).** *Recommend:* queue FIFO, mark `SLO_VIOLATED` on deadline miss,
complete anyway; `DROPPED` only past a named queue bound. Never silently succeed.

**Q40 — Provisioning delay.** *Recommend:* **1200 s on by default** (§4.7), because turning it off
would flatter the auto-scaler with an assumption the paper does not make.

**Q41 — Multi-SLO registry key (A82).** *Recommend:* **reject the conjunction** with an explicit
error naming A82, and provide §4.3's population split (70/30) as the paper's own way of expressing
mixed SLOs. Do not invent a product key `(quality, latency)` — no MILP run solved it. Cost SLOs
are rejected outright, citing A67 (`τ_{w,cost}` undefined).

**Q42 — Simulated time model.** *Recommend:* **fixed 1 s tick**, 10 s control interval, 60 s
monitoring window, 3600 s epoch — over discrete-event simulation, because the quantities being
compared are windowed rates, DES adds precision the profile data cannot support (curve points are
sparse Figure 3 reads), and a fixed tick is far easier to make deterministic and testable. Ticks
are a named coordinate so the sensitivity is checkable.

**Also noted, not blocking:** whether M6's runner should reproduce Figure 13a's three-zone shape.
*Recommend yes, as a shape-only check* — absolute values are unreachable (§11 items 2 and 3 both
bias Zone 1), so the claim is "the trade-off has the stated shape", never "we reproduce the curve".

---

## 16. What M6 deliberately does not do

- No precedence, no makespan, no DAG-aware scheduling (§12.2).
- No re-solving of routing fractions inside an epoch (§7 step 6) — that is the optimizer's job.
- No new profile data. M6 reads `ProfileSet` (for the token tail and the curves) and `MilpResult`/
  `JointResult`; it adds no numbers of its own beyond the `[INVENTED]` control knobs listed above,
  each defaulting to the paper's own behaviour or to off.
- No real infrastructure, no containers, no serving engine (§1.4, §11).
- No CPU placement (A13: A.5 has no CPU resource type), so §4.6's CPU-offload behaviour remains
  unreproducible at runtime as well as in the formulation.
- No Math Q/A, no OS-log-analysis (CLAUDE.md non-goals).

### Boundary note, stated once because it is easy to get wrong

**M6 reads `ProfileSet`, not `MilpInputs`.** `MilpInputs` collapses each `TokenDistribution` to a
single percentile (p90 by default) — that collapse is correct for A.5, whose `t_c` is a scalar
parameter, and *wrong* for the auto-scaler, whose entire justification in §3.4 is the spread
between p50 and p99. M6 therefore takes `t_c` percentiles and `ModelProfile.curve` from the
`ProfileSet` directly, and takes `n`, `x`, and the tier thresholds from the MILP result. A test
pins the import boundary in both directions.
