# Milestone 2b — Design: Video Q/A spec + executors (addendum to M2)

**Phase:** Development (paper Section 3.2, Figure 5a)
**Status:** design review pending — no implementation code exists or should exist yet.
**Scope:** the Video Q/A workflow only (Figure 1a p.568, Listing 2 p.572, Section 2.2 p.568,
Appendix A.2 + Table 5 p.585). Math Q/A and OS-log analysis remain deferred by `CLAUDE.md`.

**Source of truth:** Chaudhry, Choukse, Qiu, Goiri, Fonseca, Belay, Bianchini. "Murakkab:
Resource-Efficient Agentic Workflow Orchestration in Cloud Platforms", *OSDI '26*, pp. 567-587.
Citations are by section / listing / figure / table / equation with the USENIX page number.

**Relationship to the approved documents.** This is an *addendum*. `development/DESIGN.md` (M1)
and `development/executor_lib/DESIGN.md` (M2) are approved, implemented and unmodified; every
contract they define — `ExecutorSpec`'s three attributes, positional binding, nominal type-check,
knob factories, the `GROUNDING` scheme, `register_catalogue` — is reused here rather than
restated. Ambiguity numbering continues theirs (M1: A1-A10, M2: A11-A21), so this document starts
at **A22**. Open questions continue at **Q6**.

**Standing policy in force (Arno, 2026-09-10):** reproduce Murakkab literally. Where the paper is
ambiguous, unsound, or incomplete, take the paper's reading and report the problem; do not repair
it. Section 5 (A18) is the sharp case, and it is handled by *naming the hole*, not by inventing a
mechanism and calling it reproduction.

---

## 1. Plain-language overview

### 1.1 Why Video Q/A came back

Code Generation was enough to build M1 and M2, and not enough to *measure* anything. Two concrete
blockers, both recorded in `PROGRESS.md`:

1. **Multiplexing needs two workflows.** Section 4.3 is titled *Multi-Workflow Optimization*, and
   Table 2's headline colocation gain comes from serving `chat`→Video Q/A and `coding`→Code
   Generation on shared model instances (Section 4.1, p.575). With one workflow there is nothing
   to colocate, so M5 could not reproduce the result it exists to reproduce.
2. **Code Generation is a total order.** Its DAG is a chain (`propose → write → execute → rank`),
   so a scheduler that ignores precedence and a scheduler that respects it produce the *same*
   order. The HEFT/precedence gap in `CLAUDE.md`'s critique list is unobservable on it. Video Q/A
   has a genuine parallel branch, and Section 4.6 (p.578) co-schedules exactly that branch.

So this workflow is not "more coverage". It is the instrument that makes two of the project's
three headline critiques measurable at all. Section 6 makes the second one concrete.

### 1.2 What M2b adds, in one breath

A declarative spec file (the paper's own Listing 2, verbatim), five new nominal types, a second
catalogue module with 13 executors, two new knob factories (`F`, and a Video Q/A `model` domain),
and a registration call. Nothing in M1 or M2 is restructured — that was the point of M2's
Section 8, and this document is its first real test.

### 1.3 What M2b does *not* add

No performance numbers (accuracy, latency, TTFT/TPOT, energy, cost, token counts are M3). No
parameter values (Section 3.2, p.572 defers configuration to Section 3.3). No Math Q/A, no OS-log
analysis. No composite cross-workflow DAG — Section 4.6's request fans out across *two* workflows,
which is an M5/M6 concern, not a catalogue concern (Q12).

---

## 2. The declarative specification

### 2.1 Listing 2 is the spec — reproduced character-for-character

Unlike Code Generation, where M1 had to *construct* a spec (its A1), the paper prints the Video
Q/A declarative specification in full. Listing 2 (p.572), caption: "Murakkab's declarative
workflow specification of the video Q/A abstracts away configuration details, letting developers
focus on application logic".

`development/specs/video_qa.py` is to contain exactly this, with no edits:

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

No paraphrase, no added sub-task, no "improvement". Where this conflicts with Figure 1a and
Listing 1 — and it does, in two places — the conflict is reported in Section 8 (A22, A23) and
Listing 2 wins, because Listing 2 is the only *declarative* description the paper gives and this
milestone is about the declarative layer.

### 2.2 It already parses — confirmed, not assumed

M1's AST parser handles this file today. This is not an inference from reading
`development/spec_parser.py`; it is asserted by an **existing passing test**,
`tests/test_spec_parser.py::test_parses_the_papers_own_listing_2`, which embeds Listing 2 verbatim
as `LISTING_2` and asserts:

```python
graph.parameters == ("query", "videos")
graph.task_ids   == ("scene_detect", "frame_extract", "stt", "q_a")
graph.output     == TaskRef("q_a")
graph.node("scene_detect").args == (BoundaryRef("videos"),)
graph.node("q_a").args == (BoundaryRef("query"), (TaskRef("frame_extract"), TaskRef("stt")))
execution.slo == "LOW_LATENCY"
```

So the fan-out (`scenes` feeding two nodes), the fan-in (the list literal into one argument
position), the two-parameter workflow signature, and the execution-section stripping all work
already. M2b needs **zero parser changes**.

**No multi-output support is required, and none should be added.** Listing 1 (p.569, the
*imperative* version the paper shows as the bad example) contains
`scenes, audio = scene_detection(videos)` — a tuple unpack, and the only place in the paper where
a call binds two results. M1's parser rejects that by rule (its Section 2.2, rule 3: body
statements must be `NAME = subtask(args...)`), and `ExecutorSpec.__post_init__` enforces exactly
one output port. Listing 2 does not need it: `stt` takes `scenes`, not `audio`. Implementing
Listing 1's shape would mean reproducing the paradigm the paper is arguing *against*. See A23 for
the consequence this pushes into the STT executor's interface.

### 2.3 The workflow id and the request boundary

`parse_spec_file` derives `workflow_id` from the filename, so `development/specs/video_qa.py`
yields `video_qa`. The request section (`query = "..."`, `videos = [...]`,
`run(..., slo=LOW_LATENCY)`) is recognized and discarded exactly as for Code Generation; the SLO
tier `LOW_LATENCY` never reaches the DAG. Both properties are covered by M1's existing
request-agnosticism suite once the new spec is added to it.

---

## 3. New types

### 3.1 What gets added

`shared/types.py` is a flat frozenset of nominal names with a load-time validator and no
subtyping (M1's Section 3.3), so extension is purely additive. M2b adds five:

| Constant | Name | Justification |
|---|---|---|
| `VIDEOS` | `"Videos"` | the boundary input `videos` (Listing 2 line 6); Listing 1's `videos = ["road_trip.mp4"]` is a list of files |
| `SCENES` | `"Scenes"` | `scene_detect`'s output; Figure 1a's "Scene Detector" edge |
| `FRAMES` | `"Frames"` | `frame_extract`'s output; Figure 1a's "Raw Frames" |
| `ANNOTATED_FRAMES` | `"AnnotatedFrames"` | Figure 1a's "Annotated Frames" out of the Object Detector; needed because object detection has no sub-task of its own under Listing 2 (A22) |
| `TRANSCRIPT` | `"Transcript"` | `stt`'s output; Figure 1a's "Text" from Speech-to-Text |

**Nothing existing changes.** `Query`, `CodeCandidates`, `TestSuite`, `ExecutionResults` and
`Answer` keep their spellings and their membership. `Answer` is *reused* as `q_a`'s output —
Listing 2's `return answer`, Figure 1a's "Answer" node — which is the only deliberate overlap
between the two workflows.

M1 and M2 are `done` and their 100 tests must stay green; adding names to a frozenset cannot break
a nominal-equality check on names that are already there. The one file-level caveat is in 3.2.

### 3.2 `Query` is reused, and its docstring is inaccurate today

Listing 2's first `q_a` argument is named `query`, and Listing 2's boundary parameter is `query`.
Reusing the existing `QUERY` type is the natural reading. But M1 wrote its docstring as *"The
natural-language coding problem entering the workflow"*, which is Code-Gen-specific.

Proposal: reuse `QUERY` and **generalize the docstring only** — a comment change, no rename, no
registry change, no behavioural change. That is the single edit to an existing `shared/` file in
this milestone, and it is worth naming rather than slipping in.

The alternative — a distinct `Question` type — is offered as **Q7**. It buys sharper cross-workflow
separation (a Code Gen ranker could never be wired into a video DAG) at the cost of two nominal
types for one concept, in a type vocabulary the paper does not have at all (M1's A6).

---

## 4. The catalogue

### 4.1 Signatures, from Listing 2

```
scene_detect  :: (Videos)                                        -> Scenes
frame_extract :: (Scenes)                                        -> Frames | AnnotatedFrames
stt           :: (Scenes)                                        -> Transcript
q_a           :: (Query, [Frames | AnnotatedFrames | Transcript]) -> Answer
```

`q_a`'s second port is **variadic** with `accepted_types = {Frames, AnnotatedFrames, Transcript}`,
which is precisely the case M1's Section 4.3 correction was written for: Listing 2's
`q_a(query, [frames, transcript])` mixes two types in one argument position, and it is the paper's
own counter-example to homogeneous variadic ports. Note the consequence that makes Section 5
tractable: a variadic port accepts a *subset*, so a DAG with the `stt` branch removed still
type-checks.

Grounding markers follow M2 exactly — `PAPER` / `PAPER-FORM` / `INVENTED`, recorded in a
`GROUNDING` dict and in banner comments, and kept out of prompt-facing `description` text.

### 4.2 `scene_detect` — (Videos) → Scenes

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `opencv_scene_detector` | TOOL | **[PAPER]** Listing 1 line 3 `fn=SceneDetector()` (p.569); Section 2.3 (p.569) names "SceneDetector in OpenCV"; Section 3.2 (p.572) lists "OpenCV frame extractor" as the canonical Tool | `cores` |
| 2 | `fixed_interval_segmenter` | TOOL | **[INVENTED]** — cuts the video into fixed-length chunks with no content analysis | `cores`, `segment_s` *(invented knob)* |
| 3 | `vlm_scene_detector` | LLM | **[INVENTED]** — a multimodal LLM labels scene boundaries from sampled thumbnails | `model` |

Entry 3 is the same probe as M2's `llm_execution_simulator`: on a sub-task the paper serves with a
Tool, it is the only candidate Appendix A.5 can see at all (Section 7).

### 4.3 `frame_extract` — (Scenes) → Frames | AnnotatedFrames

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `opencv_frame_extractor` | TOOL | **[PAPER]** Section 3.2 (p.572): "the frame extraction tool exposes the knobs: `F` (number of frames to extract) and `cores` (number of CPU cores to run on)"; Listing 1 line 8 `params={"num_frames": 15}, resources={"CPUs": 32}` | `F`, `cores` |
| 2 | `omdet_frame_annotator` | TOOL | **[PAPER-FORM]** OmDet is paper-named (Section 4.1, p.575: "OmDet [89] for object detection model serving"; Section 4.6 Figures 12a-c) and Figure 1a has an Object Detector agent — but Listing 2 has **no object-detection sub-task**, so folding detection into the frame-extraction executor is OURS (A22) | `F`, `cores` |
| 3 | `clip_frame_annotator` | TOOL | **[PAPER]**-named backend: Listing 1 line 13 `object_detection = MLModel(name="CLIP", ..., resources={"CPUs": 128})` (p.569) | `F`, `cores` |
| 4 | `vlm_frame_captioner` | LLM | **[INVENTED]** — a multimodal LLM captions the sampled frames instead of a detector annotating them | `F`, `model` |

Entries 2-4 output `AnnotatedFrames`; entry 1 outputs `Frames`. Both are accepted by `q_a`'s
variadic port, so all four are genuinely selectable — this is the sub-task where executor choice
changes the *type* flowing downstream without breaking the DAG, which is a property Code Generation
never exercised.

### 4.4 `stt` — (Scenes) → Transcript

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `whisper_stt` | TOOL | **[PAPER]** Listing 1 line 10 `MLModel(name="Whisper", ..., resources={"PTUs": 50})`; Section 4.1 (p.575): "speaches-ai (v0.7) as the speech-to-text model serving engine"; Section 4.6 Figures 12a-c co-schedule it | `cores` |
| 2 | `caption_track_extractor` | TOOL | **[INVENTED]** — lifts an existing subtitle/caption track out of the container; no ML at all | `cores` |
| 3 | `vlm_transcriber` | LLM | **[INVENTED]** — an audio-capable multimodal LLM transcribes directly | `model` |

`whisper_stt`'s `cores` knob is not decoration: Section 4.6's Figure 12b runs **Whisper on CPUs**
and reports it "runs efficiently without saturating CPUs, making it a good candidate for
offloading". Section 7 explains why that knob still cannot reach the optimizer.

### 4.5 `q_a` — (Query, [Frames | AnnotatedFrames | Transcript]) → Answer

| # | Name | Kind | Grounding | Knobs |
|---|---|---|---|---|
| 1 | `multimodal_llm_qa` | LLM | **[PAPER]** Figure 1a "Q/A (LLM)" (p.568); Section 2.2 item 5 (p.568): "Multi-modal LLM (or LMM) to answer the user query given the processed frames and audio transcript"; Listing 1 line 16 | `model` |
| 2 | `multimodal_llm_qa_selfreflect` | COMPOSITION | **[PAPER-FORM]** self-reflection is form 2 (Section 3.2, p.572), realized by the paper for Math Q/A (Figure 15, p.585) | `R`, `model` |
| 3 | `multimodal_debate_qa` | COMPOSITION | **[PAPER-FORM]** LLM-Debate is form 2 and is the Code Gen structure (Figure 1b); applying it to video Q/A is ours | `D`, `R`, `model` |

**Deliberately no Tool option on `q_a`.** A tool-servable answer node would make it possible to
build a Video Q/A DAG in which *every* stage is a Tool — a workflow Appendix A.5 prices at exactly
zero across all four objectives. That is a striking demonstration and an executor no engineer
would ship; unlike M2's `llm_execution_simulator`, it is not needed to expose the gap, because
Section 7 already gets three of four stages there. Raised as **Q11**, recommendation: no.

### 4.6 Knobs

Reused from M2's `knobs.py` unchanged: `cores_knob()`, `rounds_knob()`, `debaters_knob()`.
New factories:

| Knob | Domain | Source | Level |
|---|---|---|---|
| `F` | `{1, 5, 10}` | Table 5's `Frames` column (p.585); Figure 2a's x-axis "1,N 1,Y 5,N 5,Y 10,N 10,Y" (p.570); Figure 4a "Size = # of frames" (p.571) | workflow (§3.3.1 p.574) / agent (§2.5 p.570) — the paper says both, A12 |
| `model` (Video Q/A domain) | `Llava-OneVision-7B`, `Gemma-3-27B`, `NVLM-D-72B`, `Llama-3.2-90B` | Table 5 `Model` column (p.585); Figure 2a; Figure 4a's model legend (p.571) | agent |
| `segment_s` | `{5, 15, 30}` | **[INVENTED]**, like M2's `timeout_s` — no counterpart in the paper | tool-local |

`Gemma-3-27B` and `NVLM-D-72B` appear in **both** workflows' model domains and must remain ONE id
in `shared/model_ids.py` (M2 already documents this requirement). Whisper, OmDet and CLIP are
**not** added as model ids: like M2's `python_interpreter`, a Tool *is* its backend and exposes no
`model` knob (see A31 for what that costs).

Two invariant consequences that must be handled in the implementation, not discovered during it:

- **`F` is not `frames`.** Listing 1 hardcodes `num_frames: 15`, a value **outside** the `{1,5,10}`
  domain every measurement in the paper uses (A29). We declare `{1,5,10}` per the literal policy.
- **M2's "one definition per knob" invariant weakens.** `model` now carries a different domain per
  catalogue. M2's `test_declared_knob_domains_do_not_drift_between_executors` iterates the Code Gen
  catalogue only, so it keeps passing, but the *rule* must be restated as "one definition per knob
  **per catalogue**" and the video factory must be a distinct function
  (`video_qa_model_knob()`), never a re-parameterization of `model_knob()` (A27).

### 4.7 Coverage

| Sub-task | Candidates | Kinds |
|---|---|---|
| `scene_detect` | 3 | TOOL ×2, LLM |
| `frame_extract` | 4 | TOOL ×3, LLM |
| `stt` | 3 | TOOL ×2, LLM |
| `q_a` | 3 | LLM, COMPOSITION ×2 |
| **Total** | **13** | TOOL ×7, LLM ×4, COMPOSITION ×2 |

Every sub-task has ≥3 signature-viable candidates spanning ≥2 kinds, matching M2's bar. Combined
with Code Generation, `default_library()` becomes 26 executors — which changes the orchestrator's
job on *both* workflows (Section 9.2).

---

## 5. A18 — the knob that no node can own

### 5.1 The problem, plainly

Section 3.3.1, Decision 1 (p.574) lists the workflow configuration as "the workflow-level knob
settings (*e.g.*, number of frames, **STT on/off**, debaters and rounds)". Figure 2a (p.570) plots
accuracy for six configurations that are exactly `frames × {STT on, STT off}`, and Section 2.5
(p.570) uses "whether to include a Speech-to-Text Transcript agent" as its canonical example of a
workflow-level knob. So STT on/off is unambiguously a knob the paper intends the optimizer to set.

But Section 3.2's "Attributes" (p.572) says knobs belong to executors: "Each **model or tool** in
the library exposes three attributes: … (3) a key-value list of configurable parameters." And
`stt_enabled = False` does not configure the STT executor — it **deletes the node**. An executor
cannot own the knob that decides whether it exists. Worse, the deletion is not local: it removes an
edge into `q_a`, i.e. it changes the DAG that Section 3.2 (p.573) says the orchestrator produced
and type-checked.

**This is a hole in the paper's own model, not in our implementation of it.** Murakkab states a
knob it has nowhere to put. Everything below is about which honest workaround costs least, not
about repairing the paper.

### 5.2 The five options, with costs

**Option 1 — Do not model it.** No `stt_enabled` anywhere; the DAG always contains `stt`.
*Cost:* half of Figure 2a's configuration space disappears; `C_w` for Video Q/A loses a dimension
the paper explicitly names as a decision. M3 could not reproduce Figure 2a. *Request-agnosticism:*
unaffected. *Verdict:* cheapest and least honest — it silently drops a paper-stated decision.

**Option 2 — Knob on the consumer (`q_a` declares `stt_enabled`).**
*Cost:* the `stt` node still exists and still runs; a knob on `q_a` can only mean "ignore the
transcript", so the load it was meant to remove is still incurred. M3's `t_c` would need a special
case that reaches across nodes. Also puts a knob about *another* executor on `q_a`, which the
orchestrator then sees while selecting. *Verdict:* wrong semantics dressed as the right ones.

**Option 3 — Self-deleting knob on `stt` itself (`enabled ∈ {True, False}`).**
*Cost:* one weird knob, no new machinery. The DAG and its edges are unchanged; `enabled=False`
means the executor contributes nothing, and `q_a`'s variadic port simply receives one input instead
of two — which type-checks, since variadic ports accept subsets. *Request-agnosticism:* preserved
(the knob is unvalued in the DAG, valued by M4). *Cost that matters:* the library now contains an
executor whose own knob can annihilate it, and M3 must special-case `t_c` contribution to zero.
*Verdict:* the most literal reading of "executor knob" that actually works, at the price of an
incoherent knob.

**Option 4 — Workflow-level knobs as a new field on `LogicalWorkflow`.**
*Cost:* edits an approved M1 interface (M1 and M2 are `done`, 100 tests), and introduces a concept
Section 3.2's attribute model does not have. It *is* closest to Section 3.3.1's language
("workflow-level knob settings"), and the field would hold unvalued `ParameterSpec`s so
request-agnosticism holds. *Verdict:* defensible, but it invents a mechanism and would look like
reproduction. Barred by the standing policy unless Arno overrules.

**Option 5 — A configuration *is* a DAG variant (recommended).**
Appendix A.5 defines `C_w` only as "workflow configurations for `w`" — the set is opaque, and
`a_c` / `t_c` are per configuration. Nothing in the formulation says a configuration must share a
DAG. So `stt_enabled` is expressed by `C_w` containing both the with-`stt` and without-`stt`
variants, and the MILP handles it natively through `c` with no new mechanism anywhere.
*Cost:* the Executor Library declares **no** `stt_enabled` knob at all — the choice lives in M3's
configuration enumeration, which prunes the `stt` node (valid: the pruned DAG type-checks, per
5.1's variadic-subset property). The invention shrinks to a documented pruning step at M3, and it
is labeled as ours. *Also a cost:* Section 3.2 says the orchestrator produces *a* logical workflow,
singular; under this option M3 derives a second one. That derivation is not in the paper.

### 5.3 Recommendation (Q6)

**Report the hole, then take Option 5.** Concretely:

1. M2b's catalogue declares no `stt_enabled` knob, and `video_qa.py` carries a comment saying why —
   Section 3.2's attribute model cannot express a knob that deletes a node, and we are not
   inventing a field to pretend otherwise.
2. `C_w` for Video Q/A is documented here as `{STT on, STT off} × F × model (× D, R when a
   composition is selected)`, so M3 knows what it must enumerate before it starts profiling.
3. A18 stays open in `PROGRESS.md` as a formulation gap, with this document as the reference.

Fallback if Arno prefers the knob to be visible in the library at M2b: **Option 3**, which is the
only other option that neither drops a paper-stated decision (1, 2) nor edits an approved interface
(4). I am not picking silently — this is Q6 and it is the piece most worth overruling me on.

One thing worth noticing about the evidence: **Table 5 (p.585) reports `Y` in the `STT` column for
every single chosen configuration.** The paper characterizes STT-off in Figure 2a but never shows
the optimizer *selecting* it (A28). Whatever we choose, M3 should not expect an STT-off row to
appear in a reproduction of Table 5.

---

## 6. The parallel branch — what this workflow makes demonstrable

### 6.1 The structure

```
                    ┌──> frame_extract ──┐
videos ─> scene_detect                   ├──> q_a ──> answer
                    └──> stt ────────────┘        ^
query ───────────────────────────────────────────┘
```

`frame_extract(scenes)` and `stt(scenes)` are independent: neither consumes the other's output,
both consume `scenes`, both feed `q_a`. This is the first DAG in the repo with a genuine fan-out /
fan-in, and M1's parser and type-check already produce it (Section 2.2's cited test).

The paper agrees this branch is real and schedules it deliberately. Section 4.6 (p.578), Figure
12a: "OmDet and Whisper running on dedicated A100 GPUs… The two sub-tasks run in **near-perfect
parallel, with full overlap in execution**." Figure 12c: "Both sub-tasks complete nearly
simultaneously, and Whisper's added CPU latency has minimal impact on end-to-end time."

### 6.2 What Appendix A.5 actually says about latency

Latency is **not** in any objective. Objectives (11)-(13) are energy `min Σ_m n_m e_m g_m`, cost
`min Σ_m n_m g_m c_{g(m)}`, and accuracy under a cost budget. There is no makespan term and no
precedence constraint in (1)-(13).

Latency enters once, as a *filter*, eq. (5) with peak-form (9):

> `x^peak_{w,s,c,m} = 0   if   ℓ^TTFT_m + t_c · ℓ^TPOT_m > τ_{w,s}`

Read literally: **one** model `m`'s time-to-first-token, plus **that same model's** per-output-token
time, times `t_c`, the token count of the **entire workflow configuration**. No sum over tasks. No
max over branches. No critical path.

### 6.3 What that mis-predicts on this DAG, concretely

Write the true end-to-end time of one request symbolically (no numbers — those are M3):

```
makespan  =  L_scene  +  max( L_frames(F) + L_detect(F) ,  L_stt )  +  L_qa(F, transcript)
```

A precedence-aware model computes that. Appendix A.5 computes `ℓ^TTFT_m + t_c · ℓ^TPOT_m`. Four
specific failures follow, and every one of them is invisible on Code Generation:

1. **The `max` collapses into a sum-that-isn't-a-sum.** A.5 has no per-task term to combine, so it
   cannot express either `+` or `max`. Two branches that the paper's own Figure 12a says run with
   "full overlap" are represented by a single scalar `t_c` charged to a single model. Overlap earns
   nothing, because there is no makespan to shorten; a serialized execution and a fully overlapped
   one produce **identical** MILP objective values and identical feasibility under filter (5).
2. **Three of the four stages generate no LLM tokens at all.** `scene_detect`, `frame_extract` and
   `stt` are served by OpenCV, OmDet/CLIP and Whisper — Section 4.1 (p.575) names *three different
   serving engines* (vLLM, speaches-ai, OmDet). Their runtime is not token decoding, so no value of
   `t_c` or `ℓ^TPOT_m` represents them. The branch Section 4.6 spends an entire subsection
   co-scheduling contributes approximately zero to the only latency expression the optimizer has.
3. **The knob interaction that Figure 2a plots is unrepresentable.** Raising `F` lengthens the frame
   branch; disabling STT shortens the other. Which one is on the critical path determines whether
   either change affects end-to-end latency at all. A.5 sees both knobs only through their effect on
   the scalar `t_c`, so it cannot distinguish "the budget went to frames" from "the budget went to
   the transcript", and it will predict a latency change for a knob that moved a *non-critical*
   branch.
4. **The SLO filter can certify a configuration that misses its SLO, and reject one that meets it.**
   Under-count: a long non-token branch (Whisper on CPU, Figure 12b) adds real wall-clock that
   eq. (5) cannot see, so `LOW_LATENCY` (Listing 2's own SLO tier) may be certified and violated.
   Over-count: `t_c` folds *all* branches' tokens into one serialized stream on one model, so a
   configuration whose branches genuinely overlap is charged as if they ran back-to-back.

That last pair is the demonstrable form of the HEFT critique, and it needs a workflow with a
branch — which is why Code Generation could not show it (M1's logged gap) and why this milestone
exists.

### 6.4 What M2b must *not* do about it

Nothing. M1's rule stands and is already pinned by
`tests/test_orchestrator_happy.py::test_optimizer_must_not_consume_edges_for_scheduling`: the
Logical Workflow keeps its typed edges, because Section 3.2 (p.573) says "edges denote data flow",
and M4/M5 must not read them for scheduling, because Appendix A.5 does not. M2b adds the DAG on
which that rule finally *bites*; it does not add a scheduler. If M4 turns out to need precedence to
be feasible, that is the finding.

---

## 7. Section 4.6, CPUs, and the A13 finding made concrete

M2 logged A13: `cores` is exposed as an executor knob by Section 3.2 (p.572) while Appendix A.5 has
no CPU resource at all — its set `G` is resource types with GPU budget `B_g` and per-instance cost
`c_g` (A100/H100 VMs, Section 4.1, p.575), `g_m` is a model profile's parallelism, and constraint
(7) bounds GPU usage only. In M2 that knob sat on a Python interpreter the paper barely discusses.
**Here it sits on the exact executors Section 4.6 offloads.**

Section 4.6 (p.578) reports three placements for the same parallel branch: OmDet and Whisper both
on GPUs (Figure 12a, 6×A100 total); both on CPUs (Figure 12b, GPU usage down to 4×A100, "utilizing
idle CPU resources"); and OmDet on GPU with Whisper on CPU (Figure 12c, 5×A100, "meets the latency
SLO while reducing GPU usage").

So the paper's own evaluation *chooses among CPU/GPU placements* and reports the GPU savings as a
result. Consequences for M2b, stated so nobody meets them at M4:

1. **`cores` on `whisper_stt`, `omdet_frame_annotator`, `clip_frame_annotator`,
   `opencv_frame_extractor` and `opencv_scene_detector` is declared, shown to the orchestrator, and
   consumed by nobody.** No constraint, no objective, no filter in (1)-(13) contains a CPU term.
2. **There is no variable for placement.** "Whisper on CPU vs Whisper on GPU" is not a value any
   A.5 decision variable can take: `n_m` counts instances of a *model profile*, and profiles encode
   GPU type and parallelism (Section 3.3.1 Decision 3, p.574). A CPU-hosted executor has no `n_m`.
3. **Therefore Figure 12b/12c's headline result cannot be produced by the optimizer that Appendix
   A.5 describes.** It can be measured, plotted and reported — the paper does — but not *chosen*.
   Combined with the Tool-invisibility finding (M2 Section 6.1) and the precedence gap (Section 6
   above), this is `PROGRESS.md`'s "PATTERN (M1+M2)" entry with a third independent instance:
   Section 4.6 systematically exercises capabilities the formulation cannot express.

We declare `cores` anyway, exactly as M2 did, because Section 3.2 names it as an exposed knob.
Reproduced, not repaired.

---

## 8. Ambiguities, deviations, and inventions (continuing at A22)

| # | Item | Nature |
|---|---|---|
| A22 | **The paper describes this workflow three incompatible ways.** Figure 1a (p.568) and Section 2.2 (p.568) have **five** agents including an Object Detector; Listing 1 (p.569) has five nodes with `scenes, audio = scene_detection(videos)` and `object_detection(frames)`; Listing 2 (p.572) has **four** sub-tasks and no object detection at all. We reproduce Listing 2 verbatim and fold object detection into `frame_extract` executors, which is why `AnnotatedFrames` exists as an output type of that sub-task. | Paper inconsistency — Listing 2 wins, deviation declared |
| A23 | **`stt(scenes)`, not `stt(audio)`.** Listing 1 routes audio out of scene detection into Whisper; Listing 2 feeds `stt` the *scenes*. Reproducing Listing 2 pushes audio de-muxing inside the STT executor, so `whisper_stt`'s input port is `Scenes`. Implementing Listing 1's shape would require multi-output calls, i.e. the imperative paradigm the paper argues against. | Literal-reproduction consequence |
| A24 | **A18 restated and unresolved:** Section 3.3.1 (p.574) names STT on/off as a knob; Section 3.2 (p.572) attaches knobs to executors; an executor cannot own the knob that deletes it. Five options in Section 5; recommendation is to name the hole and express it through `C_w`. | Formulation hole — the paper cannot express its own knob |
| A25 | **What *kind* are Whisper, OmDet and CLIP?** Section 3.2 (p.572) says "Traditional ML models are also included as tools", which makes them `TOOL` — and therefore invisible to A.5 (no `m`, no tokens, no `n_m`). But Section 3.3 (p.573) says model profiles report "latency (TTFT and TPOT **for LLMs**)", implying non-LLM models *do* get profiles, and Section 4.6 provisions GPUs for them. A.5's parameter set (`θ_m`, `ℓ^TTFT_m`, `ℓ^TPOT_m`, `e_m`, `g_m`) is LLM-shaped either way. We declare `TOOL`. | Real internal tension — both readings break |
| A26 | **`D`/`R` domains for a Video Q/A composition have no evidence.** `{2,4}` comes from Table 6, which is Code Generation. Reusing M2's factories imports a domain the paper never measured for this workflow. | Domain inherited across workflows — flagged (Q8) |
| A27 | **`model` now has two domains under one name.** M2's "one definition per knob" invariant must weaken to "per knob **per catalogue**"; the video factory must be a separate function, not a parameterized `model_knob()`. | Invariant change forced by the second catalogue |
| A28 | **Table 5's `STT` column is `Y` in every reported row** (p.585). The paper characterizes STT-off (Figure 2a) but never shows the optimizer choosing it. M3 should not expect an STT-off row when reproducing Table 5. | Evidence gap |
| A29 | **`F`'s domain excludes the paper's own example value.** Table 5 and Figure 2a use `{1,5,10}`; Listing 1 hardcodes `num_frames: 15`. We declare `{1,5,10}`. | Literal-reproduction consequence |
| A30 | **`cores` now sits on the executors Section 4.6 actually offloads** (Whisper, OmDet), and A.5 still has no CPU resource type or placement variable. The paper's own GPU-saving result is unreachable by its own optimizer. | Formulation gap, third instance of the PATTERN |
| A31 | **Tool backend choice is Phase-1, not Phase-2.** Because Tools expose no `model` knob, "Whisper vs another STT engine" is expressed as *executor identity* and is fixed by the orchestrator at onboarding — while Section 3.3.1 Decision 2 (p.574) promises "the chosen model **or tool** for each executor" *per epoch*. The tool half of that promise has no knob to ride on. | Internal inconsistency, new in M2b |
| A32 | **`Query` is reused across two workflows** and its M1 docstring is Code-Gen-specific; a doc-only edit is proposed (Q7). | Housekeeping with a real alternative |
| A33 | **`q_a`'s description is deliberately generic** ("Answer the query given some context", Listing 2 line 5). In a flat 26-executor library this is the description most likely to attract a wrong-workflow candidate; the type-check catches most of it, but not all. | Cross-workflow selection risk (Section 9.2) |

Candidates for `architecture-decisions.md`: **A22, A24 (A18), A25, A30, A31**.

---

## 9. File layout for the M2b implementation

```
/development/
  specs/
    video_qa.py                  # NEW: Listing 2 (p.572) verbatim, character-for-character
  executor_lib/
    DESIGN_VIDEO_QA.md           # this document
    knobs.py                     # EDIT (additive): frames_knob(), video_qa_model_knob(),
                                 #   segment_knob() [INVENTED]; KNOB_LEVELS gains F + segment_s
    video_qa.py                  # NEW: the 13 entries of Section 4 + GROUNDING +
                                 #   register_catalogue("video_qa", ...)
    __init__.py                  # EDIT (additive): import video_qa for its registration side
                                 #   effect; export video_qa_library()
/shared/
  types.py                       # EDIT (additive): Videos, Scenes, Frames, AnnotatedFrames,
                                 #   Transcript; one doc-only fix to QUERY's docstring (3.2)
  model_ids.py                   # EDIT (additive): LLAVA_ONEVISION_7B, LLAMA_3_2_90B,
                                 #   VIDEO_QA_MODELS; ALL_MODEL_IDS becomes a union. Gemma-3-27B
                                 #   and NVLM-D-72B are REUSED, never duplicated
/tests/
  test_video_qa_spec.py          # Listing 2 parses from the spec FILE (not just the embedded
                                 #   string), workflow_id == "video_qa", fan-out/fan-in present,
                                 #   LOW_LATENCY never reaches the DAG
  test_executor_lib_video_qa.py  # contract + coverage, mirroring M2's two files: three attributes,
                                 #   registered port types, no hardware knobs, GROUNDING complete,
                                 #   >=3 viable candidates and >=2 kinds per sub-task, no dead
                                 #   entries
  test_video_qa_parallel.py      # the payoff, pinned: frame_extract and stt have no path between
                                 #   them; both feed q_a; the edges carry the precedence
                                 #   information M4/M5 must not consume (Section 6.4)
  test_cross_workflow_library.py # default_library() == 26 executors; no name collisions; a Code
                                 #   Gen executor never type-checks into a video sub-task and
                                 #   vice versa
```

Build order: `shared/types.py` → `shared/model_ids.py` → `executor_lib/knobs.py` →
`executor_lib/video_qa.py` → `executor_lib/__init__.py` → `development/specs/video_qa.py` → tests.

### 9.1 Exactly one existing assertion breaks — predicted in M2 §8.1

`tests/test_executor_lib_contract.py::test_library_is_flat_and_finite` currently asserts

```python
assert default_library().all() == library.all()   # "today the only registered catalogue is Code Generation"
```

which stops holding the moment `video_qa` registers. The comment above it already says so. It
should become: `code_generation_library()` still returns exactly the 13 Code Gen entries, and
`default_library()` returns the union with no duplicate names. That is a strengthening, not a
loosening. No other M1/M2 test reads `default_library()`, and every orchestrator test is pinned to
`code_generation_library()`, so the remaining 99 should be untouched — to be verified, not assumed,
at implementation time.

### 9.2 The wider menu changes orchestrator behaviour on *both* workflows

M2's Section 8.1 warned about this and it now lands. With 26 executors in one flat library:

- `MockLLMClient`'s `keyword` mode scores every candidate; the Code Gen margins were already thin
  (`write_tests`: 0.541 vs 0.470 for a type-incompatible runner-up). Adding 13 more descriptions
  full of words like "results", "context" and "answer" may re-rank it. Re-pinning keyword-mode
  expectations is expected and legitimate; a *wrong* pick is a finding about the mock's
  length-normalized token overlap, not about a real LLM, and should be reported as such.
- Whether the orchestrator should even see both catalogues is a design question the paper answers
  by implication — Section 3.2 describes one shared library, and executors are meant to be reusable
  across workflows — so a flat union is the faithful choice, and `library_for("video_qa")` remains
  available for tests that want isolation.

---

## 10. Decisions — RESOLVED 2026-09-11

Arno reviewed Q6 directly and took the recommendation; Q7-Q12 were delegated to the
recommendations as written. The design therefore stands as documented. Recorded so they are not
re-opened.

| # | Resolution |
|---|---|
| **Q6 — A18 / `stt_enabled`** | **Option 5: a configuration IS a DAG variant.** `C_w` contains both the with-`stt` and without-`stt` variants; the MILP handles the choice natively through `c`. The Executor Library declares **no** `stt_enabled` knob anywhere. **This puts an obligation on M3:** its `C_w` enumeration must prune the `stt` node, a step the paper never describes — it must be labelled as ours, not as reproduction. Valid because `q_a`'s variadic port accepts subsets, so the pruned DAG still type-checks. Note §3.2 says the orchestrator produces *a* logical workflow, singular; M3 deriving a second is the deviation to disclose. |
| Q7 | Reuse `Query`; fix by documentation, no new `Question` type. |
| Q8 | Inherit `D`/`R` `{2,4}` for the video compositions and flag that they were never measured for Video Q/A (A26). Dropping them would leave `q_a` with a single candidate — the exact M1 defect M2 was built to fix. |
| Q9 | Whisper / OmDet / CLIP are `TOOL`, per §3.2 p.572's explicit sentence — and therefore invisible to A.5 (A25). |
| Q10 | No `backend` knob. The inconsistency with §3.3.1 Decision 2 is the finding (A31); do not paper over it. |
| Q11 | No tool-only `q_a` path. |
| Q12 | Do not model §4.6's cross-workflow composite DAG; that is an M5/M6 concern. |

### Original framing (superseded, kept for traceability)

| # | Question | Recommendation |
|---|---|---|
| **Q6** | **A18 / `stt_enabled`.** Which of Section 5's five options? | **Report the hole; take Option 5** (a configuration is a DAG variant, `C_w` carries STT on/off, the library declares no such knob). Fallback: Option 3. This is the one most worth overruling me on. |
| Q7 | Reuse `Query` for the video question, or add a distinct `Question` type? | Reuse `Query` + a doc-only docstring fix. Two nominal types for one concept, in a vocabulary the paper does not have, buys little. |
| Q8 | `D`/`R` on Video Q/A compositions inherit Code Gen's `{2,4}` (A26). Accept, or drop the two composition alternatives for `q_a`? | Accept and flag. Dropping them would leave `q_a` with one LLM candidate and no real choice — the M1 defect M2 was built to fix. |
| Q9 | Whisper / OmDet / CLIP as `TOOL` (invisible to A.5) or as model profiles with LLM-shaped metrics (A25)? | `TOOL`, per Section 3.2's explicit sentence. Record that this makes Section 4.6's GPU-provisioned Whisper invisible to the MILP. |
| Q10 | Tool backend as executor identity, or add a `backend` knob so the choice is deferred to the optimizer (A31)? | Executor identity. A `backend` knob is not in the paper and would be an invention; the inconsistency with Decision 2 is the finding. |
| Q11 | Add a Tool-only `q_a` path, enabling an entire workflow that A.5 prices at zero? | No. Three of four stages already demonstrate it; a fourth would be gratuitous invention. |
| Q12 | Also model Section 4.6's composite request (Video Q/A ∥ Code Generation under one DAG, p.578)? | No — out of M2b scope. It is a multi-workflow scheduling artifact for M5/M6, not a catalogue entry, and the intra-workflow branch already demonstrates the precedence gap. |
