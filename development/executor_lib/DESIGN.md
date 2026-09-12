# Milestone 2 — Design: Executor Library (Code Generation) `/development/executor_lib/`

**Phase:** Development (paper Section 3.2, "Executor Library" + "Attributes", Figure 5a)
**Status:** design review pending — no implementation code exists or should exist yet.
**Scope:** the *contents* of the executor catalogue for the Code Generation workflow only
(Figure 1b, p.568; Section 2.2, p.569; Appendix A.3 + Table 6, p.585-586).

**Source of truth:** Chaudhry, Choukse, Qiu, Goiri, Fonseca, Belay, Bianchini. "Murakkab:
Resource-Efficient Agentic Workflow Orchestration in Cloud Platforms", *20th USENIX Symposium on
Operating Systems Design and Implementation (OSDI '26)*, pp. 567-587. Citations are by
section / listing / figure / table / equation with the USENIX page number (`p.572` etc.).

**Standing policy in force (Arno, 2026-09-10):** reproduce Murakkab *literally*. Where the paper
is ambiguous, unsound, or incomplete, take the paper's reading and report the problem; do not
repair it. This repo is the baseline against which Arno's own system is measured, so a silently
fixed baseline destroys the comparison.

Conventions carried over from M1's `DESIGN.md`: **[DESIGN CHOICE]** marks a decision filling a
paper silence; **[INVENTED]** marks an executor or knob the paper does not name at all. Section 9
lists ambiguities (numbering continues M1's A1-A10 from A11), Section 10 lists what is genuinely
Arno's to decide.

---

## 1. Plain-language overview (read this first)

### 1.1 What the Executor Library is

The developer's declarative spec (M1) says *what* each sub-task does, in a sentence of English:
"Given a coding problem, propose candidate code solutions…". Nothing in that sentence says which
model, which pattern, or which tool should do it. The Executor Library is the platform's **menu**:
a fixed, enumerated list of concrete things that can actually perform work, each described well
enough that an LLM can read the menu and match sentences to entries.

Section 3.2 (p.572) states the design choice in one sentence:

> "A key design choice in Murakkab is mapping a broad range of unknown tasks to executors that are
> built from a finite, known set of models and tools in the library. If none is found, Murakkab
> prompts the developer to onboard a suitable one."

### 1.2 Why "finite and known" matters

Three consequences follow from that one word *finite*, and they are why this milestone exists as a
separate artifact rather than being an afterthought of the orchestrator:

1. **Selection is a closed-set classification, not open-ended generation.** The orchestrator cannot
   hallucinate an executor; anything outside the menu triggers the developer-onboarding escalation
   (M1 Section 4.5). A finite menu is what makes that escalation path meaningful.
2. **Everything downstream is keyed on these names.** M3 attaches workflow profiles and model
   profiles to library entries; M4's configuration set `C_w` (Appendix A.5, p.586) is literally the
   cross-product of the knob domains declared here. If the menu is open-ended, `C_w` is infinite and
   the MILP is not formulable. So the library is what makes the optimizer's search space finite.
3. **Profiling is amortized over the menu, not over requests.** Section 3.3 (p.573): "Profiling is
   lightweight; performed once per configuration and reused across workflows." That reuse is only
   possible because the set of configurations is enumerable in advance — here.

### 1.3 What changes versus M1's stub

M1 shipped a deliberately minimal five-entry catalogue in `development/executor_library.py` so the
orchestrator had something to select from. It has one structural defect that M2 fixes, and one
piece of machinery M2 keeps.

- **Keep:** `InMemoryExecutorLibrary`, the `ExecutorLibrary` protocol, the `ExecutorSpec` /
  `Port` / `ParameterSpec` dataclasses in `shared/executor.py`, and the nominal type registry in
  `shared/types.py`. M2 changes none of these; it *populates* them. (See Section 7 for the one
  optional, additive field this document raises as an open question.)
- **Fix:** in M1's catalogue, three of the four Code Gen sub-tasks had exactly **one**
  type-compatible executor. `write_tests` could only be `llm_unit_test_writer`; `execute_tests`
  could only be `python_interpreter`; `rank_solutions` could only be `llm_ranker`. Only
  `propose_solutions` had two candidates. Under M1's strict nominal type-check plus positional
  arity matching, "selection" was therefore a forced move for 3 of 4 nodes: an orchestrator that
  picked uniformly at random would have scored 75% by construction. That is not a test of anything.
  M2 provides at least three viable candidates per sub-task, differing in *executor kind*, in
  *knob surface*, and in *behaviour described*, so that a wrong choice is possible and the
  regeneration and escalation paths are exercised by something real.

### 1.4 What M2 explicitly does **not** contain

**No performance numbers.** Not accuracy, not latency, not TTFT/TPOT, not energy, not cost, not
token counts. Those are Milestone 3 (Section 3.3, "Workflow Profiles" and "Model Profiles",
p.573). M2 declares *which knobs exist and what values they may take*; M3 measures *what happens*
when you take them; M4 *chooses*. If a line of this catalogue would let a reader infer that
`Phi-4` is faster than `NVLM-D-72B`, that line is in the wrong milestone.

**No parameter values.** Section 3.2 (p.572), verbatim: the orchestrator "uses these descriptions
and interfaces to rank and assign executors (models or tools) for workflow tasks, **deferring
parameter configuration to a later optimization phase (Section 3.3)**." `ParameterSpec` has no
`value` field, by design (M1 `shared/executor.py`). M2 declares the holes; M4 fills them.

**No other workflow.** Video Q/A, Math Q/A and OS-log analysis are deferred by `CLAUDE.md`.
Section 8 states precisely what would change if Video Q/A is un-deferred, without building it.

---

## 2. The contract M2 must satisfy (recap of M1 Section 3)

Implements **Section 3.2, "Executor Library" and "Attributes" (p.572)**. Reproduced here only so
this document is self-contained; the authority is `shared/executor.py`.

```python
class ExecutorKind(Enum):          # closed set, Section 3.2 p.572
    LLM = "llm"                    # 1. "specialized LLM configurations (fine-tuning, few-shot
                                   #     learning, or even just domain-specific prompting)"
    COMPOSITION = "composition"    # 2. "aggregations of models, e.g., a self-reflection or an
                                   #     LLM-Debate pattern built from multiple LLMs"
    TOOL = "tool"                  # 3. "utility modules for AI workflows to take actions with"

@dataclass(frozen=True)
class ExecutorSpec:
    name: str
    kind: ExecutorKind
    description: str                          # attribute (1): textual description
    inputs: tuple[Port, ...]                  # attribute (2): interface spec, ORDERED
    outputs: tuple[Port, ...]                 # attribute (2): exactly one, enforced
    parameters: tuple[ParameterSpec, ...]     # attribute (3): key-value list of knobs, UNVALUED
```

Invariants M1 enforces at construction, which constrain every entry below:

| Invariant | Origin |
|---|---|
| Exactly one output port | M1 [DESIGN CHOICE]: Listing 2 binds one result per call (`scenes = scene_detect(videos)`) |
| At most one variadic input port | M1 `shared/executor.py` |
| Every `Port.type` is in `TYPE_REGISTRY` | M1 Section 3.3; load-time `UnknownTypeError` |
| Names unique across the library | `InMemoryExecutorLibrary.__init__` |
| Declaration order is stable (orchestrator tie-break) | `InMemoryExecutorLibrary.all()` |

**Additional M2 rule — names are frozen once published.** Executor names become join keys for M3's
profiles and appear verbatim in the orchestrator prompt. M2 therefore reuses M1's five names
unchanged (`llm_debate_coders`, `llm_single_shot_coder`, `llm_unit_test_writer`,
`python_interpreter`, `llm_ranker`) and only adds. Renaming an entry later silently invalidates
every profile keyed on it.

### 2.1 What "a viable alternative" actually means here

M1's type-check (Section 4.4) makes selection much tighter than "the description sounds right". For
an executor to be *selectable* for a sub-task written as `results = execute_tests(candidates, tests)`
it must satisfy all of:

1. **Arity**: exactly as many input ports as the call has arguments (2 here);
2. **Positional type equality**: port *i*'s type equals the type produced by argument *i*'s source,
   nominally, with no coercion;
3. **Variadic agreement**: a list-literal argument requires `variadic=True` at that position, and
   every element type must be in `port.accepted_types`;
4. **Output type**: must equal the input type expected by whatever consumes it downstream.

So genuine alternatives must share a *signature* and differ in *behaviour* — which is exactly the
intended shape of the choice, because Section 3.2 says the orchestrator selects on "these
descriptions and interfaces". The catalogue below is built signature-first for that reason.

---

## 3. Where the parameter vocabulary comes from

### 3.1 The paper's three knob levels

Section 2.5 (p.570) partitions configuration into three levels, and Section 3.3.1 (p.574)
restates them as the optimizer's three decisions:

| Level | Section 2.5, p.570 (examples) | Section 3.3.1, p.574 (Decision) | Lives in M2? |
|---|---|---|---|
| **Workflow-level** | "whether to include a Speech-to-Text Transcript agent" | Decision 1, *Workflow configuration*: "number of frames, STT on/off, debaters and rounds" | **Yes** — as knobs on the executor that embodies the choice |
| **Agent-level** | "how many frames to extract in Frame Extractor, which LLM to use for Q/A" | folded into Decision 1 + Decision 2, *Model/tool provisioning*: "the chosen model or tool for each executor" | **Yes** — `model` and per-executor knobs |
| **Hardware-level** | "CPU vs. GPU and parallelism degree for each model" | Decision 3, *Resource allocation*: `n_m`, and "A profile encodes a specific model, GPU type, and parallelism strategy, so choosing `m` implicitly fixes the hardware and parallelism degree" | **No** — M3 model profiles |

**The hardware boundary, stated explicitly.** No executor in this catalogue declares `gpu`,
`gpu_type`, `tp` / tensor-parallel degree, `batch`, or `n_m`. Section 3.3.1 (p.574) is unambiguous:
those are *implied by the choice of model profile `m`*, not selected separately. Table 6 (p.586)
confirms the packaging — its columns are `SLO | Objective | Tier | Model | Agents | Rounds | GPU |
TP | TPOT (s) | TPS`, where `Model/GPU/TP` together identify one profile and `Agents/Rounds` are the
workflow knobs. M2 owns the right-hand pair; M3 owns the left-hand triple.

That boundary has exactly one leak, and it is the paper's, not ours — see Section 3.3.

### 3.2 The knob vocabulary M2 uses

Only five knob names appear in this catalogue. Four are paper-named; one is invented.

| Knob | Type | Domain | Source | Level |
|---|---|---|---|---|
| `model` | enum (str) | the Code Gen model set, Section 3.4 | Section 3.2, p.572: "`model` (which LLM to use)" | agent-level (§2.5) / Decision 2 (§3.3.1) |
| `D` | int | `{2, 4}` | Section 3.2, p.572: "`D` (number of debaters)"; Table 6 `Agents` column ∈ {2,4}; Figure 2c/4b, p.570/571 | workflow-level (§3.3.1 "debaters and rounds") |
| `R` | int | `{2, 4}` | Section 3.2, p.572: "`R` (number of rounds)"; Table 6 `Rounds` column ∈ {2,4}; Figure 2c/4b | workflow-level |
| `cores` | int | `{1, 2, 4, 8, 16, 32}` | Section 3.2, p.572: the frame extractor "exposes the knobs: `F` … and `cores` (number of CPU cores to run on)"; Listing 1 line 3/8 uses `"CPUs": 32` | hardware-level, but exposed as an *executor* knob by the paper — see 3.3 |
| `timeout_s` | int | `{5, 30, 120}` | **[INVENTED]** — no analogue in the paper | tool-local |

**`D` and `R` domains are declared as the literal enumerated set `{2, 4}`, not a range.** Every
place the paper reports these values — Table 6 (p.586), Figure 2c and 2d (p.570), Figure 4b (p.571)
— uses exactly 2 and 4. Under the literal-reproduction policy we declare `{2, 4}` and do not
generalize to `[1..8]`, even though a range is obviously "more useful". Two direct consequences,
both intentional: (a) there is no `D=1` configuration, so a single non-debating coder must be a
*separate executor* rather than a degenerate parameterization of the debate composition — which is
why `llm_single_shot_coder` exists as its own entry; (b) `C_w` for Code Gen is small and
enumerable, which is what M3/M4 need. (Math Q/A's Figure 16a, p.586, uses `R ∈ {4, 6, 8}` — a
different workflow, deliberately not merged in.)

### 3.3 The paper's own violation of its knob boundary — `cores`

Section 3.2 (p.572) names `cores` as an *executor* knob of the frame extraction tool. But Section
2.5 (p.570) classifies "CPU vs. GPU and parallelism degree" as **hardware-level**, and Section
3.3.1 Decision 3 (p.574) says hardware follows from the model profile. `cores` therefore sits on
the wrong side of the paper's own boundary.

Worse — and this is the part that matters for M4 — Appendix A.5 (p.586) has **no CPU resource at
all**. Its resource set is `G` = resource types with budget `B_g` and per-instance cost `c_g`,
instantiated in the evaluation as A100/H100 GPU VMs (Section 4.1, p.575); `g_m` is *parallelism for
model profile `m`*. There is no variable, parameter, or constraint into which a CPU-core count
could be substituted.

**Consequence, stated plainly because a reader should not discover it at M4:** the `cores` knob on
`python_interpreter` (and on any future frame extractor) is declared here, shown to the
orchestrator, and then **can never reach the MILP**. It cannot appear in a capacity constraint
(eq. 3 is denominated in tokens), cannot appear in the cost or energy objectives (eqs. 11-12 sum
over `n_m` GPU instances), and cannot appear in the latency filter (eq. 5 is
`ℓ^TTFT_m + t_c · ℓ^TPOT_m`). It is a knob with no consumer. We declare it anyway, because
Section 3.2 explicitly lists `cores` as an exposed knob, and we log the dead-end (A13).

### 3.4 The `model` knob domain — which LLMs may be chosen

Names only. No performance implication is asserted, and the pairing of a model with a GPU type and
tensor-parallel degree is M3's, per Section 3.3.1 Decision 3.

Code Generation model set, taken from the paper's own Code Gen figures and tables:

| Model id | Evidence |
|---|---|
| `DeepSeek-Qwen-32B` | Table 6 (p.586) `Model` column; Figure 2c/2d (p.570); Figure 4b (p.571) |
| `Gemma-3-27B` | Table 6; Figure 2c/2d; Section 4.1 policy LG baseline (p.575) |
| `Phi-4` | Table 6; Figure 2c/2d; Figure 4b |
| `NVLM-D-72B` | Table 6; Figure 4b |
| `DeepSeek-Llama-70B` | Figure 4b (p.571) configuration space only — never appears in a *chosen* Table 6 row |

**[DESIGN CHOICE]** The domain is the five-model union, not Table 6's four. Rationale: Table 6
reports what the optimizer *chose*; Figure 4b (p.571, "Large space of workflow configurations")
shows what it chose *from*, and the library's job is to define the choice space, not the outcome.
Flagged as A16 because it is arguable, and it is a one-line change if Arno prefers the four.

Storage: a single shared constant, so that M3's profiles and M2's knob domains cannot drift apart
(see Section 7, `shared/model_ids.py`). A model id is an opaque string here — it acquires GPU,
parallelism, throughput, latency, and energy only in M3.

---

## 4. The catalogue

Grouped by the sub-task it serves, per M1 Section 2.4's spec:

```python
def workflow(query):
    candidates = propose_solutions(query)               # (Query) -> CodeCandidates
    tests      = write_tests(query, candidates)         # (Query, CodeCandidates) -> TestSuite
    results    = execute_tests(candidates, tests)       # (CodeCandidates, TestSuite) -> ExecutionResults
    answer     = rank_solutions(query, [candidates, results])
    return answer                                       # (Query, [..]) -> Answer
```

Types are M1's registry (`shared/types.py`): `Query`, `CodeCandidates`, `TestSuite`,
`ExecutionResults`, `Answer`. **M2 adds no new types and does not modify `shared/types.py`.** That
is a deliberate constraint on the catalogue, not a coincidence: every alternative below is
expressible in the existing vocabulary, which is what makes it a genuine drop-in alternative rather
than a differently-shaped node.

Grounding legend: **[PAPER]** the paper names this executor or pattern for Code Generation;
**[PAPER-FORM]** the paper names this *form* or *pattern* but applies it to another workflow;
**[INVENTED]** no counterpart in the paper.

### 4.1 `propose_solutions` — (Query) → CodeCandidates

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `llm_debate_coders` | COMPOSITION | **[PAPER]** Figure 1b Coder-A/B/C + "Multi-Round Debate" arc, p.568; Section 2.2 "It adopts the *LLM Debate* framework", p.569; knob set verbatim Section 3.2, p.572 | `D`, `R`, `model` |
| 2 | `llm_self_reflect_coder` | COMPOSITION | **[PAPER-FORM]** Section 3.2 names "a self-reflection … pattern" as form 2, p.572; realized by the paper for Math Q/A (Figure 15, p.585, "Multi-Round Self-Reflect", Reflect/Re-Answer loop). Applying it to coding is ours. | `R`, `model` |
| 3 | `llm_single_shot_coder` | LLM | **[INVENTED]** (carried from M1). Justified as form 1, "specialized LLM configurations", Section 3.2 p.572, and as the no-debate baseline that `D∈{2,4}` cannot express (Section 3.2 above). | `model` |
| 4 | `llm_fewshot_coder` | LLM | **[PAPER-FORM]** form 1 verbatim includes "few-shot learning" and "domain-specific prompting", Section 3.2 p.572. The specific instantiation is ours. | `model` |

Why these are a real choice rather than padding: entry 1 is many agents × many rounds, entry 2 is
one agent × many rounds, entries 3-4 are one agent × one round differing only in prompting
strategy. That is precisely the axis Figure 2c (p.570) varies ("accuracy is sensitive to the number
of debaters and rounds in LLM Debate"), so the alternatives correspond to real, distinct points in
the paper's own configuration space — while the catalogue itself says nothing about which point is
better.

Descriptions must discriminate behaviourally (M1's obligation, Section 3.2 of that document). E.g.
for entry 2: *"Self-reflection composition: a single coder agent drafts a candidate solution, then
critiques and revises its own draft over several rounds, stopping when confident or at a round
limit. One agent, no cross-agent debate."* The trailing clause is the discriminator against
entry 1; without it, keyword-matching selection collapses the two.

### 4.2 `write_tests` — (Query, CodeCandidates) → TestSuite

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `llm_unit_test_writer` | LLM | **[PAPER]** Figure 1b Tester-A/Tester-B (LLM), p.568; Section 2.2 "tester agents generate tests", p.569 (carried from M1) | `model` |
| 2 | `llm_debate_testers` | COMPOSITION | **[PAPER]**-adjacent: Figure 1b draws *two* tester agents fully cross-connected to the coders; Section 2.2 says the agents (plural, including testers) "engage in iterative rounds of debate". Whether the testers debate is exactly M1's open item **A2**. | `D`, `R`, `model` |
| 3 | `property_test_generator` | TOOL | **[INVENTED]**. Justified only by form 3's breadth, Section 3.2 p.572 ("utility modules … or any third-party tools that follow the MCP specification", plus "Traditional ML models are also included as tools"). A non-LLM property/fuzz test generator. | `cores`, `timeout_s` |

Entry 2 is the catalogue's direct probe of M1's A2 ambiguity: if testers *are* debaters, the
orchestrator should prefer it, and the workflow then carries **two independent `(D, R)` pairs** —
which Table 6, with a single `Agents` and a single `Rounds` column per row, cannot represent. That
is a new finding, logged as A14 below.

Entry 3 exists to make one thing concrete and visible: a Tool alternative on a task that otherwise
generates tokens. Under Appendix A.5 it costs nothing — see Section 6.

### 4.3 `execute_tests` — (CodeCandidates, TestSuite) → ExecutionResults

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `python_interpreter` | TOOL | **[PAPER]** Figure 1b "Python Interp. (Tool)", p.568; Section 2.2 "execute them using a Python interpreter", p.569 (carried from M1) | `cores`, `timeout_s` |
| 2 | `sandboxed_container_runner` | TOOL | **[INVENTED]**. A stronger-isolation execution backend (container per candidate) with a different resource envelope. | `cores`, `timeout_s` |
| 3 | `llm_execution_simulator` | LLM | **[INVENTED]** — see the warning below. An LLM that *predicts* test outcomes by reading code and tests, without executing anything. | `model` |

Entries 1 and 2 are a deliberate demonstration, not filler. They are behaviourally different
(process isolation, resource envelope, startup cost) and yet **completely indistinguishable to
Appendix A.5**: both are Tools, both have no model profile, both generate zero tokens, so both
contribute exactly zero to eqs. (1)-(13). Whichever the orchestrator picks, the MILP's objective
value is identical. Section 6 develops this.

Entry 3 is the sharp edge and I am flagging it rather than shipping it silently (open question
Q3). It is the *only* `execute_tests` candidate the MILP can see at all, because it is the only one
that consumes tokens. It is also, in any honest engineering sense, the worst of the three. So the
catalogue would encode the inversion: the executor with real cost is visible; the two that actually
work are free. That is a genuinely useful illustration of the Tool gap for the baseline
comparison — and simultaneously an executor the paper never contemplates. Recommendation: include
it, marked `[INVENTED]` in its description, because the demonstration is exactly the kind of
concrete gap `CLAUDE.md` says this repo exists to surface. Arno may strike it.

### 4.4 `rank_solutions` — (Query, [CodeCandidates | ExecutionResults | TestSuite]) → Answer

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `llm_ranker` | LLM | **[PAPER]** Figure 1b "Ranker (LLM)", p.568; Section 2.2 "The final output is selected as the highest-voted solution, determined by an LLM based on both the proposed candidates and the original query", p.569 (carried from M1) | `model` |
| 2 | `llm_vote_ensemble_ranker` | COMPOSITION | **[INVENTED]**, though "highest-voted" (Section 2.2, p.569) invites it: several judge agents vote independently and the majority wins. | `D`, `model` |
| 3 | `test_pass_rate_ranker` | TOOL | **[INVENTED]**. Deterministic: rank candidates by test pass rate, no LLM. Grounded only in form 3's "Traditional ML models are also included as tools", Section 3.2 p.572. | (none) |

The second input port is variadic with `accepted_types = {CodeCandidates, ExecutionResults,
TestSuite}`, mirroring Listing 2's heterogeneous `q_a(query, [frames, transcript])` (p.572) and
M1's correction in its Section 4.3.

Entry 2 raises a naming question I am resolving rather than asking about: its debater count is
declared as **`D`**, not a new `V`. Section 3.2 defines `D` as "number of debaters" for the LLM
Debate composition; a voting ensemble is the same structural knob (how many parallel agents), and
introducing a second name for it would fragment M3's configuration enumeration for no benefit.
Note the consequence: with entries in 4.1, 4.2 and 4.4 all exposing `D`, a single Code Gen workflow
can carry three of them. See A14.

Entry 3 exposes a wart worth recording (A19): the spec calls `rank_solutions(query, [...])` with
arity 2, so any candidate **must** declare two input ports even if it ignores one. A pass-rate
ranker has no use for `Query`, but must declare a `Query` port to be selectable. Positional arity
matching, inherited from Listing 2's call syntax, forces interface padding. Not repaired.

### 4.5 Coverage summary

| Sub-task | Candidates | Kinds represented |
|---|---|---|
| `propose_solutions` | 4 | COMPOSITION ×2, LLM ×2 |
| `write_tests` | 3 | LLM, COMPOSITION, TOOL |
| `execute_tests` | 3 | TOOL ×2, LLM |
| `rank_solutions` | 3 | LLM, COMPOSITION, TOOL |
| **Total** | **13** | LLM ×5, COMPOSITION ×4, TOOL ×4 |

Every sub-task has ≥3 viable candidates spanning ≥2 executor kinds, so the orchestrator's job is a
real 4-way selection over a 13-entry menu (naive uniform accuracy ≈ 25% per node, ≈ 0.4% for the
whole workflow) rather than M1's near-forced move.

**Cross-task distractors are free.** All 13 entries are visible for every sub-task — the library is
flat and workflow-agnostic (Section 3.2: "a finite, known set"). The type-check rejects most
cross-task confusions (`python_interpreter` cannot serve `rank_solutions`: wrong output type), but
not all: `llm_debate_coders` and `llm_fewshot_coder` share a signature, as do `llm_unit_test_writer`
and `llm_debate_testers`. Those are the cases where the orchestrator must actually read the
description, and they are what M2's tests should target.

---

## 5. Selection is not the only consumer — what M3 and M4 read from here

Stated so the catalogue is designed against its real downstream contract, and so the boundary is
audit-able later:

| Consumer | Reads | Milestone |
|---|---|---|
| Orchestrator prompt (`ToolSpec` projection) | `name`, `kind`, `description`, ports, knob names + domains (values *not* requested) | M1, done |
| Type-check | ports only | M1, done |
| Workflow profiling | knob **domains**, to enumerate configurations `c ∈ C_w` to profile, and executor identity to attribute prompt/completion tokens | M3 |
| Model profiling | the `model` knob's domain, as the candidate model list to profile × GPU × parallelism | M3 |
| MILP | nothing directly — it sees `C_w`, `a_c`, `t_c`, and model profiles `m`, all produced by M3 | M4 |

The last row is the important one and it is easy to miss: **the MILP never reads an
`ExecutorSpec`.** Appendix A.5's index sets are `W, S, M, C_w, G` — there is no executor index.
Everything M2 declares reaches M4 only after M3 has flattened it into per-configuration accuracy
`a_c` and token count `t_c`. This is the mechanism behind Section 6's second finding.

---

## 6. Required contact with the known critiques

Two of M1's logged findings land directly on this catalogue. Both are reproduced faithfully and
reported, per the standing policy.

### 6.1 Every Tool in this catalogue is free, forever

Appendix A.5 (p.586-587) is denominated entirely in tokens and model profiles:

- eq. (1)-(2) allocate request rates `x_{w,s,c,m}` to **model profiles** `m ∈ M`;
- eq. (3) capacity: `μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c ≤ n_m · θ_m` — tokens against token
  throughput;
- eq. (5)/(9) latency filter: `ℓ^TTFT_m + t_c · ℓ^TPOT_m > τ_{w,s}` — one model's TTFT plus that
  model's per-output-token time;
- eq. (11) energy `Σ_m n_m e_m g_m`, eq. (12) cost `Σ_m n_m g_m c_{g(m)}` — both over model
  instances on GPU resource types.

A Tool has no model profile (`m`), generates no tokens (`t_c` contribution 0), has no `θ_m`,
`ℓ^TTFT_m`, `ℓ^TPOT_m`, or `e_m`, and requires no `g ∈ G` GPU instance. Therefore **every TOOL entry
in Section 4 contributes exactly zero cost, zero energy, zero latency, and zero capacity
consumption to the entire formulation.** This catalogue has four of them.

Concrete consequences, all of which a reader should meet here and not at M4:

1. `python_interpreter` vs. `sandboxed_container_runner` is an **unobservable** choice. The MILP's
   objective is bit-identical either way. There is no formulation-level reason to prefer one.
2. The `cores` knob is **unreachable** (Section 3.3). A.5 has no CPU resource type, so no value of
   `cores` can change any constraint or objective. Murakkab's own worked example of an executor knob
   — the frame extractor's `cores`, Section 3.2 p.572 — is a knob its own optimizer cannot use.
3. `timeout_s` is likewise unreachable, and additionally invented (A17).
4. Wall-clock time spent in the Python interpreter is invisible to the latency SLO filter, so a
   configuration can be certified as meeting `τ_{w,s}` while spending arbitrary real time executing
   tests. This is M1's A10 sharpened onto a specific catalogue entry.
5. Swapping an LLM executor for a Tool executor (e.g. `llm_unit_test_writer` →
   `property_test_generator`) makes an entire workflow stage free. If executor assignment were ever
   moved inside the optimizer, this would be a degenerate optimum. It is not, only because
   assignment is frozen at Phase 1 by the orchestrator (Table 1, p.572) — a safety property that
   holds by accident of phase ordering, not by construction.

**Not repaired.** No shadow CPU resource type, no tool-latency field, no synthetic token cost. The
gap is the deliverable.

### 6.2 Per-executor `model` knobs dead-end at M4

Table 1 (p.572) lists "Executor assignment per DAG node … Refined per SLO tier by optimizer", and
Section 3.3.1 Decision 2 (p.574) promises "the chosen model or tool for **each executor** in each
selected workflow configuration". But every A.5 decision variable is `x_{w,s,c,m}`: workflow, SLO
tier, whole-workflow configuration, **one** model. There is no executor or DAG-node index anywhere
in Appendix A.5. Corroboration: Table 6 (p.586) reports a single `Model` per configuration row, as
does Table 5 (p.585) for Video Q/A, whose Figure 1a has five distinct agents.

**Consequence for this catalogue:** M2 declares a `model` knob on nine separate executors
(5 LLM + 4 COMPOSITION). A faithful M4 can honour **one** of them. The nine per-executor `model`
knobs collapse, at M3's configuration-enumeration step, into a single workflow-level model choice.

We declare them per-executor anyway — Section 3.2's attribute (3) is per-executor, and Decision 2
promises per-executor assignment, so removing them would be *repairing* the paper. But the
declaration is not honoured downstream, and this document says so rather than letting M4 discover
it. (M1's A4; `PROGRESS.md` gaps list.)

### 6.3 A3 revisited: one `model` knob on a composition, and what is lost

Section 2.2 (p.569) says of the Code Gen agents: "Each agent plays a unique role (*e.g.*, algorithm
developer, unit tester) and **may employ the same or different LLMs**." Section 3.2 (p.572) says the
LLM Debate composition exposes exactly "`D` …, `R` …, and `model` (which LLM to use)" — singular.

**What this catalogue declares:** the paper's version. `llm_debate_coders` exposes one `model` knob
covering all `D` debaters; likewise `llm_self_reflect_coder`, `llm_debate_testers`,
`llm_vote_ensemble_ranker`. No `models: list`, no per-role model map, no `model_A`/`model_B`.

**What is lost, precisely:**

1. *Intra-composition heterogeneity.* A debate with a 72B model and a 27B model arguing — the
   canonical LLM-Debate setup in the literature the paper cites — is not declarable. The prose
   permits it; the knob set does not.
2. *Role-differentiated cost tuning.* "Big model for the coder, small model for the tester" is
   partially recoverable **across** sub-tasks, because `propose_solutions` and `write_tests` are
   separate executors with separate `model` knobs — and then it is lost again at M4 by 6.2. So the
   capability survives exactly one milestone and dies in the next.
3. *Figure 10's own setting.* Section 4.4 (p.577) reports the dynamic coding pipeline with "neither
   writer model uniformly best: the smaller model anchors the cost-efficient regime while the
   larger model contributes the highest-accuracy points **when paired with a specialized prompt or
   reviewer**." That is per-role model differentiation, demonstrated by the paper, in a workflow
   whose configuration space its own MILP cannot express.

**Not repaired.** A `models` tuple knob would be a one-line change and is explicitly *not* being
made. Logged as A15; open question Q2 if Arno disagrees.

---

## 7. File layout for the M2 implementation

```
/development/
  executor_library.py             # SHRINKS to a compatibility shim: re-exports
                                  #   InMemoryExecutorLibrary + code_generation_library from
                                  #   executor_lib, so M1's orchestrator and tests keep working.
  executor_lib/
    DESIGN.md                     # this document
    __init__.py                   # public API: code_generation_library(), default_library(),
                                  #   register_catalogue(); re-exports the catalogue tuples
    registry.py                   # InMemoryExecutorLibrary (moved from executor_library.py)
                                  #   + CATALOGUES: dict[str, tuple[ExecutorSpec, ...]] and the
                                  #   union builder. Contains NO executor definitions.
    knobs.py                      # ParameterSpec factories: model_knob(), debaters_knob(),
                                  #   rounds_knob(), cores_knob(), timeout_knob().
                                  #   One definition per knob => domains cannot drift between
                                  #   entries. Docstrings carry the §2.5 / §3.3.1 level.
    code_generation.py            # the 13 entries of Section 4, grouped by sub-task, each with
                                  #   its paper citation or [INVENTED] marker in the docstring.
    # video_qa.py / math_qa.py    # NOT created in M2. Section 8 describes what they would hold.

/shared/
  model_ids.py                    # NEW, additive: the model-name vocabulary (Section 3.4).
                                  #   Names only, zero performance data. M3 joins profiles on it.
  executor.py, types.py           # UNCHANGED by M2.

/tests/
  test_executor_lib_contract.py   # every entry: unique name, one output, ≤1 variadic port, all
                                  #   port types registered, no ParameterSpec carries a value,
                                  #   no knob named gpu/tp/batch/n_m (the §3.3 hardware boundary)
  test_executor_lib_coverage.py   # each of the 4 sub-tasks has >=3 signature-viable candidates
                                  #   spanning >=2 kinds; every entry is reachable by some
                                  #   sub-task signature (no dead entries)
  test_executor_lib_knobs.py      # D/R domains are exactly {2,4}; model domain == CODE_GEN_MODELS
                                  #   for every executor that declares `model`
  test_executor_lib_orchestration.py  # M1 orchestrator over the full catalogue: fixture mock
                                  #   reaches the expected 4-node DAG; a signature-sharing wrong
                                  #   pick is caught by the type-check and recovered
```

Build order: `shared/model_ids.py` → `executor_lib/knobs.py` → `executor_lib/registry.py` →
`executor_lib/code_generation.py` → `executor_lib/__init__.py` → `development/executor_library.py`
(shim) → tests. File by file, with confirmation, per `CLAUDE.md`.

### 7.1 Two consequences for existing M1 code (not silent)

1. **M1 tests that assert catalogue size or exact membership will fail** (`len(library) == 5`). They
   should be updated to assert *presence* of the five M1 names rather than exclusivity.
2. **`MockLLMClient`'s `keyword` mode may now choose differently.** Its `kind` cue maps
   "debate"/"rounds" to `COMPOSITION`, but the catalogue now holds four compositions, two of which
   (`llm_debate_coders`, `llm_debate_testers`) share most of their vocabulary. Fixture-mode tests
   are unaffected; keyword-mode expectations may need re-pinning. This is the point — M1's mock was
   trivially correct because the menu was trivially small.

### 7.2 One open structural question: a `level` field on `ParameterSpec`

M3 needs to know whether a knob is workflow-level (cross-multiplies into `C_w` once per workflow) or
agent-level (once per executor). Two options:

- **(a) Documentation only, recommended.** `ParameterSpec` is untouched; `knobs.py` docstrings and
  this document carry the level. Rationale: the paper's own taxonomy is *self-inconsistent*
  (A12), and A.5 has no per-knob index anyway — `a_c` and `t_c` fold every knob into the opaque
  configuration `c`, so a level tag would have no consumer inside the reproduction.
- **(b) Additive optional field** `level: Literal["workflow","agent"] | None = None`. Backward
  compatible, but it edits an approved M1 interface and encodes a taxonomy the paper contradicts
  itself on.

Recommendation: (a). Raised as Q1.

---

## 8. Forward compatibility (structure now, executors later)

`CLAUDE.md` defers Video Q/A. `PROGRESS.md` records two open reasons it may come back:
multiplexing (M5) cannot reproduce Table 2/4's colocation gain with a single workflow, and Code
Generation is a total order, so the precedence/makespan gap (M1 Section 8.1) cannot be demonstrated
on it — Section 4.6's own parallel-branch example needs Video Q/A. Retrofitting after M3 has
profiled the library is expensive, so the *structure* accommodates a second workflow now while the
*content* does not.

Three structural properties, all satisfied by Section 7's layout:

1. **The library is a union of per-workflow catalogue modules, not one hardcoded tuple.**
   `registry.py` holds `CATALOGUES: dict[str, tuple[ExecutorSpec, ...]]` and builds the flat library
   from whichever catalogues are registered. `default_library()` returns the union of all of them;
   `code_generation_library()` returns just one. Adding `video_qa.py` is a registration, not a
   refactor.
2. **Knob definitions are shared, not per-workflow.** `cores` on a Video Q/A frame extractor must be
   the *same* `ParameterSpec` as `cores` on `python_interpreter`, or M3 profiles two different
   things under one name. `knobs.py` exists for this.
3. **The type registry is additive.** `shared/types.py` is a flat frozenset of nominal names with a
   load-time validator; adding `Video`, `Scenes`, `Frames`, `Transcript`, `AnnotatedFrames` breaks
   nothing, because there is no subtyping to disturb. `Answer` is already shared across both
   workflows, which is the only overlap.

### 8.1 Exactly what would change if Video Q/A is un-deferred

Nothing in Section 4 changes. The delta is:

| Change | File | Nature |
|---|---|---|
| Add `Video, Scenes, Frames, Transcript, AnnotatedFrames` | `shared/types.py` | additive constants + registry entries |
| Add Video Q/A model ids (`Llava-OneVision-7B`, `NVLM-D-72B`, `Gemma-3-27B`, `Llama-3.2-90B`, plus `Whisper` and `OmDet` as tool backends — Section 4.1 p.575, Table 5 p.585, Listing 1 p.569) | `shared/model_ids.py` | additive; `NVLM-D-72B` and `Gemma-3-27B` overlap with Code Gen and must remain one id |
| New catalogue: scene detector (TOOL), frame extractor (TOOL, knobs `F` + `cores` — the paper's own worked example, Section 3.2 p.572), speech-to-text (TOOL/LLM), object detector (TOOL, "CNN-based image classifiers", Section 3.2 p.572), multimodal Q/A LLM | `executor_lib/video_qa.py` | new file only |
| Add the `F` knob factory, and the workflow-level `stt_enabled` on/off knob (Section 3.3.1 p.574: "STT on/off") | `executor_lib/knobs.py` | additive |
| Register the catalogue | `executor_lib/registry.py` | one dict entry |

Two things that would need *thought*, not just typing, and are therefore recorded now:

- **`stt_enabled` has no owner.** "Whether to include a Speech-to-Text Transcript agent" is
  Section 2.5's canonical **workflow-level** knob (p.570) — it toggles a *node's existence*. But
  `ExecutorSpec` attaches knobs to executors, and an executor that may not exist cannot own the knob
  that decides whether it exists. M1's `LogicalWorkflow` is a fixed DAG. This is a real modeling
  hole in the M1+M2 interface, invisible from Code Generation (which has no optional stage) and
  unavoidable in Video Q/A. Flagged as A18 now, while it is cheap.
- **Cross-workflow distraction.** A single flat library means Video Q/A executors are offered to
  Code Gen sub-tasks and vice versa. That is what Section 3.2 describes and is arguably the point
  (a shared executor ecosystem), but it roughly doubles the menu and will change orchestrator
  behaviour on the *existing* Code Gen tests. Expect to re-pin them.

---

## 9. Ambiguities, deviations, and inventions

Continuing M1's numbering (A1-A10 are in `/development/DESIGN.md` Section 9).

| # | Item | Nature |
|---|---|---|
| A11 | The paper names **no Code Generation executors** beyond Figure 1b's node labels (Coder-A/B/C, Tester-A/B, Python Interp., Ranker) and Section 2.2's prose. Alternatives 4.1#2-4, 4.2#2-3, 4.3#2-3, 4.4#2-3 are constructed by us to make selection non-trivial, each labeled [PAPER-FORM] or [INVENTED] in Section 4. | Reconstruction, unavoidable — but declared |
| A12 | **The knob taxonomy is self-inconsistent.** Section 2.5 (p.570) calls "how many frames to extract in Frame Extractor" *agent-level*; Section 3.3.1 (p.574) lists "number of frames, STT on/off, debaters and rounds" all as the *workflow configuration*. Same knob, two levels. | Paper inconsistency — flagged, taxonomy kept documentation-only (7.2) |
| A13 | **`cores` is a hardware knob exposed as an executor knob** (Section 3.2 p.572), and Appendix A.5 has no CPU resource type, so it can never reach the MILP. | Formulation gap (Section 3.3, 6.1) |
| A14 | **Multiple `(D, R)` pairs per workflow.** If `write_tests` → `llm_debate_testers` and/or `rank_solutions` → `llm_vote_ensemble_ranker`, one Code Gen workflow carries two or three `D`s and two `R`s. Table 6 (p.586) has exactly one `Agents` and one `Rounds` column per row. Either the paper's testers do not debate (M1's A2), or Table 6 under-reports the configuration. | Paper ambiguity, new in M2 — affects M3's `C_w` enumeration |
| A15 | **A3 sharpened:** the single `model` knob on a composition cannot express Section 2.2's "may employ the same or different LLMs", and Section 4.4/Figure 10 (p.577) *demonstrates* per-role model differentiation the formulation cannot represent. | Internal tension (Section 6.3) — reproduced as-is |
| A16 | **Model-domain boundary:** Table 6 (p.586) chooses among four models; Figure 4b (p.571) plots five. We declare the five-model union as the domain. | [DESIGN CHOICE] — arguable, one-line reversal |
| A17 | **`timeout_s` is entirely invented.** The paper names no tool knob other than `F` and `cores`. Its domain `{5, 30, 120}` is arbitrary and unreachable by the MILP. | [INVENTED] |
| A18 | **On/off (existence) knobs have no owner** in the `ExecutorSpec` model. `stt_enabled` (Section 3.3.1, p.574) toggles whether a node exists; knobs attach to nodes. Not exercised by Code Gen; blocking for Video Q/A. | Interface hole, surfaced early (Section 8.1) |
| A19 | **Positional arity forces interface padding.** `test_pass_rate_ranker` must declare an unused `Query` input port to match `rank_solutions(query, [...])`. Inherited from Listing 2's call-composition data flow. | Consequence of M1's binding rule — not repaired |
| A20 | **The paper names tool categories we do not instantiate** — web-search, file-search, computer-use, MCP third-party tools, CNN classifiers, Word2Vec analyzers (Section 3.2, p.572). None fits a Code Generation sub-task. Their absence is scope, not oversight. | Scope note |
| A21 | **`D`/`R` domains are the literal `{2, 4}`**, not a range, because that is all the paper ever reports for Code Gen (Table 6; Figures 2c/2d, 4b). Consequence: no `D=1`, hence `llm_single_shot_coder` as a separate entry. | Literal-reproduction consequence |

Candidates for `architecture-decisions.md`: **A12, A13, A14, A18**, plus the Section 6.1
enumeration of Tool-invisibility consequences (which strengthens M1's already-logged Tool gap with
a concrete "two executors, identical objective value" instance).

---

## 10. Decisions — RESOLVED 2026-09-10

All five were decided by Arno on 2026-09-10; every one took the recommendation, so the catalogue
in Sections 3-5 stands as written and needs no revision. Recorded here so they are not re-opened.

| # | Decision | Resolution |
|---|---|---|
| Q1 | `ParameterSpec.level` | **Document-only.** No new field on M1's approved interface. The paper's own three-level taxonomy is self-contradictory (A12) and `a_c`/`t_c` fold all knobs into an opaque `c`, so a level tag would have no consumer. |
| Q2 | Single `model` knob on compositions | **Keep, literally.** A `models` tuple would be a repair; barred by the reproduce-literally policy. Consequence in 6.3 stands. |
| Q3 | Ship `llm_execution_simulator` | **Include, clearly marked.** Its purpose is to make the Tool-invisibility inversion demonstrable (4.3, 6.1): it is the only `execute_tests` candidate A.5 can see. |
| Q4 | `model` domain size (A16) | **Five**, per Figure 4b p.571 — the full plotted space, not Table 6's four selected models. Avoids baking the paper's outcome into the input space. |
| Q5 | Ship `llm_debate_testers` (A2) | **Include.** A14's double-`(D,R)` problem is deferred to M3, not pre-empted here. |

**One decision deliberately deferred, and it gates M3.** Whether Video Q/A is un-deferred is to be
settled *at the M3 boundary*, before profiling starts. Two open problems need it: M5's multiplexing
cannot reproduce Table 2's gain with a single workflow, and Code Generation is a total order with no
parallel branch on which to demonstrate the precedence gap. M2 is therefore Code-Gen-only as
designed, but structured per Section 8 so a second workflow's executors drop in without
restructuring. Do not start M3 without answering it — retrofitting after profiling is the expensive
path.

### Original framing (superseded, kept for traceability)

1. **Q1 — `ParameterSpec.level`.** Document-only (recommended) vs. an additive optional field on an
   approved M1 interface. See 7.2.
2. **Q2 — Keep the single `model` knob on compositions?** Recommended: yes, literally, per Section
   6.3. Overruling it (a `models` tuple) would make the catalogue express something the paper's
   prose allows but its knob set and MILP do not — a repair, with the comparison cost that implies.
3. **Q3 — Ship `llm_execution_simulator`?** An invented executor whose only virtue is that it makes
   the Tool-invisibility inversion demonstrable inside the catalogue (Section 4.3). Recommended:
   include, clearly marked. Strike it if the catalogue should contain only executors a reasonable
   engineer would deploy.
4. **Q4 — Five-model domain or Table 6's four?** (A16). Recommended: five.
5. **Q5 — Does `write_tests` get `llm_debate_testers`?** This is M1's A2 resurfacing as a concrete
   catalogue entry. Including it is cheap and makes the ambiguity testable; it also creates the
   double-`(D,R)` problem (A14) that M3 must then answer. Recommended: include, and settle A14 at
   M3 rather than pre-empting it here.
