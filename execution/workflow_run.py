"""
Executing one request end to end -- the first time all three life-cycle phases run together.

Phase 1 (M1/M2) produced a `LogicalWorkflow`: a DAG whose nodes carry executors. Phase 2 (M4/M5)
produced a deployment plan. Phase 3 (M6) looked the plan up and chose a `(configuration, model)`
pair. This module does the last step -- it WALKS the DAG and produces a per-node trace.

THE PROHIBITION, AND EXACTLY WHERE THE LINE IS. Every milestone so far has been forbidden to read
the DAG, because A.5 has no precedence constraint and no makespan term. M7 must read it, because
you cannot run `scene_detect -> {frame_extract || stt} -> q_a` without respecting data flow. The
distinction is not a technicality:

    M7 walks the DAG for DATA-FLOW CORRECTNESS.
    M7 does not schedule by the DAG for RESOURCE ALLOCATION.

The `(c, m)` pair is fixed by the dispatcher BEFORE the walk begins and is not revisited. There is
no earliest-finish-time rule, no critical-path heuristic, no makespan objective, and no node is
ever moved to a different model to go faster. Node order follows the spec's data dependencies and
nothing else. `tests/test_end_to_end.py` enforces all three claims.

SIBLINGS RUN CONCURRENTLY IN SIMULATED TIME [DESIGN CHOICE, Q52 -- overridden]. The design doc
recommended serial execution as "deliberate pessimism". We take concurrent instead, for two
reasons that both point at the paper: Section 4.6 (p.578) MEASURES the overlap -- "The two
sub-tasks run in near-perfect parallel, with full overlap in execution" -- and M3's
`critique/critical_path.py` already computes `L_scene + max(L_frames, L_stt) + L_qa`. Running
siblings serially would contradict the paper's own measurement and disagree with the critique
module this trace feeds. A node starts when its last predecessor finishes; that single rule
produces the `max(...)` for free.

WHAT THIS IS NOT. There is no LLM, no GPU, no sandbox, no Python interpreter. Node outputs are
typed stubs (Q50) and carry no correctness claim -- accuracy remains a profile constant, exactly
as in A.5. The only quantity this module produces that is worth anything is TIMING STRUCTURE:
which nodes exist, in what order, with what overlap, and what each contributes to the span.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from optimization.profiles.schema import ConfigKey, ModelProfileKey
from shared.executor import ExecutorKind
from shared.workflow import LogicalWorkflow

TOOL_DURATION_S: float = 0.0
"""Q44. A.5's own answer, and a more legible finding than an invented number.

Section 3.3 profiles "TTFT and TPOT for LLMs"; a TOOL has no profile, contributes no tokens, and
therefore costs A.5 exactly nothing. A zero-width `execute_tests` node sitting in a trace beside
three LLM nodes states the blind spot more plainly than 0.8 s would. The invented overlay in
`profiles/critique/tool_latency.py` is opt-in and taint-marked (Q16).
"""


@dataclass(frozen=True)
class NodeTrace:
    """One executed DAG node."""

    task_id: str
    executor: str
    kind: ExecutorKind
    start_s: float
    end_s: float
    llm_invocations: int
    tokens: float | None
    model: ModelProfileKey | None
    duration_source: str

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    @property
    def is_free_to_the_formulation(self) -> bool:
        """True when A.5 charges nothing for this node -- every TOOL stage."""
        return self.kind is ExecutorKind.TOOL


@dataclass(frozen=True)
class RequestTrace:
    """One request's journey through one workflow, and what eq. (5) said it would cost."""

    request_id: int
    workflow_id: str
    config: ConfigKey
    model: ModelProfileKey
    nodes: tuple[NodeTrace, ...]
    eq5_s: float | None
    tau_s: float | None
    tool_durations_included: bool

    @property
    def observed_span_s(self) -> float:
        """Wall-clock across the DAG: the max end time. With concurrent siblings this IS the
        critical path -- `L_scene + max(L_frames, L_stt) + L_qa` falls out of the walk."""
        return max((n.end_s for n in self.nodes), default=0.0)

    @property
    def llm_invocations(self) -> int:
        """Total LLM calls. eq. (5) charges ONE prefill however large this is (A96)."""
        return sum(n.llm_invocations for n in self.nodes)

    @property
    def tool_nodes(self) -> tuple[NodeTrace, ...]:
        return tuple(n for n in self.nodes if n.is_free_to_the_formulation)

    @property
    def serial_span_s(self) -> float:
        """What the span would be with no overlap -- the counterfactual Section 4.6 rules out."""
        return sum(n.duration_s for n in self.nodes)

    @property
    def overlap_saving_s(self) -> float:
        """Time saved by the parallel branch. Zero on a total order like Code Generation."""
        return self.serial_span_s - self.observed_span_s


def _predecessors(workflow: LogicalWorkflow) -> Mapping[str, tuple[str, ...]]:
    out: dict[str, list[str]] = {n.task_id: [] for n in workflow.nodes}
    for edge in workflow.edges:
        out.setdefault(edge.dst_task, []).append(edge.src_task)
    return {k: tuple(v) for k, v in out.items()}


def _topological(workflow: LogicalWorkflow) -> list[str]:
    """Data-flow order. Ties broken by DECLARATION order, never by duration.

    Breaking ties by duration would be a scheduling heuristic, which is exactly what the
    prohibition forbids -- so the tie-break is the order the developer wrote the sub-tasks in.
    """
    preds = _predecessors(workflow)
    order = [n.task_id for n in workflow.nodes]
    done: list[str] = []
    remaining = list(order)
    while remaining:
        ready = [t for t in remaining if all(p in done for p in preds[t])]
        if not ready:
            raise ValueError(f"{workflow.workflow_id}: cycle or dangling edge in the DAG")
        pick = min(ready, key=order.index)
        done.append(pick)
        remaining.remove(pick)
    return done


def llm_invocations_for(task_id: str, kind: ExecutorKind, config: ConfigKey) -> int:
    """How many LLM calls a node makes. **A95** -- counted, never timed individually.

    `propose_solutions` is a structured COMPOSITION: `D` debater agents over `R` rounds, so
    `D x R` invocations. M1/M2 model it as one node with knobs rather than an unrolled subgraph,
    which matches Section 2.2's description and A.5's `C_w`, where the whole debate is
    distinguished only by the magnitude of `t_c`.

    We count these and do NOT time them separately (Q45): timing `D x R` sub-calls needs a
    per-call token count, and A59 says no such split is published. Counting is free and exact;
    splitting would be fabrication.
    """
    if kind is ExecutorKind.TOOL:
        return 0
    if kind is ExecutorKind.COMPOSITION:
        knobs = config.knob
        return int(knobs.get("D", 1)) * int(knobs.get("R", 1))
    return 1


def execute(
    workflow: LogicalWorkflow,
    library,
    config: ConfigKey,
    model: ModelProfileKey,
    request_id: int = 1,
    ttft_s: float | None = None,
    tpot_s: float | None = None,
    total_tokens: float | None = None,
    tau_s: float | None = None,
    tool_durations: Mapping[str, float] | None = None,
    start_s: float = 0.0,
) -> RequestTrace:
    """Walk the DAG once and record what happened.

    `tool_durations` defaults to zero per node (Q44). Supplying the invented overlay from
    `profiles/critique/tool_latency.py` is opt-in and taints the result -- callers that do so
    must say so, which `RequestTrace.tool_durations_included` records.

    THE LLM TIME ATTRIBUTION IS THE HONEST PART. `total_tokens` is `t_c`, which is per REQUEST
    and has no published per-node split for Code Generation (A59). So rather than inventing
    thirds, the whole token cost is charged to the node that generates them where that is
    derivable (Video Q/A: one LLM node, so all of it) and DISTRIBUTED BY INVOCATION COUNT where
    it is not (Code Generation: three LLM nodes). The latter is marked `duration_source =
    'apportioned_by_invocation_count [OURS]'` on every node it touches, so no reader can mistake
    it for a profiled split.
    """
    order = _topological(workflow)
    preds = _predecessors(workflow)
    by_id = {n.task_id: n for n in workflow.nodes}
    tools = dict(tool_durations or {})

    kinds = {t: library.get(by_id[t].executor).kind for t in order}
    invocations = {t: llm_invocations_for(t, kinds[t], config) for t in order}
    total_invocations = sum(invocations.values())

    end_times: dict[str, float] = {}
    traces: list[NodeTrace] = []

    for task_id in order:
        node = by_id[task_id]
        kind = kinds[task_id]
        # Concurrent siblings: a node starts when its LAST predecessor finishes.
        begin = max((end_times[p] for p in preds[task_id]), default=start_s)

        if kind is ExecutorKind.TOOL:
            duration = tools.get(task_id, TOOL_DURATION_S)
            source = (
                "INVENTED overlay (profiles/critique/tool_latency.py)"
                if task_id in tools
                else "0.0 -- A.5 charges nothing for a TOOL (Section 3.3 profiles LLMs only)"
            )
            tokens = 0.0
        elif ttft_s is None or tpot_s is None or total_tokens is None:
            duration = 0.0
            source = "eq. (5) unevaluable for this profile (A35/A36: no TTFT reported)"
            tokens = None
        else:
            share = invocations[task_id] / max(1, total_invocations)
            tokens = total_tokens * share
            duration = ttft_s * invocations[task_id] + tokens * tpot_s
            source = (
                "eq. (5) per node; tokens apportioned by invocation count [OURS] (A59: no "
                "published per-node split)"
                if total_invocations > invocations[task_id]
                else "eq. (5); this workflow has ONE LLM node so the split is exact"
            )

        end = begin + duration
        end_times[task_id] = end
        traces.append(
            NodeTrace(
                task_id=task_id,
                executor=node.executor,
                kind=kind,
                start_s=begin,
                end_s=end,
                llm_invocations=invocations[task_id],
                tokens=tokens,
                model=model if kind is not ExecutorKind.TOOL else None,
                duration_source=source,
            )
        )

    eq5 = (
        None
        if (ttft_s is None or tpot_s is None or total_tokens is None)
        else ttft_s + total_tokens * tpot_s
    )
    return RequestTrace(
        request_id=request_id,
        workflow_id=workflow.workflow_id,
        config=config,
        model=model,
        nodes=tuple(traces),
        eq5_s=eq5,
        tau_s=tau_s,
        tool_durations_included=bool(tools),
    )


__all__ = ["NodeTrace", "RequestTrace", "TOOL_DURATION_S", "execute", "llm_invocations_for"]
