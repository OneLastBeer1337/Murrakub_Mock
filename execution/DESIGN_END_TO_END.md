# Milestone 7 — End-to-end single-request run (Code Generation)

**All three life-cycle phases joined for the first time** (paper Section 3.1, Figure 5, Table 1,
p.572; Phase 1 §3.2 p.572–573; Phase 2 §3.3 p.573–574; Phase 3 §3.4 p.574–575).

Status: **design review pending.** No implementation code is written. Ambiguity numbering
continues at **A94**; open decisions continue at **Q43**.

Conventions carried forward: `[OURS]` = our construction, faithful in spirit but not stated by
the paper; `[DESIGN CHOICE]` = a fork we picked, alternative recorded; `[INVENTED]` = a number or
mechanism with no paper source, quarantined to `critique/` or to an explicitly named experiment
coordinate. Standing policy (`reproduce-murakkab-literally`): where the paper is ambiguous,
unsound or silent, keep its reading and RECORD the problem.

---

## 1. Plain language first — what M7 is, and what it is not

Everything built so far stops one step short of running anything.

- M1/M2 turn a declarative spec into a **logical workflow**: four Code Generation sub-tasks
  (`propose_solutions → write_tests → execute_tests → rank_solutions`), each mapped to an
  executor from the library, with data-flow edges. No models, no hardware (§3.2, p.573:
  "Configuration details ... are omitted from the specification").
- M3 profiles configurations and models. M4/M5 solve Appendix A.5 and emit a **deployment plan**:
  knobs, model, GPU type, instance counts, routing fractions.
- M6 puts that plan in the **registry**, accepts requests, converts routing fractions into a
  per-request choice, and charges the request's tokens to a simulated instance. But M6 treats a
  request as **one opaque unit of token work**. It never looks at the four nodes.

M7 is the first milestone that opens the request. One Code Generation request arrives, the
registry hands back the plan, the dispatcher picks a `(c, m)` pair — and then the four sub-tasks
actually run, in data-flow order, each producing an output that the next one consumes, each
stamped with a simulated start and finish time.

**What M7 is not.** It is not a scheduler, not a performance model of a serving engine, and not a
correctness test of generated code. There is no GPU and no LLM (CLAUDE.md non-goals). Every
"answer" is a deterministic stub; every duration comes from eq. (5) applied to digitized Figure 3
curves. §9 states exactly what a run can and cannot establish, and it should be read before any
M7 number is quoted anywhere.

### 1.1 Why this milestone is the one that matters for the comparison

`PROGRESS.md` calls M7 "first point real numbers can be sanity-checked". The precise sense in
which that is true is narrow and worth stating up front:

**M7 is the first place a workflow's end-to-end latency is produced by summing over its nodes.**
Every latency in the project so far has been a single evaluation of Appendix A.5's eq. (5),

    ℓ^TTFT_m + t_c · ℓ^TPOT_m  ≤  τ_{w,s}

— one model, one token total, no sum over sub-tasks, no max over paths (A5_VERBATIM.md). M3 built
`optimization/profiles/critique/critical_path.py` to state the gap between that expression and a
path over the DAG, and it could only state it **structurally**: which symbols eq. (5) contains and
which it does not. Its magnitudes are `[INVENTED]` tool times and it is quarantined from
`to_milp_inputs()` by test.

M7 supplies the missing half: **observed** per-node start/finish timestamps from an actual DAG
walk. For the first time the comparison has a left-hand side that was measured by running
something rather than asserted by reading Appendix A.5. §7 specifies that handoff, and §7.3 is
brutally honest about how much of it Code Generation can carry (answer: the ordering and the
node count, not the per-node token magnitudes — A59).

---

## 2. The request lifecycle across all three phases

```
                 [Phase 1 — development, M1/M2]                    once, at onboarding
  specs/code_generation.py
        └─ spec_parser  ──► TaskGraph
              └─ WorkflowOrchestrator (abstract LLM client, MOCK — §8)
                    └─ type_check  ──► LogicalWorkflow(nodes, edges)

                 [Phase 2 — optimization, M3/M4/M5]                once per epoch (60 min)
  enumerate_cw ──► C_w ; build_model_profiles ──► M
        └─ solve() / solve_joint()  ──► MilpResult / JointResult
              └─ build_executable()  ──► ExecutableWorkflow  ──► WorkflowRegistry

                 [Phase 3 — execution, M6 + M7]                    per request
  Request(workflow_id="code_generation", payload={query: ...}, slo=("accuracy","best"))
        └─ registry.lookup(...)            ──► ExecutableWorkflow        [M6]
        └─ Dispatcher.choose(...)          ──► one (c, m) pair           [M6]
        └─ SimulatedFleet / ModelServer    ──► queue delay, token charge [M6]
        └─ DagWalk over LogicalWorkflow    ──► per-node invocations      [M7, NEW]
              └─ NodeExecutor per ExecutorKind (§4)
        └─ RequestTrace(node timings, eq5 latency, observed span)        [M7, NEW]
              └─ RequestOutcome (M6's Outcome enum, unchanged)
```

The only new machinery is the last two boxes. M7 changes nothing upstream: it does not re-solve,
does not re-key the registry, does not alter dispatch, and does not touch the fleet's accounting.

**A94 [NEW] — the paper never describes node-level runtime execution.** §3.4 (p.574) describes
the runtime as: receive payload with workflow identifier, "look up the registry to obtain the
corresponding executable workflow and submit it for execution". *Submits it for execution* is the
whole of it. Table 1's Phase 3 rows are "Request dispatch" (scope: Request) and "Batch
composition" (scope: Instance) — neither is per sub-task. So the loop that walks the four nodes
exists in **no** part of the paper's description; it is entailed by the workflow being a DAG whose
"edges denote data flow" (§3.2, p.573), not stated. The DAG walk is therefore `[OURS]`, and that
label matters: M7's centrepiece finding is a comparison between something the paper specifies
(eq. 5) and something it leaves implicit (the path). Marking the second as ours is what keeps the
comparison honest.

---

## 3. The DAG-walk rule, and the prohibition boundary

This is the load-bearing section of the milestone. Read it before §4.

### 3.1 The rule, in one sentence

**M7 walks the DAG for data-flow correctness. M7 does not schedule by the DAG for resource
allocation.**

### 3.2 Why these are not in conflict

Every milestone so far has obeyed an explicit prohibition (M4 §10.1, M6 §12.2, and
`shared/workflow.py`'s `LogicalEdge` docstring: "RULE FOR MILESTONES 4/5: the optimizer must NOT
read these edges for scheduling"). The reason is that Appendix A.5 has **no precedence
constraint and no makespan term** — adding one would make the reproduction better than the paper
and destroy the baseline.

But you cannot execute `rank_solutions` before `execute_tests`, because `rank_solutions`'s second
argument *is* `execute_tests`'s output. That is not a scheduling decision; it is what the spec
means. `LogicalWorkflow.__post_init__` already enforces topological ordering of `nodes` at
construction time, so the order exists in the data structure before M7 touches it.

The distinction, stated as a boundary:

| Uses the DAG for… | Allowed in M7? | Why |
|---|---|---|
| deciding the ORDER in which node outputs become available | **yes** | data flow; §3.2 p.573 defines edges as data flow |
| deciding WHICH node runs where / on which instance | **no** | that is allocation; A.5 has no per-node variable (A81) |
| computing earliest finish times / critical path to choose an order | **no** | HEFT; absent from the paper |
| overlapping parallel branches deliberately to shorten a span | **no** | §4.6 measures overlap, A.5 cannot express it — and M7 must not silently supply it |
| minimizing or bounding a makespan | **no** | no A.5 objective mentions completion time |
| RECORDING the span that the naive walk happened to produce | **yes** | measurement, not optimization (§7) |

### 3.3 The order M7 uses, stated so it cannot be mistaken for a policy

Nodes execute in **`LogicalWorkflow.nodes` order** — i.e. the topological order the spec's own
statement sequence already fixed, ties broken by declaration order. No sort, no heuristic, no
lookahead. On Code Generation this is a total order, so there is exactly one admissible order and
the choice is vacuous; the statement matters for Video Q/A, where `frame_extract` and `stt` are
siblings and *any* tie-break is arbitrary.

`[DESIGN CHOICE]` Sibling nodes execute **sequentially, in declaration order, with no overlap**.
The alternative — running them concurrently in simulated time — would import §4.6's measured
"near-perfect parallel, with full overlap" into the runtime, which is a capability the paper
*demonstrates* but its formulation cannot express. Reproducing the formulation literally means the
naive runtime does not do it either, and the resulting span is then a number the critique module
can compare against a parallel path. Recorded as the milestone's largest deliberate pessimism; see
Q52.

### 3.4 How a test enforces the boundary

Three tests, not one, because the prohibition has three distinct failure modes:

1. **Textual** — `test_no_precedence_scheduling.py` (M6's, extended): no identifier in
   `/execution/` matches `makespan|earliest_finish|critical_path|heft|slack|priority_rank`, and
   `dag_walk.py` imports nothing from `optimization.profiles.critique`.
2. **Behavioural** — `test_walk_order_is_declaration_order.py`: for a synthetic workflow with two
   sibling branches of deliberately *unequal* profiled duration, the walk executes them in
   declaration order, NOT longest-first. A HEFT-like implementation passes the textual test and
   fails this one.
3. **Allocative** — `test_walk_does_not_choose_instances.py`: the `(c, m)` pair and the instance
   are chosen once, by M6's dispatcher, before the walk starts; the walk receives them as
   immutable inputs and has no reference to the fleet. Changing the DAG cannot change the
   allocation.

---

## 4. What "executing" an executor means in simulation

`ExecutorKind` (shared/executor.py) has three members and each means something different here.

### 4.1 `ExecutorKind.LLM` — e.g. `llm_unit_test_writer`

A profiled model call. Simulated duration is eq. (5) on the dispatched model profile:
`ℓ^TTFT_m + tokens · ℓ^TPOT_m`, exactly the expression `sim/service.py::ServiceParams.
service_time_s` already implements — deliberately the same function the optimizer's filter uses,
so planner and runtime agree about what a call costs and disagree only about what they *count*.

The problem is `tokens`. See §5.

### 4.2 `ExecutorKind.COMPOSITION` — `llm_debate_coders` with `(D, R)`

M1/M2 model the debate as **one node with knobs**, not as `R` unrolled nodes (§3.2 p.572: "The LLM
Debate composition exposes the knobs: D, R, and model"; §3.2 p.573: the logical workflow "is
represented as a directed acyclic graph (DAG)", so the loop cannot be an edge). A.5 inherits this:
the entire debate is distinguished from a single-shot coder **only by the magnitude of `t_c`** —
Table 6's `Agents`/`Rounds` columns (A45) select a different configuration `c`, hence a different
`t_c`, and nothing else.

So what does "executing" `propose_solutions` with `D=4, R=4` mean?

`[DESIGN CHOICE]` M7 executes it as **one timed invocation** whose duration is eq. (5) on the
config's token total, and **records** `llm_invocations = D · R = 16` as a structural count. The
count is reported, never costed.

**A95 [NEW] — a composition's internal structure is invisible to every term the paper defines,
including its own latency.** `D` debaters in one round are logically concurrent; `R` rounds are
strictly sequential. The real latency of a debate is therefore ≈ `R ×` (one round), and one round
is ≈ the slowest of `D` parallel calls — not `D·R ×` a call, and not a single call. eq. (5)
contains neither `D` nor `R`; it contains one TTFT and one token total. So the single knob the
paper's own Figure 2c/2d sweeps (debate size) moves latency in a way eq. (5) can only represent by
inflating `t_c` linearly in `D·R` — which is the *serial* reading, the one §4.6 shows the system
does not use. This is the PATTERN entry (formulation narrower than the system) arriving inside a
single node rather than between nodes, and it is new: prior instances were about parallel *nodes*.
M7 does not repair it. It records `llm_invocations`, `debaters`, `rounds` in the node timing so the
critique module can say what the serial reading would have cost.

### 4.3 `ExecutorKind.TOOL` — `python_interpreter` serving `execute_tests`

Zero tokens, zero cost, zero energy, zero capacity. This is not an omission in our code; it is
A.5's accounting (§3.3 p.573 profiles "TTFT and TPOT for LLMs"; tools have no profile — A25/A31),
and M3's `workflow_profiles._zero_tokens` already encodes it.

But a tool takes **time**, and M7 has to put *something* on the clock or the node is a no-op.

`[DESIGN CHOICE]` **Tool duration is 0.0 seconds in the default path.** That is the literal
reproduction: A.5 charges tools nothing, so a faithful runtime charges them nothing, and every
headline M7 number is produced with tools at zero. An optional overlay, `tool_overlay`, can inject
`critique/tool_latency.py`'s `[INVENTED]` service times (`execute_tests = ...`, Q16) — but:

- it lives in `execution/critique/tool_overlay.py`, which `/execution/` may not import (the
  existing one-way-dependency test);
- enabling it sets `RequestTrace.tainted_by_invented = True` and appends a fidelity note, so no
  report produced with it can be quoted as a reproduction number;
- it is off by default.

The quarantine is the whole point: the *finding* is that a workflow stage with real wall-clock
contributes exactly zero to the optimizer's latency filter, and that finding is destroyed the
moment an invented magnitude is allowed into the headline. With tools at zero, `execute_tests`
appears in M7's trace as a node with a start time, a finish time equal to its start time, and a
recorded `contributes_to_eq5 = False`. **That zero-width node is itself the result.**

### 4.4 Answers

Each node returns a deterministic stub value of its declared output type (`CODE_CANDIDATES`,
`TEST_SUITE`, `TEST_RESULTS`, `CODE`), derived from the request id and the node id. No correctness
is claimed or measured. Accuracy remains a profile constant `a_c`: a "quality SLO met" result is a
tautology (the filter selected a config whose profiled `a_c` clears `τ`), exactly as M6 §11 item 5
states, and M7 changes nothing about that.

---

## 5. Tokens: what M7 can and cannot count

### 5.1 The blocker, restated

**A59** (M3): `t_c` is published per *request*, totalling every LLM call in the configuration
(Figure 2d's CDFs). Code Generation has three LLM nodes (`propose_solutions`, `write_tests`,
`rank_solutions`) and **no published apportionment**. Any split would be `[INVENTED]`, which Q19
forbids outside `critique/`. M3 records all three as `Unavailable`.

**Consequence for M7, stated without hedging: per-node token counts do not exist, therefore
per-node LLM *durations* do not exist either.** eq. (5) needs `tokens`; `tokens` per node is
`Unavailable`; so `ℓ^TTFT + tokens·ℓ^TPOT` cannot be evaluated per node for Code Generation.

### 5.2 What M7 charges, and to whom

`[DESIGN CHOICE]` M7 keeps **M6's request-level accounting unchanged**: one token draw per
request from the configuration's `TokenDistribution`, charged **once** to one `(c, m)` pair, as
A.5's eq. (3) (`Σ x·t_c`, request-denominated) requires. The DAG walk does not re-charge anything.
The fleet sees exactly what it saw at M6.

This produces a clean and uncomfortable statement:

**A96 [NEW] — the execution model and the capacity model disagree about how many LLM calls a
request is.** At runtime a Code Generation request performs three LLM node invocations (16 of them
inside `propose_solutions` alone, by §4.2's count — 18 in total for `D=4, R=4`). In eq. (3) it is
one `t_c`. The reconciliation the paper intends is that `t_c` is the *sum* over all calls, and
that is coherent for **throughput** (tokens are tokens, whoever emits them). It is **not** coherent
for **latency**: eq. (5) applies a *single* `ℓ^TTFT_m` to a token total produced by 18 separate
prefills. A request with 18 calls pays 18 TTFTs in any real system and 1 in eq. (5). This is
Arno's capacity-model critique becoming arithmetic rather than argument, and M7 is where it can be
traced: the trace records `llm_invocations` per request, and `ttft_undercount = (llm_invocations −
1) · ℓ^TTFT_m` is computable exactly, from profiled numbers only, with **no invented magnitude**.
That is the milestone's most defensible new number.

### 5.3 So what is measurable on Code Generation?

| Quantity | Status on Code Gen | Basis |
|---|---|---|
| node execution ORDER, node count, per-node executor kind | **measured** | the walk; no numbers needed |
| number of LLM invocations (incl. `D·R`) | **measured** | knobs from `ConfigKey`; integers, not magnitudes |
| `ttft_undercount` = `(n_calls − 1)·ℓ^TTFT_m` | **measured** | profiled TTFT only (A96) |
| request-level eq. (5) latency | **measured** | as M6; profiled `t_c`, TTFT, TPOT |
| queueing delay, SLO outcome | **measured** | M6's service model (already reported) |
| per-node LLM duration | **UNAVAILABLE** | A59 — no token split exists |
| observed end-to-end span with tool time | **structural only** | A94 + Q16; tools are 0.0 by default |
| overlap credit on a parallel branch | **N/A on Code Gen** | total order — needs Video Q/A |

This is the honest answer to "what can M7 sanity-check?": **structure, counts and the
request-level latency arithmetic — not per-node magnitudes.** Anyone expecting a per-node latency
breakdown for Code Generation is expecting a number the paper never published.

---

## 6. Which model serves which node

**A81** (M6): `x_{w,s,c,m}` has no executor index, so the plan carries one `m` for the whole
workflow. Table 1's Phase 1 row promises per-node assignment "refined per SLO tier by optimizer";
the optimizer has no variable with which to refine it.

`[DESIGN CHOICE]` **All LLM/COMPOSITION nodes in a request execute on the single dispatched `m`.**
It is the only reading the plan supports. The trace records `assignment_source = "plan (single m,
A81)"` on every node, so the absence of refinement is visible per node rather than in a footnote.

**A97 [NEW] — the plan does not determine how many LLM nodes a Code Generation request has.**
M3 §12.3 point 5 already noted that `rank_solutions` may be served by the `test_pass_rate_ranker`
TOOL (zero tokens) or by an LLM ranker, and that `C_w`'s knobs do not determine which. So the
executor identity comes from **Phase 1's mock LLM selector** (§8), not from the optimizer — which
means `llm_invocations`, and therefore `ttft_undercount` (A96), depends on a Phase-1 choice the
optimizer never sees and cannot revise. M7 records which executor was chosen for every node and
reports `llm_invocations` with that provenance attached.

---

## 7. Per-node timing records, and the handoff to `critical_path.py`

### 7.1 What is recorded

```
NodeTiming:
    task_id, executor, kind                 # from LogicalWorkflow
    start_s, finish_s                       # simulated seconds, from the walk
    duration_s                              # finish - start
    contributes_to_eq5: bool                # False for every TOOL node
    tokens: float | Unavailable             # Unavailable for Code Gen's LLM nodes (A59)
    llm_invocations: int                    # 1, or D*R for a COMPOSITION (A95)
    model: ModelProfileKey | None           # the single plan m (A81)
    provenance: tuple[str, ...]             # per-node caveats, e.g. "tool time 0.0 per A.5"

RequestTrace:
    request, config, model, tier, tau_s
    nodes: tuple[NodeTiming, ...]           # walk order
    observed_span_s                         # last finish - first start
    eq5_latency_s                           # the planner's own number for this request
    queue_delay_s                           # M6's, the term eq. (5) lacks
    llm_invocations_total
    ttft_undercount_s                       # (invocations - 1) * TTFT   (A96)
    tainted_by_invented: bool               # True iff tool_overlay was enabled
    fidelity_notes: tuple[str, ...]
```

### 7.2 The handoff

`execution/critique/observed_dag.py` (named in M6 §13, never built) converts `RequestTrace` into
the term/magnitude form `optimization/profiles/critique/critical_path.py` already consumes:
`eq5_seconds` vs a path over the DAG. The direction of the dependency is fixed and tested:
`/execution/` never imports `critique`; `critique` may import `/execution/`'s data types.

What changes for `critical_path.py`: today its path magnitudes come from `tool_latency.py`'s
invented constants. After M7 it can be handed **observed** node timings. Its `TermGap` — the four
structural absences from eq. (5) — does not change at all and does not need to; it was never in
doubt.

### 7.3 What the comparison can actually measure, per workflow — say this plainly

- **Code Generation**: the comparison remains **structural plus two integers**. It gains node
  order, node count, `llm_invocations`, and `ttft_undercount` (A96) — all derived from integers
  and profiled TTFT, none invented. It does **not** gain per-node durations (A59) and it has no
  parallel branch on which the `max(...)` gap exists at all (total order).
- **Video Q/A**: the comparison gains a real span. Three of four nodes are tools (so `node_tokens`
  decomposes exactly, A59), the branch `frame_extract || stt` exists, and §4.6 measured overlap
  there. But the tool magnitudes are still `[INVENTED]` and still quarantined, so the *span* is
  tainted while the *shape* is not.

Video Q/A is **out of M7's scope** (this milestone is Code Gen, per `PROGRESS.md`), but the trace
format is workflow-agnostic by construction so that a later milestone can run it without redesign.
Recorded so that no one reads §7.2 as a promise M7 delivers.

---

## 8. The mock selector is now load-bearing — what M7's numbers are worth

`PROGRESS.md` (M2b) records the defect verbatim: `MockLLMClient.keyword` scores overlap ÷
candidate description length, so **longer, more discriminating descriptions lose**. It picks the
`[INVENTED]` `fixed_interval_segmenter` over the paper's `opencv_scene_detector`, and the type
checker cannot catch it because both type-check identically.

M7 is the first milestone whose output depends on that selector's choices, so here is the exposure
ledger, stated rather than papered over:

| M7 quantity | Depends on the mock selector? | Therefore worth |
|---|---|---|
| node execution ORDER | **no** | the spec's data flow fixes it |
| node COUNT (4) | **no** | the spec fixes it |
| which EXECUTOR serves each node | **YES** | a mock's preference over a half-invented catalogue |
| `llm_invocations` (is `rank_solutions` an LLM or a TOOL? A97) | **YES** | ditto |
| `ttft_undercount` (A96) | **YES**, via `llm_invocations` | ditto — report with the executor list beside it |
| the `(c, m)` pair, `t_c`, `n_m`, routing | **no** | comes from M3/M4/M5 profiles and the MILP |
| request-level eq. (5) latency, queue delay, SLO outcome | **no** | profiled numbers + M6's service model |

**Rule for M7:** any reported quantity in the "YES" rows is printed together with the executor
assignment that produced it, and `fidelity_notes` carries the selector-bias sentence. The fix is a
real LLM client, not description tuning — out of scope here (CLAUDE.md non-goals: "No real
orchestrator LLM yet"). Q53 asks whether M7 should additionally pin Code Generation's executor
assignment to a fixed, reviewed mapping so the bias cannot silently move the numbers between runs.

---

## 9. What a single end-to-end run can and cannot establish

In the style of M6 §11, and inheriting all of it.

**Simulated:** arrival time, token draw from the profiled percentile ladder, queueing against a
FIFO token-rate backlog, per-instance capacity `n·θ_m`, eq. (5) service time, instance counts,
20-minute provisioning delay. **New in M7:** a node-by-node walk over the logical DAG with
per-node timestamps.

**Not simulated, therefore not claimable:** everything in M6 §11 (no batching engine, no KV cache,
no preemption, no network, no CPU placement, accuracy not measured) **plus three M7-specific
items**:

1. **No per-node LLM time on Code Generation** (A59). The observed span attributes essentially all
   duration to whichever node the request-level charge is anchored on. The span is real arithmetic
   over unreal apportionment.
2. **Tool time is 0.0** by default (§4.3). The observed span is a *lower bound* on end-to-end
   latency, and knowingly so.
3. **No intra-composition concurrency** (A95) and **no sibling overlap** (§3.3). Where the paper
   measured overlap (§4.6), M7's naive walk serializes. On Code Generation — a total order — this
   costs nothing; on Video Q/A it would.

**The blunt version.** A single end-to-end run establishes that the three phases **compose**: that
a spec parses into a DAG, that the DAG's configuration space is profiled, that the MILP's plan is
registrable and dispatchable, and that a request traverses all of it and comes back with a
structured trace. That is an **integration** result, and it is genuinely the first one in this
repo. It establishes **nothing** about whether Murakkab meets SLOs, because the only latencies in
the system are recomputations of eq. (5) on digitized figure reads. Any sentence of the form "M7
shows Murakkab achieves X seconds" is false by construction; the admissible form is "M7 shows that
what the plan charged for this request and what executing it consumed differ by Y, using only
profiled numbers".

---

## 10. Contact with the two standing critiques

### 10.1 Capacity model — one request, traced

M7 is the first place a **single** request's resource consumption is traceable end to end and set
beside what eq. (3) charged for it. The per-request ledger:

| Quantity | Where it comes from | eq. (3)'s view |
|---|---|---|
| LLM invocations | the walk (A96) | not represented — `t_c` is one scalar |
| tokens | one draw from `TokenDistribution` | `t_c` (p90, A46) |
| TTFTs actually paid | `llm_invocations` | one |
| tool wall-clock | 0.0 (A.5's own answer) | zero, correctly and damningly |
| capacity consumed | `tokens / θ_m` instance-seconds | `x·t_c/θ_m` |
| GPU-seconds provisioned for it | from `n_m·g_m` (A93's corrected accessor) | objective (12), not (6) — A72 |

The last row is where A72 becomes visible per request: eq. (6) charges *work consumed*, objective
(12) minimizes *fleet provisioned*, and a single request makes the wedge between them concrete.

### 10.2 HEFT / precedence — the centrepiece

Stated as prohibition + obligation, as in M4 §10.1 and M6 §12.2:

- **Prohibition.** M7 adds no precedence constraint, no makespan term, no EFT, no critical-path
  ordering, no deliberate overlap. Enforced by §3.4's three tests.
- **Obligation.** M7 records what the naive walk produced, so the gap stops being an argument
  about symbols and becomes a pair of numbers on the same request: `eq5_latency_s` (what the
  planner admitted the request on) versus `observed_span_s` + `queue_delay_s` (what running it
  took). On Code Generation the wedge is `ttft_undercount_s` plus queueing, both of which are
  computed from profiled values only.

**The honest scope limit, repeated because it is easy to oversell:** Code Generation is a total
order. The `max(...)` term — the part of the gap §4.6 actually measured — **cannot be exhibited on
it at all**. M7 demonstrates the *sum-over-nodes* half of the precedence gap and the TTFT
undercount; the *parallel-overlap* half needs Video Q/A and a later milestone. `critical_path.py`
already says exactly this in its module docstring, and M7 must not contradict it.

---

## 11. Scope: dynamic workflow requests

§3.4's second request shape (natural-language query, no workflow named) is **already accepted** by
M6: `Request.is_dynamic` exists, and M6 §3 routes the dynamic branch through M1's
`WorkflowOrchestrator`, escalating with `ExecutorOnboardingRequired` when no onboarded workflow
matches.

`[DESIGN CHOICE]` **M7 does not extend it, and does not use it for any measurement.** The named
shape is the sole measurement path, for the §8 reason: the dynamic branch's *workflow
identification* runs entirely through `MockLLMClient.keyword`, the component with the known
length-penalizing bias, so a dynamic-shape end-to-end number would compound a mock selector's
workflow choice with a mock selector's executor choices. One test (`test_dynamic_request_reaches_
the_same_walk.py`) asserts that a dynamic request which *does* resolve to `code_generation`
produces an identical trace to the named request — i.e. the branch converges — and nothing is
measured through it. Recommendation in Q47.

---

## 12. File layout and build order under `/execution/`

Build in this order, file by file, confirming each (CLAUDE.md).

```
/execution/
  DESIGN_END_TO_END.md       this file
  node_exec.py               what one node's execution means per ExecutorKind (Section 4)
  trace.py                   NodeTiming, RequestTrace (Section 7.1)
  dag_walk.py                the data-flow walk: order, binding, invocation (Section 3)
  end_to_end.py              the lifecycle: accept -> lookup -> dispatch -> walk -> trace
  critique/observed_dag.py   RequestTrace -> critical_path.py's form (Section 7.2) [import-forbidden]
  critique/tool_overlay.py   optional INVENTED tool durations (Section 4.3)        [import-forbidden]
```

Existing modules are **not modified** except for two additive changes, each confirmed separately:
`RequestOutcome` gains an optional `trace: RequestTrace | None`, and `ExecutionReport` gains
`traces` plus the three M7 fidelity notes.

**Deviation note, recorded because M6's design promised otherwise.** M6 §13 listed `build.py`,
`epoch.py`, `trigger.py`, `critique/dispatch_gap.py` and `critique/observed_dag.py`. As built,
`build_executable()` lives in `registry.py`, the epoch loop and trigger live in `runner.py`, and
`critique/` contains only `__init__.py`. M7 builds `critique/observed_dag.py` as designed;
`critique/dispatch_gap.py` (A83's realized-vs-planned split) remains unbuilt and is **not** M7's
job — flagged so it is not quietly lost.

---

## 13. Test list — each named for the property it defends

| File | Defends |
|---|---|
| `test_end_to_end_single_request.py` | one Code Gen request traverses all three phases and returns a trace with four nodes in spec order |
| `test_walk_order_is_declaration_order.py` | siblings run in declaration order, never longest-first — a HEFT implementation fails here (§3.4.2) |
| `test_walk_does_not_choose_instances.py` | the `(c, m)` pair and instance are fixed before the walk; changing the DAG cannot change the allocation (§3.4.3) |
| `test_no_precedence_scheduling.py` (extend M6's) | no makespan/EFT/critical-path identifier anywhere in `/execution/` |
| `test_tool_nodes_cost_nothing.py` | every TOOL node has `duration_s == 0.0` and `contributes_to_eq5 is False` by default — A.5's own accounting, made visible |
| `test_tool_overlay_taints_the_report.py` | enabling the overlay sets `tainted_by_invented` and adds a fidelity note; a clean report cannot contain an invented tool magnitude |
| `test_code_gen_node_tokens_are_unavailable.py` | A59 is not repaired: no per-node token count is synthesised for Code Gen, and no code path divides `t_c` by 3 |
| `test_request_is_charged_once.py` | the fleet sees exactly one token charge per request regardless of node count — eq. (3) is request-denominated (§5.2) |
| `test_ttft_undercount_is_computed.py` | A96 becomes a number, from profiled TTFT and integer invocation counts only |
| `test_debate_is_one_node_many_invocations.py` | `D·R` is recorded as a count and never as a cost; the composition stays one node (A95) |
| `test_all_llm_nodes_share_one_model.py` | A81: one `m` per request, and every node records `assignment_source` |
| `test_trace_records_selector_provenance.py` | §8: every selector-dependent quantity carries the executor assignment that produced it |
| `test_execution_never_imports_critique.py` (extend M6's) | the one-way dependency now covers `observed_dag` and `tool_overlay` |
| `test_observed_dag_feeds_critical_path.py` | `critical_path.py` consumes a `RequestTrace` without importing `/execution/`'s internals, and its `TermGap` is unchanged |
| `test_dynamic_request_reaches_the_same_walk.py` | the dynamic shape converges on the same trace; nothing is measured through it (§11) |
| `test_span_is_a_lower_bound.py` | `fidelity_notes` states the three M7 limits; a trace without them cannot be constructed (§9) |
| `test_accuracy_is_not_measured.py` | no M7 code path computes or asserts an accuracy; `a_c` remains a profile constant |

---

## 14. Open decisions for Arno (Q43–Q53) — with a recommendation for each

**Q43 — Per-node token apportionment (A59).** Invent a split (e.g. equal thirds) so per-node
durations exist, or leave `Unavailable`?
*Recommend:* **leave `Unavailable`.** Q19 forbids invented values outside `critique/`, and an
invented split would make M7's headline per-node timings fiction while looking like data. If a
plot is wanted, put an explicit equal-split in `critique/` with the usual taint.

**Q44 — Tool duration at runtime (Q16, §4.3).** Zero, or the invented overlay?
*Recommend:* **0.0 by default**, overlay opt-in and taint-marked. Zero *is* A.5's answer, and a
zero-width `execute_tests` node in the trace is a more legible finding than an invented 0.8 s.

**Q45 — Debate unrolling (A95).** One invocation, or `D·R` timed sub-invocations?
*Recommend:* **one timed invocation, `D·R` recorded as a count.** Timing `D·R` sub-calls requires
a per-call token count that does not exist, and would fabricate the very magnitude A59 denies.

**Q46 — Per-node model assignment (A81).** *Recommend:* **single plan `m` for all LLM nodes**, with
`assignment_source` on every node. It is the only reading `x_{w,s,c,m}` supports.

**Q47 — Dynamic requests in M7 (§11).** *Recommend:* **accepted, converged, not measured.** One
convergence test; the named shape is the measurement path. Reason: §8's selector bias would
compound.

**Q48 — What defines an SLO violation now that a span exists?** eq. (5) + queue (M6's current
rule), or the observed span?
*Recommend:* **keep M6's rule authoritative** and report the span alongside, never thresholded.
Thresholding the span would impose a stricter SLO than the paper defines (§3.4's τ is compared
against eq. 5) and would make M7 report violations Murakkab would not — flattering our critique
rather than measuring it. The *difference* between the two is the finding; redefining the metric
would hide it inside a pass/fail.

**Q49 — `rank_solutions`'s executor (A97).** Pin it, or take the mock selector's choice?
*Recommend:* **take the selector's choice and record it**, since that is the reproduction of §3.2's
mechanism — but print it beside `llm_invocations` every time. See Q53 for the stability concern.

**Q50 — Node outputs.** *Recommend:* deterministic typed stubs keyed by `(request_id, task_id)`.
No content model, no correctness claim; accuracy stays a profile constant.

**Q51 — Which run is the headline?** A single request into an idle fleet (no queueing, the clean
composition demonstration), or a request inside M6's loaded trace?
*Recommend:* **both, reported as a pair.** The idle run isolates the eq. (5)-vs-walk wedge with
zero queueing; the loaded run shows that wedge alongside M6's measured finding that queueing
dominates token variance as a violation cause. Neither alone is honest.

**Q52 — Sibling overlap (§3.3).** Serial (chosen) or concurrent-in-simulated-time?
*Recommend:* **serial**, and record it as a deliberate pessimism. Not load-bearing for M7 (Code Gen
is a total order) but it must be decided before Video Q/A is run through the same walk, where it
determines whether §4.6's measured overlap appears in our runtime or not. Flagged now because
changing it later would silently move a published span.

**Q53 — Pin Code Generation's executor assignment? (§8)** The mock selector's choices could shift
if any description is ever edited, silently moving `llm_invocations` and `ttft_undercount`.
*Recommend:* **yes — snapshot-test the assignment** (`propose_solutions → llm_debate_coders`, etc.)
so that a change to any executor description breaks a test with a diff, rather than quietly
changing an M7 number. This pins the *bias* in place rather than fixing it, which is the correct
move under the standing policy: the defect stays visible and stops being volatile.

---

## 15. What M7 deliberately does not do

- No precedence constraint, no makespan term, no DAG-aware allocation (§3, §10.2).
- No repair of A59 — no token split is invented (§5, Q43).
- No invented tool magnitude in any default path (§4.3, Q44).
- No re-solve, no registry change, no dispatch change, no fleet-accounting change (§2).
- No real LLM, no real tool, no correctness or accuracy measurement (§4.4, §9).
- No Video Q/A run, no parallel-branch overlap result — that needs a later milestone (§7.3).
- No Math Q/A, no OS-log-analysis (CLAUDE.md non-goals).

### New ambiguities recorded by this design

**A94** the paper never describes node-level runtime execution (§2) · **A95** a composition's
`D`/`R` structure is invisible to eq. (5), and inflating `t_c` encodes the serial reading §4.6
disproves (§4.2) · **A96** the execution model and the capacity model disagree about how many LLM
calls a request is; `ttft_undercount` quantifies it from profiled values only (§5.2) · **A97** the
plan does not determine how many LLM nodes a Code Gen request has — Phase 1's mock selector does
(§6).
