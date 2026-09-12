"""
`C_w` -- enumerating the workflow configuration set, and the [OURS] DAG pruning it forces.

Appendix A.5 (p.586) defines the set in full as:

    "Cw: workflow configurations for w"

That is the ENTIRE definition. It is an opaque index set with `a_c` and `t_c` attached per
element. What varies inside one element comes from Section 3.3.1, Decision 1 (p.574):

    "the workflow-level knob settings (e.g., number of frames, STT on/off, debaters and rounds)
     for each (workflow, SLO)-pair"

The enumeration here is the cross-product of the knob domains AS IMPLEMENTED IN M2/M2b, with one
collapse and one expansion:

COLLAPSE (paper-forced). The nine Code Gen and seven Video Q/A executors that declare a `model`
knob collapse to ONE workflow-level model, because every A.5 decision variable is `x_{w,s,c,m}`
with a single `m` and no executor index. This reproduces a defect rather than simplifying one: it
is precisely why `a_c` can be indexed by configuration alone, and it is the M1 gap "MILP has no
per-executor index".

EXPANSION (ours). `C_video` contains DAG VARIANTS, not just knob tuples. See `prune_stt` below.

TOOL KNOBS ARE EXCLUDED [DESIGN CHOICE]. `cores`, `timeout_s` and `segment_s` cannot reach the
MILP -- A.5 has no CPU resource type at all (M2 A13; `G`, `B_g`, `c_g` and eq. (7) are GPU-only) --
so including them would multiply `|C_w|` by 6*3*3 = 54 with every copy carrying an identical
`a_c` and `t_c`. The literal reading is that a knob setting is part of the configuration, so this
is a place where we chose tractability over literalism. It is recorded, and
`enumerate_cw(include_dead_knobs=True)` exists so that the claim of observational equivalence to
A.5 is testable rather than asserted.
"""

from __future__ import annotations

from itertools import product
from typing import Final, Iterable

from development.executor_lib.knobs import INVENTED_KNOBS
from optimization.profiles.schema import ConfigKey
from shared.model_ids import CODE_GEN_MODELS, VIDEO_QA_MODELS
from shared.types import types_match
from shared.workflow import InputBinding, LogicalEdge, LogicalNode, LogicalWorkflow, TaskRef

# ---------------------------------------------------------------------------------------------
# Live knob domains -- the ones A.5 can actually see
# ---------------------------------------------------------------------------------------------

DEBATERS: Final[tuple[int, ...]] = (2, 4)
"""`D`, from `llm_debate_coders` (Section 3.2, p.572). Domain matches Table 6's `Agents` column
(p.586) and Figure 2c's x-axis (p.570)."""

ROUNDS: Final[tuple[int, ...]] = (2, 4)
"""`R`, from `llm_debate_coders`. Domain matches Table 6's `Rounds` column."""

FRAMES: Final[tuple[int, ...]] = (1, 5, 10)
"""`F`, from `opencv_frame_extractor` (Section 3.2, p.572: "F (number of frames to extract)").
Domain matches Figure 2a's x-axis (p.570) and Table 5's `F` column (p.585)."""

STT_VARIANTS: Final[tuple[str, ...]] = ("stt_on", "stt_off")
"""Section 3.3.1 (p.574) names "STT on/off" as a workflow-level decision and Figure 2a (p.570)
plots both halves. It is NOT a knob: see `prune_stt`."""

DEAD_KNOB_DOMAINS: Final[dict[str, tuple[object, ...]]] = {
    "cores": (1, 2, 4, 8, 16, 32),
    "timeout_s": (5, 30, 120),
    "segment_s": (5, 15, 30),
}
"""Knobs that exist in the Executor Library and can never reach A.5 (6*3*3 = 54 combinations).

`cores` is PAPER-NAMED (Section 3.2, p.572: "the frame extraction tool exposes the knobs: F ...
and cores") and still unreachable, which is the sharper half of gap A13: Section 4.6 (p.578,
Figures 12b/12c) *evaluates* CPU offload and reports it meeting the latency SLO while cutting GPU
usage, yet A.5 has no CPU resource type in which to express it. `timeout_s` and `segment_s` are
ours (`INVENTED_KNOBS`)."""

assert set(DEAD_KNOB_DOMAINS) >= INVENTED_KNOBS, "an invented knob escaped the dead-knob list"


# ---------------------------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------------------------


def _dead_knob_suffixes(include: bool) -> Iterable[tuple[tuple[str, object], ...]]:
    if not include:
        yield ()
        return
    names = sorted(DEAD_KNOB_DOMAINS)
    for combo in product(*(DEAD_KNOB_DOMAINS[n] for n in names)):
        yield tuple(zip(names, combo))


def enumerate_code_generation(include_dead_knobs: bool = False) -> tuple[ConfigKey, ...]:
    """|C_codegen| = |D| * |R| * |models| = 2 * 2 * 5 = 20.

    EXACTLY ONE `(D, R)` PAIR PER CONFIGURATION (A45, resolved). M2 left open whether
    `llm_debate_testers` contributes a second, independent `(D, R)`: [OSDI] Table 6 (p.586) heads
    the column `Agents`, which is ambiguous. [ARXIV] Table 5 (arXiv p.17) is the same table with
    the column headed `Debaters`. The column is `D`. A DAG in which the orchestrator selects
    `llm_debate_testers` is therefore NOT REPRESENTABLE in `C_w` -- a second `(D, R)` pair has
    nowhere to go.

    Paper coverage: Figure 2c (p.570) plots 4 `(D,R)` x 3 models = 12 of these at good precision;
    Figure 4b (p.571) covers all 5 models x 4 `(D,R)` = 20 at coarser precision.
    """
    out: list[ConfigKey] = []
    for dead in _dead_knob_suffixes(include_dead_knobs):
        for d, r, model in product(DEBATERS, ROUNDS, CODE_GEN_MODELS):
            knobs = tuple(sorted((("D", d), ("R", r), ("model", model)) + dead))
            out.append(ConfigKey("code_generation", knobs))
    return tuple(out)


def enumerate_video_qa(include_dead_knobs: bool = False) -> tuple[ConfigKey, ...]:
    """|C_video| = |STT variants| * |F| * |models| = 2 * 3 * 4 = 24.

    The STT dimension is a DAG VARIANT, not a knob (Q6 Option 5 / A50). See `prune_stt`.

    Paper coverage: Figure 2a (p.570) plots 6 `(F, STT)` x 3 models = 18 at good precision;
    Llama-3.2-90B is absent from Figure 2a but present in Figure 4a's legend (as
    `Llama-3.2-90B-Vision`, A48), giving its 6 points at lower precision.
    """
    out: list[ConfigKey] = []
    for dead in _dead_knob_suffixes(include_dead_knobs):
        for variant, f, model in product(STT_VARIANTS, FRAMES, VIDEO_QA_MODELS):
            knobs = tuple(sorted((("F", f), ("model", model)) + dead))
            out.append(ConfigKey("video_qa", knobs, dag_variant=variant))
    return tuple(out)


def enumerate_cw(workflow_id: str, include_dead_knobs: bool = False) -> tuple[ConfigKey, ...]:
    """`C_w` for one workflow."""
    if workflow_id == "code_generation":
        return enumerate_code_generation(include_dead_knobs)
    if workflow_id == "video_qa":
        return enumerate_video_qa(include_dead_knobs)
    raise KeyError(
        f"no configuration space registered for {workflow_id!r}; "
        "Math Q/A and OS-log analysis are deferred (CLAUDE.md)"
    )


EXPECTED_CARDINALITY: Final[dict[str, int]] = {"code_generation": 20, "video_qa": 24}
"""|C| = 44 total. Sanity check against Insight 3 (p.571), which claims configuration complexity
is O(#WorkflowKnobs x #AgentKnobs x #HardwareKnobs): 44 configurations x ~26 model profiles gives
~1,144 `(c, m)` pairs, against Figure 4a/4b's plotted clouds of roughly 100-200 points each. Our
space is an order of magnitude larger than the paper's own plots because A.5 places NO constraint
tying `c` to `m` (M1 gap; `MilpInputs.coherent()` measures the consequence)."""


# ---------------------------------------------------------------------------------------------
# [OURS] DAG pruning -- the M3 OBLIGATION, discharged here
# ---------------------------------------------------------------------------------------------

STT_TASK_ID: Final[str] = "stt"
STT_SOURCE_TASK_ID: Final[str] = "scene_detect"
STT_CONSUMER_TASK_ID: Final[str] = "q_a"


class PruneError(Exception):
    """The pruning precondition or postcondition failed."""


def _assert_still_type_checks(pruned: LogicalWorkflow, library: object) -> None:
    """Re-run the paper's own DAG type-check on the derived graph (Section 3.2, p.573).

    "The orchestrator performs type-checking on the DAG to ensure output types from source nodes
     match input types of destination nodes."

    This is the property that makes Option 5 legal rather than a hack: `q_a`'s variadic `context`
    port declares `accepted_types = {Frames, AnnotatedFrames, Transcript}`, and a variadic port
    accepts a SUBSET of its declared types, so dropping the `Transcript` source leaves a DAG that
    still satisfies the paper's rule. If that were not true, `stt_off` would not be a legal
    configuration and half of `C_video` would be unreachable.
    """
    produced = {n.task_id: n.output_type for n in pruned.nodes}
    for node in pruned.nodes:
        spec = library.get(node.executor)  # type: ignore[attr-defined]
        ports = {p.name: p for p in spec.inputs}
        for binding in node.inputs:
            port = ports.get(binding.port_name)
            if port is None:
                raise PruneError(f"{node.task_id!r}: port {binding.port_name!r} vanished")
            if len(binding.sources) > 1 and not port.variadic:
                raise PruneError(
                    f"{node.task_id!r}: {len(binding.sources)} sources into non-variadic port"
                )
            for src in binding.sources:
                if not isinstance(src, TaskRef):
                    continue
                src_type = produced[src.task_id]
                if not any(types_match(src_type, t) for t in port.accepted_types):
                    raise PruneError(
                        f"{node.task_id!r}: {src.task_id!r} produces {src_type!r}, which port "
                        f"{port.name!r} does not accept ({sorted(port.accepted_types)})"
                    )


def prune_stt(workflow: LogicalWorkflow, library: object | None = None) -> LogicalWorkflow:
    """Derive the `stt_off` Video Q/A DAG from the `stt_on` one. **[OURS] -- NOT REPRODUCTION.**

    Two disclosures are mandatory here, per the M3 OBLIGATION in PROGRESS.md:

    1. THE PAPER DESCRIBES NO PRUNING STEP. Section 3.3.1 (p.574) names "STT on/off" as a
       decision and Figure 2a (p.570) plots both halves of it, but nowhere does the paper
       describe deriving a second DAG from the first, nor any mechanism that could. `stt_enabled`
       cannot be a knob: Section 3.2 (p.572) attaches knobs to "each model or tool", and an
       executor cannot own the knob that deletes it (A18/A24). This function is our invention.

    2. SECTION 3.2 (p.573) SAYS THE ORCHESTRATOR PRODUCES *A* LOGICAL WORKFLOW, SINGULAR --
       "The workflow orchestrator transforms a declarative workflow specification into a logical
       workflow ... represented as a directed acyclic graph (DAG)". Under Option 5, M3 derives a
       SECOND DAG from the orchestrator's one, after the orchestrator has finished and without
       consulting it. The phase boundary of Table 1 (p.572) -- DAG structure "Once at onboarding",
       workflow knobs "Per epoch" -- is crossed by this step. Disclosed, not repaired.

    The postcondition assertion is not decoration: `q_a`'s variadic port accepting a SUBSET of
    its declared types is the property that makes Option 5 legal rather than a hack.
    """
    ids = {n.task_id for n in workflow.nodes}
    if STT_TASK_ID not in ids:
        raise PruneError(f"{workflow.workflow_id}: no {STT_TASK_ID!r} node to prune")

    nodes: list[LogicalNode] = []
    for node in workflow.nodes:
        if node.task_id == STT_TASK_ID:
            continue
        bindings: list[InputBinding] = []
        for binding in node.inputs:
            kept = tuple(
                s
                for s in binding.sources
                if not (isinstance(s, TaskRef) and s.task_id == STT_TASK_ID)
            )
            if not kept:
                raise PruneError(
                    f"{node.task_id!r} argument {binding.arg_index} was fed ONLY by "
                    f"{STT_TASK_ID!r}; pruning would leave it unbound. Option 5 is only "
                    "legal where the consumed port is variadic and retains >=1 source."
                )
            bindings.append(
                binding if kept == binding.sources else InputBinding(
                    arg_index=binding.arg_index,
                    port_name=binding.port_name,
                    port_type=binding.port_type,
                    sources=kept,
                )
            )
        nodes.append(
            LogicalNode(
                task_id=node.task_id,
                task_description=node.task_description,
                executor=node.executor,
                inputs=tuple(bindings),
                output_type=node.output_type,
                open_parameters=node.open_parameters,
            )
        )

    edges = tuple(
        e for e in workflow.edges if e.src_task != STT_TASK_ID and e.dst_task != STT_TASK_ID
    )

    pruned = LogicalWorkflow(
        workflow_id=workflow.workflow_id,
        nodes=tuple(nodes),
        edges=edges,
        inputs=workflow.inputs,
        outputs=workflow.outputs,
    )

    # -- postconditions ------------------------------------------------------------------
    remaining = {n.task_id for n in pruned.nodes}
    if STT_TASK_ID in remaining:
        raise PruneError("stt survived pruning")
    for node in pruned.nodes:
        for binding in node.inputs:
            for src in binding.sources:
                if isinstance(src, TaskRef) and src.task_id == STT_TASK_ID:
                    raise PruneError(f"{node.task_id!r} still references {STT_TASK_ID!r}")
    for edge in pruned.edges:
        if edge.src_task not in remaining or edge.dst_task not in remaining:
            raise PruneError(f"dangling edge {edge.src_task}->{edge.dst_task}")
    if len(pruned.nodes) != len(workflow.nodes) - 1:
        raise PruneError("pruning removed more than the stt node")
    if library is not None:
        _assert_still_type_checks(pruned, library)
    return pruned


def dag_variant_of(config: ConfigKey) -> str:
    """Which DAG a configuration runs on. `default` for workflows with a single DAG."""
    return config.dag_variant


__all__ = [
    "DEAD_KNOB_DOMAINS",
    "DEBATERS",
    "EXPECTED_CARDINALITY",
    "FRAMES",
    "ROUNDS",
    "STT_VARIANTS",
    "PruneError",
    "dag_variant_of",
    "enumerate_code_generation",
    "enumerate_cw",
    "enumerate_video_qa",
    "prune_stt",
]
