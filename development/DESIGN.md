# Milestone 1 — Design: Declarative Spec + Workflow Orchestrator (`/development/`)

**Phase:** Development (paper Section 3.2, Figure 5a)
**Status:** design review pending — no implementation code exists or should exist yet.
**Scope:** Code Generation workflow only (Figure 1b, Section 2.2, Appendix A.3).

**Source of truth:** Chaudhry et al., "Murakkab: Resource-Efficient Agentic Workflow
Orchestration in Cloud Platforms", *20th USENIX Symposium on Operating Systems Design and
Implementation (OSDI '26)*, pp. 567-587. All citations below are to the OSDI version by
section / listing / figure / table / equation number, with the USENIX page number where it
helps (`p.572` etc.). The arXiv preprint (2508.18298v2) is the same work with different
numbering and is **not** cited here.

This revision was written against the PDF directly. Every claim below is either verified in the
paper (cited) or is an explicit design decision filling a paper silence (labeled
**[DESIGN CHOICE]**). Section 9 lists what the paper genuinely leaves open; Section 10 lists
the few decisions that are the reproduction author's to make.

---

## 1. Plain-language overview (read this first)

### 1.1 What problem this phase solves

Today, building an agentic application means writing *what* you want done and *how* it runs in
the same breath. The paper's Listing 1 (p.569) is the illustration: a video Q/A workflow where
the developer hardcodes `Whisper` for transcription, `Llama-3.2` for reasoning, `"CPUs": 32`,
`"PTUs": 50`, `"batch": 256`, `"num_frames": 15`, and API keys — all interleaved with the
actual data flow. The paper calls this "tightly coupled application logic and execution
details" and, in Section 2.3, "Rigid and Imperative Definitions". Because the platform only
sees opaque API calls, it cannot swap in a cheaper model, batch across tenants, or right-size
hardware.

Murakkab splits the two apart (Section 3.2, "Declarative Specification"):

- The **developer** writes only the *what*: sub-tasks in natural language plus the data flow
  between them. "Configuration details (*e.g.*, which LLM to use, number of frames to extract,
  resource allocation) are omitted from the specification" (Section 3.2, p.573).
- The **platform** decides the *how*, in two stages:
  1. **This milestone (Section 3.2):** the Workflow Orchestrator, "an LLM with tool-calling
     capabilities", maps each sub-task to an executor from a "finite, known set of models and
     tools in the library", producing a *Logical Workflow* DAG. Parameter configuration is
     explicitly "deferred to a later optimization phase (Section 3.3)".
  2. **Later milestones (Section 3.3, M3-M5):** the optimizer picks the actual model, GPU,
     parallelism, and knob values by solving the MILP of Appendix A.5.

### 1.2 What this milestone produces

The **Logical Workflow** (Section 3.2, p.573), quoted:

> "This abstract execution plan captures the functional intent of each task without binding to
> specific models, resources, or hardware. It is represented as a directed acyclic graph (DAG),
> where nodes are executors and edges denote data flow. This representation remains
> request-agnostic, containing no per-request details such as query text, input payloads, or
> SLOs. Execution specifics (*e.g.*, model selection or hardware allocation) are deferred to
> later stages."

Two properties fall straight out of that sentence and are the acceptance criteria for M1:
**unconfigured** (parameters are declared holes, never values) and **request-agnostic** (no
query, no payload, no SLO). Listing 2 (p.572) enforces the second one *syntactically*: `query`
and `videos` are **parameters of `def workflow(...)`**, and their concrete values plus the SLO
appear only in the separate "Execution with example request" section, at
`run(workflow(query, videos), slo=LOW_LATENCY)`. The workflow body never sees a value. Our
design reproduces exactly that boundary.

### 1.3 Why an LLM does the executor selection

Sub-task descriptions are natural language; executor descriptions are natural language. Section
3.2 (p.573): the orchestrator "receives a list of available executors and their interfaces,
along with task descriptions, and selects the best executor for each sub-task". Note the plural
— one call carrying all task descriptions, not one call per task. The catalogue is finite and
closed, and when nothing fits, "Murakkab prompts the developer to onboard a suitable one"
(Section 3.2, p.572).

### 1.4 Why type-checking exists

Section 3.2, p.573, verbatim:

> "The orchestrator performs type-checking on the DAG to ensure output types from source nodes
> match input types of destination nodes. In case of mismatches, the workflow is regenerated
> with error feedback to the LLM. Persistent errors prompt the developer to revise the
> specification."

So: check, regenerate with feedback, and on persistence escalate to the human. The paper does
**not** state how many regenerations "persistent" means — that bound is ours (Section 4.5).

---

## 2. The declarative specification (what a developer writes)

Implements **Section 3.2, "Declarative Specification" and Listing 2 (p.572)**.

### 2.1 Format: a Python DSL, matching Listing 2

Listing 2 is reproduced verbatim below from p.572 (it is the paper's own caption: "Murakkab's
declarative workflow specification of the video Q/A abstracts away configuration details,
letting developers focus on application logic"):

```python
# == Sub-tasks in the workflow ==
scene_detect  = "Given a list of videos, identify scenes in each."
frame_extract = "Given a list of scenes, extract frames."
stt           = "Given a list of scenes, convert audio to text."
q_a           = "Answer the query given some context."
# == Workflow description (sub-tasks and data flow) ==
def workflow(query, videos):
    scenes     = scene_detect(videos)
    frames     = frame_extract(scenes)
    transcript = stt(scenes)
    answer     = q_a(query, [frames, transcript])
    return answer
# == Execution with example request ==
query  = "What is the name of the person wearing the red dress?"
videos = ["road_trip.mp4"]
result = run(workflow(query, videos), slo=LOW_LATENCY)
```

Everything the format needs is visible here:

| Element | Meaning |
|---|---|
| `name = "<natural language>"` at module level | declares a sub-task; the string is its entire description |
| `def workflow(<params>)` | the workflow; parameters are the **boundary inputs** (names only, no values) |
| `y = subtask(a, b)` inside the body | a DAG node; **data flow is positional Python call composition** |
| `[frames, transcript]` as an argument | fan-in: several upstream results into one argument position |
| `return answer` | the workflow output |
| everything after the `def` | the *request*: concrete values and `slo=` — **not part of the workflow** |

There are no channel names, no `consumes`/`produces` lists, and no developer-written types.
An earlier draft of this document invented all three; they are gone.

### 2.2 How the DSL is turned into a graph: AST parsing **[DESIGN CHOICE]**

Listing 2 as printed is not executable Python — a `str` is not callable, so `scene_detect(videos)`
would raise. The paper's Listing 1 caption calls its analogue "Simplified", and the paper never
specifies the runtime machinery. Two ways to close that gap:

- **Symbolic tracing:** wrap each sub-task string in a callable that records invocations, then
  execute `workflow(...)`. Requires the developer to write `SubTask("...")` instead of a bare
  string, i.e. it *changes Listing 2's surface syntax*. Rejected for that reason.
- **AST parsing (chosen):** parse the source with `ast`, never execute it. Listing 2's syntax is
  preserved character-for-character, developer code is never run at spec-load time, and the
  `run(...)` line is inert by construction — which is a structural guarantee of
  request-agnosticism rather than a promise.

Parsing rules (any violation is a `SpecValidationError` naming the source line):

1. Module-level `NAME = "<string literal>"` before the workflow → a sub-task description.
2. Exactly one `def workflow(...)`. Its parameters are boundary inputs.
3. Body statements must be `NAME = subtask_name(args...)` or a final `return NAME`.
4. Each argument is a parameter name, a previously-assigned name, or a list literal of those.
   Argument *position* is the data-flow order, preserved on the node.
5. No loops, conditionals, comprehensions, re-assignment of an existing name, nested defs, or
   calls to anything that is not a declared sub-task. This is what keeps the graph a DAG, as
   Section 3.2 requires ("represented as a directed acyclic graph"). A `for` loop in the spec
   is rejected with an explicit message rather than silently unrolled.
6. Statements after the workflow definition are recognized as the **execution section** and
   discarded. Concretely: any assignment feeding `run(...)`, and the `run(..., slo=...)` call
   itself, never reach the Logical Workflow. `slo=` appearing anywhere *inside* `def workflow`
   is a hard error.

### 2.3 Developer execution preferences — allowed, and not part of the DAG

Section 3.2 (p.573) is explicit and it contradicts the blanket "ban all configuration" rule an
earlier draft of this document proposed:

> "However, Murakkab does not restrict developers from specifying any execution preferences
> (*e.g.*, particular LLM choice or hardware constraint), which are then incorporated into the
> optimization process as constraints."

So the loader does **not** reject a stated preference. It captures preferences into a separate
`ExecutionPreferences` side-channel that travels beside the Logical Workflow to the optimizer,
where they become MILP constraints (fixing an `x_{w,s,c,m}` to zero for disallowed models, or
bounding `n_m` per resource type — the exact encoding is M4's problem). Two rules:

- Preferences never enter `LogicalWorkflow` nodes. A node still carries only "which executor",
  never "which model". Otherwise Section 3.2's "without binding to specific models, resources,
  or hardware" is violated.
- Per-**request** details remain banned outright inside the workflow body: query text, input
  payloads, and SLOs, quoting the request-agnostic sentence. This is the narrowed, defensible
  version of the earlier deny-list: it now bans exactly the three things the paper names, and
  nothing more.

The paper does not specify the *syntax* for preferences (open item A7, Section 9). M1 accepts
them only as an optional argument to the loader, not as new DSL syntax, so no syntax is invented.

### 2.4 The Code Generation workflow (Figure 1b, Section 2.2, Appendix A.3)

**The paper contains no declarative listing for Code Generation** — Listing 2 covers Video Q/A
only. The spec below is therefore constructed by applying Listing 2's format to the Code
Generation workflow the paper *does* describe. The sources for the structure are verified:

Figure 1b (p.568), read off the figure: `Query` → `Coder-A (LLM)`, `Coder-B (LLM)`,
`Coder-C (LLM)`, with a **Multi-Round Debate** arc drawn back over the three coders → fully
cross-connected to `Tester-A (LLM)` and `Tester-B (LLM)` → `Python Interp. (Tool)` →
`Ranker (LLM)` → `Answer`. Caption: "Code generation workflow: text-only with an LLM Debate
structure to write, test and execute code."

Section 2.2, "Code Generation" (p.569), verbatim: "It adopts the *LLM Debate* framework, where
coder agents propose candidate solutions and tester agents generate tests and execute them
using a Python interpreter. Each agent plays a unique role (*e.g.*, algorithm developer, unit
tester) and may employ the same or different LLMs. The agents engage in iterative rounds of
debate, aiming to reach consensus or terminating after a pre-defined number of rounds. The
final output is selected as the highest-voted solution, determined by an LLM based on both the
proposed candidates and the original query."

Appendix A.3 (p.585) + Table 6 (p.586): the knobs reported for this workflow are "model, number
of debaters, number of debate rounds"; Table 6's columns are
`SLO | Objective | Tier | Model | Agents | Rounds | GPU | TP | TPOT (s) | TPS`, with **one**
`Model` per row and `Agents ∈ {2,4}`, `Rounds ∈ {2,4}`.

Proposed spec, `development/specs/code_generation.py`:

```python
# == Sub-tasks in the workflow ==
propose_solutions = "Given a coding problem, propose candidate code solutions by having multiple agents debate and revise them over several rounds."
write_tests       = "Given a coding problem and candidate code solutions, write unit tests that check them."
execute_tests     = "Execute the candidate code solutions against the unit tests and report the results."
rank_solutions    = "Select the highest-voted solution given the candidate solutions, their test results, and the original query."
# == Workflow description (sub-tasks and data flow) ==
def workflow(query):
    candidates = propose_solutions(query)
    tests      = write_tests(query, candidates)
    results    = execute_tests(candidates, tests)
    answer     = rank_solutions(query, [candidates, results])
    return answer
# == Execution with example request ==
query  = "Write a function that returns the longest common subsequence of two strings."
result = run(workflow(query), slo=HIGH_ACCURACY)
```

Intended mapping onto Figure 1b, and onto executors the orchestrator should select:

| Sub-task | Figure 1b nodes | Expected executor | Knobs (deferred to optimizer) |
|---|---|---|---|
| `propose_solutions` | Coder-A/B/C + the Multi-Round Debate arc | **Structured composition**: LLM Debate | `D` (debaters), `R` (rounds), `model` |
| `write_tests` | Tester-A, Tester-B | **LLM** | `model` |
| `execute_tests` | Python Interp. | **Tool** | (tool knobs, e.g. timeout) |
| `rank_solutions` | Ranker | **LLM** | `model` |

Note that this exercises all three executor forms of Section 3.2 in one workflow, which is
exactly what M1 needs to test.

**The debate loop is a knob, not a cycle.** Figure 1b's back-arrow is *internal to the LLM
Debate composition*, which Section 3.2 (p.572) names as a structured composition exposing "`D`
(number of debaters), `R` (number of rounds), and `model` (which LLM to use)". Section 3.2
(p.573) requires the Logical Workflow to be a DAG. So iteration surfaces as `R`, a parameter
the optimizer sets (Table 6's `Rounds` column), and never as a graph edge. This is settled by
the paper, not a judgement call.

**One genuine ambiguity here** (logged as A2 in Section 9): whether the tester agents are a
separate sub-task, as designed above, or additional debaters *inside* the same LLM Debate
composition. Table 6 reports a single `Agents` count for the whole workflow, which is
consistent with either reading. The design above picks "separate sub-task" because Figure 1b
draws the debate arc over the coders only, and because collapsing testers into the composition
would leave `write_tests` with no node and make the Python interpreter a dangling input. This
is flagged, not silently resolved.

---

## 3. Executor Library interface contract

Implements **Section 3.2, "Executor Library" and "Attributes" (p.572)**. The library's
*contents* are Milestone 2; M1 defines the interface M2 must satisfy plus a minimal mock
catalogue.

### 3.1 The three forms — verbatim from Section 3.2

> "1. **LLM**: specialized LLM configurations (fine-tuning, few-shot learning, or even just
> domain-specific prompting); 2. **Structured compositions**: aggregations of models, *e.g.*, a
> self-reflection or an LLM-Debate pattern built from multiple LLMs; 3. **Tool**: utility
> modules for AI workflows to take actions with (*e.g.*, OpenCV frame extractor for video
> processing, web-search, file-search, computer-use, or any third-party tools that follow the
> MCP specification). Traditional ML models are also included as tools (*e.g.*, CNN-based image
> classifiers or Word2Vec sentiment analyzers)."

`ExecutorKind` is therefore a closed enum of exactly `LLM | COMPOSITION | TOOL`.

**A composition is opaque at this layer**, with a single `model` knob. That is the paper's own
framing: "The LLM Debate composition exposes the knobs: `D` (number of debaters), `R` (number
of rounds), and `model` (which LLM to use)" (Section 3.2, p.572), corroborated by Table 6's
single `Model` column per configuration row. The orchestrator sees one node; Figure 1b is
drawing that node's internals. (The tension with Section 2.2's "may employ the same or
different LLMs" is real and is logged as A3 — not resolved here.)

### 3.2 The three attributes — verbatim from Section 3.2, "Attributes"

> "Each model or tool in the library exposes three attributes: (1) a textual description, (2) an
> interface specification, and (3) a key-value list of configurable parameters. For example, the
> frame extraction tool exposes the knobs: `F` (number of frames to extract) and `cores` (number
> of CPU cores to run on). ... The *orchestrator* uses these descriptions and interfaces to rank
> and assign executors (models or tools) for workflow tasks, deferring parameter configuration
> to a later optimization phase (Section 3.3)."

```python
class ExecutorKind(Enum):
    LLM = "llm"
    COMPOSITION = "composition"
    TOOL = "tool"

@dataclass(frozen=True)
class Port:
    name: str
    type: str              # nominal type name from the shared type registry (3.3)
    variadic: bool = False # accepts a list-literal argument, cf. q_a(query, [frames, transcript])

@dataclass(frozen=True)
class ParameterSpec:
    """One entry of the paper's 'key-value list of configurable parameters' (Section 3.2).
    Declared here, VALUED by the optimizer (Section 3.3). No value field, by design."""
    name: str                                  # e.g. "D", "R", "model", "F", "cores"
    kind: Literal["int", "float", "str", "enum"]
    domain: tuple | None                       # e.g. (2, 4) for Agents/Rounds per Table 6

@dataclass(frozen=True)
class ExecutorSpec:
    name: str
    kind: ExecutorKind
    description: str                    # attribute (1)
    inputs: tuple[Port, ...]            # attribute (2), ordered — positional binding
    outputs: tuple[Port, ...]           # attribute (2)
    parameters: tuple[ParameterSpec, ...]   # attribute (3)
```

Obligations on Milestone 2: names unique and stable (they become tool names in the prompt and
join keys for M3 profiles); every `Port.type` must exist in the registry; `parameters` must be
complete, because the optimizer never reads executor internals; descriptions must discriminate
on behaviour, since they are the orchestrator's only selection signal.

For Code Generation, M2 must at minimum provide an LLM-Debate composition with knobs `D`, `R`,
`model` (Section 3.2 / Table 6), a Python-interpreter tool, and general-purpose LLM executors.

### 3.3 The type registry **[DESIGN CHOICE]**

The paper mandates type-checking on the DAG (Section 3.2, p.573) but never specifies a type
vocabulary; the declarative spec contains no types at all, so **all types come from executor
interface specifications**. A minimal nominal vocabulary is therefore required for the paper's
own check to be executable. For Code Generation: `Query`, `CodeCandidates`, `TestSuite`,
`ExecutionResults`, `Answer`. Strict nominal equality, no subtyping, no coercion — a
`Text`-for-everything vocabulary would make the paper's check vacuous.

### 3.4 Library interface

```python
class ExecutorLibrary(Protocol):
    def all(self) -> tuple[ExecutorSpec, ...]: ...
    def get(self, name: str) -> ExecutorSpec: ...   # raises UnknownExecutorError
```

Flat and finite, matching "a finite, known set of models and tools in the library"
(Section 3.2, p.572). No retrieval layer.

---

## 4. Workflow Orchestrator

Implements **Section 3.2, "Workflow Orchestrator" and "Logical Workflow" (p.573)**, and Table 1
(p.572) Phase 1 rows: "Workflow DAG structure" and "Executor assignment per DAG node", both
"Once at onboarding", scope "Workflow".

### 4.1 Pipeline

```
code_generation.py  (declarative spec, Listing-2 form)
   -> AST parse -> TaskGraph (nodes = sub-tasks, edges = positional data flow)   [Section 2.2]
   -> ONE LLM call: all task descriptions + full executor catalogue -> assignment
   -> positional port binding
   -> DAG type-check (source output type == destination input type)
   -> ok?  yes -> LogicalWorkflow  ->  /optimization/
           no  -> regenerate with error feedback to the LLM  (bounded, Section 4.5)
                  -> exhausted -> escalate: "revise the specification"
   (any task with no suitable executor -> escalate: "onboard a suitable one")
```

The AST parse settles the *DAG structure*; the LLM settles the *executor assignment*. That
split matches Table 1, which lists those as two separate Phase-1 decisions.

### 4.2 What the LLM is shown — one workflow-level call

Section 3.2, p.573: the orchestrator "receives a list of available executors and their
interfaces, along with task descriptions, and selects the best executor for each sub-task", and
Section 3.2, p.572: it "uses these descriptions and interfaces to rank and assign executors
(models or tools) for workflow tasks". Plural task descriptions, one interaction. So M1 issues
**one call per orchestration attempt**, carrying:

- every sub-task's id and natural-language description,
- the data-flow structure (which sub-task feeds which argument position of which), so the model
  can reason about wireability across the whole graph rather than one node at a time,
- the full executor catalogue: `name`, `kind`, `description`, ordered input/output ports with
  types, and parameter **names and domains**.

Parameters are shown but flagged not-to-be-chosen, because Section 3.2 defers "parameter
configuration to a later optimization phase". The model must know a debate executor *has* a `D`
knob to judge fit; it must not set `D`. Any parameter values returned are discarded.

### 4.3 Port binding: positional

Listing 2's data flow is positional Python composition, so the i-th call argument binds to the
i-th input port of the selected executor. No inference, no channel names — the earlier draft's
type-driven binding heuristic is deleted; the DSL already carries the order.

A list-literal argument (`q_a(query, [frames, transcript])`, Listing 2 line 11) binds several
upstream results to one port; that port must be `variadic`. Arity mismatch (call arity !=
executor input-port count) is reported as a type-check failure and fed to the regeneration loop,
since choosing a different executor is exactly the fix.

> **Correction applied during implementation (M1 build).** An earlier revision of this section
> required *every element of a list-literal argument to have the same type as the port*. That is
> wrong, and Listing 2 itself is the counter-example: `q_a` is described as "Answer the query
> given some context", and its list argument `[frames, transcript]` mixes extracted frames with
> a speech-to-text transcript — two different types into one argument position. The same applies
> to `rank_solutions(query, [candidates, results])` in Section 2.4, which mixes `CodeCandidates`
> with `ExecutionResults`. A variadic port therefore declares a **set of accepted types**
> (`Port.accepted_types`), and each element must be a member of that set. Non-variadic ports are
> unchanged: exactly one source, exact nominal equality.

### 4.4 Type-checking

Implements Section 3.2, p.573 verbatim: "output types from source nodes match input types of
destination nodes". Checks:

1. **Edge type equality** — for every edge, `source.output.type == destination.input.type`,
   nominal, no coercion or adapter insertion.
2. **Arity** — call arity equals the executor's input-port count.
3. **Variadic consistency** — a list-literal argument requires a variadic port, and every
   element's type must be in that port's `accepted_types` set (see the correction in 4.3).
   A non-variadic port takes exactly one source.
4. **Boundary types** — workflow parameters (e.g. `query`) adopt the type of the port they first
   feed; if the same parameter feeds two ports of different types, that is a mismatch.
5. **Acyclicity** — guaranteed by the AST rules (Section 2.2 rule 5), re-asserted after binding.

Only checks 1-4 depend on executor selection; those are the ones the regeneration loop can fix.

### 4.5 Regeneration loop, and the retry bound

The behaviour is the paper's ("the workflow is regenerated with error feedback to the LLM.
Persistent errors prompt the developer to revise the specification"). **The number is not.**

```
MAX_ORCHESTRATION_ATTEMPTS = 3     # 1 initial + 2 regenerations
```

**[DESIGN CHOICE — the paper gives no retry bound; "persistent" is unquantified. This is an
implementation decision filling a paper silence, not reproduction of a stated value.]**

On a failed attempt, the orchestrator re-issues the workflow-level call with:

- the previous full assignment,
- the structured errors, each naming task, executor, port, and both types, e.g.
  `execute_tests -> 'llm_code_reviewer': input port 0 has type Query, but upstream
  propose_solutions produces CodeCandidates`,
- the list of already-rejected `(task, executor)` pairs, reported as tried but not hard-banned
  (a pair can become valid once a neighbour changes).

Tasks that type-checked cleanly keep their assignment unless the LLM changes them, so the loop
converges rather than thrashing.

Two distinct escalation paths, both taken straight from the paper:

- **No suitable executor** for some sub-task → escalate immediately, do not burn attempts:
  "If none is found, Murakkab prompts the developer to onboard a suitable one" (Section 3.2,
  p.572). Message names the sub-task and asks for library onboarding.
- **Persistent type errors** after `MAX_ORCHESTRATION_ATTEMPTS` → `OrchestrationFailure`
  carrying every attempt, every error, and the executors that would have type-checked per task:
  "Persistent errors prompt the developer to revise the specification" (Section 3.2, p.573).

The orchestrator never silently falls back to a mechanical type-correct pick. That would defeat
both escalation paths. Section 3.2 also notes "A feedback loop allows developers to inspect and
refine the generated specification, supporting hybrid workflows with both manual and
system-generated tasks" — M1 realizes the inspect half by making `LogicalWorkflow` printable and
JSON-serializable; interactive refinement is not built.

### 4.6 The Logical Workflow output

```python
@dataclass(frozen=True)
class LogicalNode:
    task_id: str
    task_description: str                        # the developer's natural-language string
    executor: str                                # name into the ExecutorLibrary
    inputs: tuple[InputBinding, ...]             # positional; each -> upstream task or boundary param
    open_parameters: tuple[ParameterSpec, ...]   # UNBOUND. Valued by the optimizer (Section 3.3).

@dataclass(frozen=True)
class LogicalEdge:                # "edges denote data flow" (Section 3.2, p.573)
    src_task: str
    dst_task: str
    dst_arg_index: int
    type: str

@dataclass(frozen=True)
class LogicalWorkflow:
    workflow_id: str
    nodes: tuple[LogicalNode, ...]     # topologically ordered
    edges: tuple[LogicalEdge, ...]
    inputs: tuple[Port, ...]           # boundary params: names and types only, never values
    outputs: tuple[Port, ...]
```

Construction-time invariants, asserting the request-agnostic sentence mechanically: no field
holds a query string, payload, SLO, model name, or hardware name, and `open_parameters` never
holds a value. `ExecutionPreferences` (Section 2.3) is a *sibling* object, not a field of the
DAG.

---

## 5. The `LLMClient` abstraction

Current placeholder `shared/llm_client.py` has the right boundary and the wrong granularity: its
`select_executor(task_description, candidates) -> str` is per-task, but Section 3.2 describes a
single call receiving all task descriptions. It also cannot express error feedback (needed for
the regeneration loop) or "no suitable executor" (needed for the onboarding escalation).
Proposed shape, to be applied in the build step:

```python
@dataclass(frozen=True)
class ToolSpec:
    """Prompt-facing projection of one ExecutorSpec — the paper's three attributes."""
    name: str
    kind: str
    description: str                       # attribute (1)
    interface: dict[str, Any]              # attribute (2): ordered typed ports
    parameters: dict[str, Any]             # attribute (3): names + domains, VALUES NOT REQUESTED

@dataclass(frozen=True)
class TaskDescription:
    task_id: str
    description: str
    upstream: tuple[str | None, ...]       # per argument position: task id, or None for boundary

@dataclass(frozen=True)
class AssignmentFeedback:
    previous: Mapping[str, str]
    errors: tuple[str, ...]
    rejected: tuple[tuple[str, str], ...]  # (task_id, executor) already tried

@dataclass(frozen=True)
class ExecutorAssignment:
    assignments: Mapping[str, str]         # task_id -> executor name
    unmatched: tuple[str, ...]             # tasks with no suitable executor -> onboarding path
    rationale: Mapping[str, str]

class LLMClient(ABC):
    @abstractmethod
    def assign_executors(
        self,
        workflow_id: str,
        tasks: Sequence[TaskDescription],
        candidates: Sequence[ToolSpec],
        feedback: AssignmentFeedback | None = None,
    ) -> ExecutorAssignment: ...
```

`ToolSpec` stays in `shared/` as the prompt-facing projection of `ExecutorSpec`, so the library
can hold fields (profiling hints, internal ids) that never reach the prompt.

### 5.1 Mock client behaviour **[DESIGN CHOICE — the placeholder file explicitly defers this
to this document]**

`MockLLMClient`, deterministic, four modes:

- **`fixture` (default in tests):** an explicit `{task_id: executor_name}` map given at
  construction. Makes DAG assertions exact.
- **`keyword`:** normalized token overlap between each task description and each candidate's
  description/name, plus a `kind` cue (verbs like "execute"/"run" favour `TOOL`; "debate",
  "multiple agents", "rounds" favour `COMPOSITION`). Highest score wins; ties break on library
  declaration order. Exercises "plausible but unverified choice" without a network call.
- **`faulty`:** returns a type-incompatible executor for a configured task on attempt 1 and a
  correct one on attempt 2, so the regeneration loop and its feedback text are actually tested.
- **`faulty_forever`:** never recovers, driving the persistent-failure escalation. A
  `no_match` flag additionally returns a non-empty `unmatched` to drive the onboarding path.

All modes honour `feedback.rejected` (except `faulty_forever`) and never emit parameter values.

---

## 6. Proposed file layout

```
/development/
  DESIGN.md                       # this document
  __init__.py
  specs/
    code_generation.py            # the declarative spec, Listing-2 form (Section 2.4)
  spec_parser.py                  # AST parse -> TaskGraph; enforces rules 1-6 of Section 2.2
  executor_library.py             # ExecutorLibrary protocol + InMemoryExecutorLibrary
                                  #   + MINIMAL mock catalogue for M1. Real catalogue = M2.
  orchestrator.py                 # one LLM call, positional binding, regeneration, escalation
  type_check.py                   # checks 1-5 of Section 4.4
  prompting.py                    # ExecutorSpec -> ToolSpec projection; feedback message text
  errors.py                       # SpecValidationError, TypeCheckError,
                                  #   ExecutorOnboardingRequired, OrchestrationFailure

/shared/                          # per CLAUDE.md: cross-phase types live here
  llm_client.py                   # revised per Section 5
  types.py                        # nominal type registry
  executor.py                     # ExecutorKind, Port, ParameterSpec, ExecutorSpec
  workflow.py                     # TaskGraph, LogicalWorkflow/Node/Edge, ExecutionPreferences

/tests/
  test_spec_parser.py             # Listing-2 shape parses; loops/ifs/slo-in-body rejected;
                                  #   the run(...) line never reaches the graph
  test_type_check.py              # each check fails for the right reason
  test_orchestrator_happy.py      # fixture mock -> expected Code Gen DAG (4 nodes, 3 forms)
  test_orchestrator_retry.py      # faulty mock -> recovers on attempt 2; feedback asserted
  test_orchestrator_escalation.py # faulty_forever -> OrchestrationFailure after 3 attempts;
                                  #   no_match -> ExecutorOnboardingRequired immediately
  test_request_agnostic.py        # LogicalWorkflow holds no query/payload/SLO/model/hardware
```

Build order: `shared/types.py` -> `shared/executor.py` -> `shared/workflow.py` ->
`shared/llm_client.py` (revision) -> `development/errors.py` -> `development/spec_parser.py` ->
`development/specs/code_generation.py` -> `development/executor_library.py` ->
`development/type_check.py` -> `development/prompting.py` -> `development/orchestrator.py` ->
tests.

---

## 7. Hand-off to later milestones (Table 1, p.572)

| Decision | Frequency | Scope | Milestone |
|---|---|---|---|
| Workflow DAG structure | Once at onboarding | Workflow | **M1** |
| Executor assignment per DAG node | Once at onboarding | Workflow | **M1** (but see 8.2) |
| Final model/tool per executor | Per epoch | (Workflow, SLO) | M4/M5 |
| GPU type and parallelism | Per epoch | (Workflow, SLO) | M4/M5 |
| Workflow-level knobs | Per epoch | (Workflow, SLO) | M4/M5 |
| Per-model instance count `n_m` | Per epoch | Model | M4/M5 |
| Scale-out/in, batching, routing | Continuous / per request | Model / Instance / Request | M6/M7 |

Table 1's Phase-1 note "Per-query for dynamic requests" refers to the Dynamic Coding Pipeline of
Section 2.2 (p.569), where "the execution structure of this pipeline is determined on a
per-request basis". That is a *different* workflow from Figure 1b's static code generation and
is out of M1 scope; noted so it is not mistaken for a missing feature (item A9).

M1's single hand-off artifact is `LogicalWorkflow` (+ optional `ExecutionPreferences`). M3 will
key workflow profiles on it; M4 consumes the result as workflow configurations `c ∈ C_w`.

---

## 8. Contact with Arno's two critiques — now citable against Appendix A.5

Appendix A.5 (p.586-587) verified in full: sets `W, S, M, C_w, G`; parameters
`λ^peak_{w,s}, λ^avg_{w,s}, α, τ_{w,s}, a_c, t_c, θ_m, ℓ^TTFT_m, ℓ^TPOT_m, g_m, e_m, c_g, B_g`;
decision variables `n_m ∈ Z⁺`, `x^peak_{w,s,c,m} ∈ R⁺`, `x^avg_{w,s,c,m} ∈ R⁺`; constraints
(1)-(10); objectives (11)-(13); solved with Gurobi, 300 s limit.

### 8.1 Precedence and makespan (critique b) — confirmed, and sharper than assumed

The objectives are minimize energy `min Σ_m n_m e_m g_m` (11), minimize cost
`min Σ_m n_m g_m c_{g(m)}` (12), and maximize accuracy under a cost budget (13). **There is no
makespan term and no precedence constraint anywhere in (1)-(13).**

Latency enters only as a *filter*, eq (5) and its peak-form (9):

> `x^peak_{w,s,c,m} = 0   if  ℓ^TTFT_m + t_c · ℓ^TPOT_m > τ_{w,s}`

Read that expression carefully, because it corrects what an earlier draft of this document
predicted. It is **one model `m`'s** time-to-first-token plus **that same model's** per-output-
token time multiplied by `t_c`, the token count of the **entire workflow configuration `c`**.
It does not sum over DAG tasks. It does not take a max over branches. There is no critical
path, and there is no per-task latency to aggregate — the formulation never sums over tasks at
all, so the earlier "a precedence-blind optimizer over-counts a parallel branch" framing was
wrong and has been removed. The accurate statement is stronger: **end-to-end latency is modeled
as a single serialized token-generation stream on one model, as though the workflow were one
long generation.** Any workflow structure — parallel branches, tool calls that consume wall-
clock but no tokens, debate rounds that serialize — is invisible to eq (5)/(9).

This bears on M1 directly: the Code Generation DAG has a `Python Interp. (Tool)` node
(Figure 1b) whose execution time is not token generation at all, so it cannot appear in
`ℓ^TTFT_m + t_c · ℓ^TPOT_m` under any value of `t_c`. Tool latency is structurally
unrepresentable in the latency SLO filter.

**M1's decision:** keep the typed edges. Section 3.2 (p.573) states the Logical Workflow's
"edges denote data flow", so a DAG without edges is not the paper's artifact. The infidelity, if
any, lives downstream, so the rule attached is: **M4/M5 must not read `LogicalWorkflow.edges`
for scheduling**, enforced by a documented rule plus a test, because Appendix A.5 does not. If
M4 ever needs precedence to make the MILP feasible, that is itself the finding and goes to
`architecture-decisions.md`.

### 8.2 The MILP has no per-node index — an internal inconsistency in the paper

This is a finding M1 surfaces that was not in the earlier draft.

Every MILP variable is `x_{w,s,c,m}`: workflow, SLO tier, **whole-workflow configuration**, and
**one model `m`**. There is no DAG-node index anywhere in Appendix A.5. Meanwhile Table 1
(p.572) lists "Executor assignment per DAG node" with the note "**Refined per SLO tier by
optimizer**". Those two statements cannot both hold: the optimizer as formulated cannot refine a
per-node assignment, because nodes are not in its index set.

Corroboration from the results tables: Table 6 (p.586, Code Generation) has one `Model` column
per row alongside `Agents`, `Rounds`, `GPU`, `TP`; Table 5 (p.585, Video Q/A) likewise reports a
single `Model` per row (e.g. `Llava-OneVision-7B`) for a workflow whose Figure 1a has several
distinct agents. Note also eq (1): the demand for `(w,s)` may be split across `(c,m)` pairs, but
`t_c` is the *whole configuration's* token count, so each chosen `m` is charged the entire
workflow's tokens — i.e. `m` serves the whole workflow for its share of requests. Per-node model
differentiation is not expressible.

Consequence for M1, stated plainly: the per-node executor assignment this milestone produces is
**collapsed downstream** into a single (configuration, model) choice. M1 should still produce it
— Section 3.2 and Table 1 both require it — but M4 must be built against `x_{w,s,c,m}` as
written, and the collapse logged as a gap rather than papered over by inventing a node index.

### 8.3 Capacity (critique a) — restating the critique against eq (3) honestly

The actual constraint, eq (3):

> `μ_m · Σ_{w,s,c} x^peak_{w,s,c,m} · t_c ≤ n_m · θ_m ,  ∀ m ∈ M`

with `μ_m` the model-specific multiplexing factor, `n_m ∈ Z⁺` the number of instances of model
profile `m`, and `θ_m` its token throughput. So this is request-rate × tokens-per-request ≤
instances × per-instance token throughput.

**Instance counts are present and integral.** The "per-task slot consumption" paraphrase in
`CLAUDE.md` does not fit eq (3) as written, and this document will not pretend otherwise — the
critique needs restating against the real constraint. What eq (3) actually does is aggregate
*all* workflows' token demand on model `m` into one scalar rate inequality against
`n_m · θ_m`, with `θ_m` a constant from the model profile. Consequences worth carrying into M4:

- `t_c` is tokens for the **whole workflow configuration**, not per task. So a `D=3, R=2` debate
  and a single LLM call are distinguished only through `t_c`. **This is an explicit requirement
  on M3:** workflow profiles must produce a token count per configuration that already folds in
  debaters × rounds. Section 3.3 supports this — "Workflow profiles quantify executor-level
  load, including prompt and completion tokens for LLM-based executors" — so the composition
  observation from the earlier draft survives and is now actionable rather than speculative.
- `θ_m`, `ℓ^TTFT_m`, `ℓ^TPOT_m` are per-profile constants, so load-dependent latency is captured
  only by which profile is chosen (Section 3.3: profiles "span load levels"), not by the load
  the MILP actually assigns. Whether that closes the loop is an M4 question; flagged here so it
  is not discovered late.

Nothing in M1 models capacity. What M1 fixes is the node granularity that M3's `t_c` must be
measured over, which is why the Section 2.4 mapping table is worth getting right.

---

## 9. Ambiguities and gaps that remain (post-PDF)

Everything the earlier draft tagged `[UNVERIFIED]` about Listing 2, Figure 1b, the executor
attributes, the three forms, the DAG/request-agnostic requirement, and the type-check-and-
regenerate loop is now **verified and cited**; those tags are gone. What genuinely remains:

| # | Item | Nature |
|---|---|---|
| A1 | The paper gives **no declarative listing for Code Generation** — Listing 2 is Video Q/A only. Section 2.4's spec is constructed by applying Listing 2's format to Figure 1b + Section 2.2 + Appendix A.3/Table 6. | Reconstruction, unavoidable |
| A2 | Whether tester agents are a **separate sub-task** (our choice) or extra debaters inside the LLM Debate composition. Figure 1b draws the debate arc over coders only; Table 6 reports one `Agents` count for the workflow. Both readings fit. | Paper ambiguity — flagged, not silently resolved |
| A3 | Section 2.2 says agents "may employ the same or different LLMs", but the LLM Debate knob set is `{D, R, model}` (Section 3.2) and Table 6 has one `Model` column. Different LLMs per agent is describable in prose and not expressible in the knobs or the MILP. | Real internal tension — logged, not resolved |
| A4 | Table 1's "Executor assignment per DAG node ... Refined per SLO tier by optimizer" vs. Appendix A.5 having no node index in `x_{w,s,c,m}`. | Internal inconsistency (Section 8.2) |
| A5 | No retry bound is given for "Persistent errors". Our `MAX_ORCHESTRATION_ATTEMPTS = 3` is an implementation choice, not reproduction. | Paper silence |
| A6 | No type vocabulary is specified anywhere, though type-checking is mandated. The registry in Section 3.3 is ours. | Paper silence |
| A7 | Developer "execution preferences ... incorporated into the optimization process as constraints" (Section 3.2) — no syntax, and no mapping to A.5 variables, is given. M1 accepts them out-of-band and defers the encoding to M4. | Paper silence |
| A8 | Listing 2 is not executable as printed (a `str` is not callable); the real surface machinery is unspecified. AST parsing (Section 2.2) preserves the printed syntax exactly and sidesteps this. | Paper simplification |
| A9 | Table 1's "Per-query for dynamic requests" DAG structure refers to the Dynamic Coding Pipeline (Section 2.2), a different workflow from Figure 1b. Out of M1 scope by `CLAUDE.md`. | Scope note |
| A10 | Tool execution time is structurally absent from the latency filter eq (5)/(9), which is pure token generation on one model — yet Figure 1b's Code Gen workflow contains a Python interpreter Tool node. | Formulation gap (Section 8.1) |

Items A3, A4, A10, and the Section 8.3 restatement of the capacity critique are candidates for
`architecture-decisions.md`.

---

## 10. Decisions that are the reproduction author's to make

The paper's open questions from the previous draft are resolved and removed. These three are
choices Arno may want to overrule, all of them filling paper silences rather than interpreting
the paper:

1. **`MAX_ORCHESTRATION_ATTEMPTS = 3`** (A5). Any bound is defensible; 3 is proposed.
2. **A2's modeling choice** — testers as a separate sub-task. If Arno prefers the "testers are
   debaters inside the composition" reading, the Code Gen spec drops to 3 sub-tasks and
   `write_tests` disappears. Affects M3's `t_c` accounting, so it is cheaper to settle now.
3. **Whether `ExecutionPreferences` is implemented in M1 or deferred to M4** (A7). Proposed:
   define the dataclass in M1 so the boundary exists, populate and encode it in M4.
