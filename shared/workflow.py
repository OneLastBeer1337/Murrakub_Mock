"""
Workflow data model: the parsed declarative specification and the Logical Workflow DAG.

Implements Murakkab (OSDI '26):
  * Section 3.2, "Declarative Specification" + Listing 2 (p.572) -> `TaskGraph`
  * Section 3.2, "Logical Workflow" (p.573)                      -> `LogicalWorkflow`

Section 3.2, "Logical Workflow" (p.573), verbatim:
  "This abstract execution plan captures the functional intent of each task without binding to
   specific models, resources, or hardware. It is represented as a directed acyclic graph
   (DAG), where nodes are executors and edges denote data flow. This representation remains
   request-agnostic, containing no per-request details such as query text, input payloads, or
   SLOs. Execution specifics (e.g., model selection or hardware allocation) are deferred to
   later stages."

Both properties of that paragraph are enforced structurally in this module:
  * unconfigured   -> `LogicalNode.open_parameters` holds `ParameterSpec`s, which have no value
                      field at all (see `shared/executor.py`);
  * request-agnostic -> `audit_request_agnostic()` walks the DAG and fails on any field that
                      could hold a query, payload, SLO, model or hardware binding.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Any, Mapping, Union

from shared.executor import ParameterSpec, Port

# ---------------------------------------------------------------------------------------------
# Parsed declarative specification (the output of `development/spec_parser.py`)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BoundaryRef:
    """A reference to a parameter of `def workflow(...)`, i.e. a workflow boundary input.

    Listing 2 (p.572): `def workflow(query, videos)` -- `query` and `videos` are NAMES only.
    Their values appear solely in the execution section (`run(workflow(query, videos), ...)`),
    which never reaches the graph. This is the request-agnostic boundary made syntactic.
    """

    name: str


@dataclass(frozen=True)
class TaskRef:
    """A reference to the result of an earlier sub-task call, e.g. `scenes` in Listing 2."""

    task_id: str


SourceRef = Union[BoundaryRef, TaskRef]
Argument = Union[BoundaryRef, TaskRef, tuple[SourceRef, ...]]
"""One argument position of a sub-task call.

A tuple represents a list literal, e.g. Listing 2 line 11: `q_a(query, [frames, transcript])`.
"""


@dataclass(frozen=True)
class TaskNode:
    """One sub-task invocation in the workflow body.

    `task_id` is the sub-task's variable name (e.g. `scene_detect`); `description` is the
    natural-language string the developer bound to it. Section 3.2, "Workflow Specification"
    (p.572): "We allow tasks to be expressed in natural language..."
    """

    task_id: str
    description: str
    result_name: str
    args: tuple[Argument, ...]
    lineno: int


@dataclass(frozen=True)
class TaskGraph:
    """The declarative specification after parsing: sub-tasks + data flow, no configuration.

    Nodes are in source order, which is also topological order: the DSL requires a name to be
    assigned before it is used, so a call can only reference results that precede it.
    """

    workflow_id: str
    parameters: tuple[str, ...]
    nodes: tuple[TaskNode, ...]
    output: TaskRef

    def node(self, task_id: str) -> TaskNode:
        for n in self.nodes:
            if n.task_id == task_id:
                return n
        raise KeyError(task_id)

    @property
    def task_ids(self) -> tuple[str, ...]:
        return tuple(n.task_id for n in self.nodes)


@dataclass(frozen=True)
class ExecutionSection:
    """The discarded "== Execution with example request ==" part of the spec.

    Listing 2 (p.572), lines 13-15:
        query  = "What is the name of the person wearing the red dress?"
        videos = ["road_trip.mp4"]
        result = run(workflow(query, videos), slo=LOW_LATENCY)

    This is the REQUEST, not the workflow. It is captured here purely so that tests can assert
    that none of these literals reach the `LogicalWorkflow` (Section 3.2, p.573: "no per-request
    details such as query text, input payloads, or SLOs"). Nothing in the orchestration path
    reads this object.
    """

    literals: tuple[str, ...] = ()
    slo: str | None = None
    lines: tuple[int, ...] = ()


# ---------------------------------------------------------------------------------------------
# Logical Workflow (Section 3.2, p.573)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class InputBinding:
    """One argument position bound to an executor input port.

    Binding is positional: the i-th call argument binds to the i-th input port, because
    Listing 2 expresses data flow as positional Python call composition
    (DESIGN.md Section 4.3).
    """

    arg_index: int
    port_name: str
    port_type: str
    sources: tuple[SourceRef, ...]
    """One source normally; several when the argument was a list literal into a variadic port."""


@dataclass(frozen=True)
class LogicalNode:
    """A DAG node: "nodes are executors" (Section 3.2, p.573).

    Carries WHICH executor, never which model/hardware -- that is Section 3.3's decision
    (Table 1, p.572: "Final model/tool per executor ... Per epoch").
    """

    task_id: str
    task_description: str
    executor: str
    inputs: tuple[InputBinding, ...]
    output_type: str
    open_parameters: tuple[ParameterSpec, ...]
    """UNBOUND knobs, e.g. LLM Debate's D/R/model (Section 3.2, p.572). Valued by the optimizer."""


@dataclass(frozen=True)
class LogicalEdge:
    """A DAG edge: "edges denote data flow" (Section 3.2, p.573).

    NOTE (DESIGN.md Section 8.1): these edges carry precedence information that Murakkab's own
    optimizer cannot use -- Appendix A.5 (p.586-587) has no precedence constraint and no
    makespan term, and its latency filter eqs (5)/(9) never sums over tasks. The edges are kept
    because the paper defines the Logical Workflow as a DAG whose edges denote data flow.
    RULE FOR MILESTONES 4/5: the optimizer must NOT read these edges for scheduling.
    """

    src_task: str
    dst_task: str
    dst_arg_index: int
    type: str


@dataclass(frozen=True)
class LogicalWorkflow:
    """The output of the development phase (Figure 5a, p.572) and the sole hand-off to
    `/optimization/`."""

    workflow_id: str
    nodes: tuple[LogicalNode, ...]
    edges: tuple[LogicalEdge, ...]
    inputs: tuple[Port, ...]
    """Boundary parameters: names and types only, never values."""
    outputs: tuple[Port, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for node in self.nodes:
            for binding in node.inputs:
                for src in binding.sources:
                    if isinstance(src, TaskRef) and src.task_id not in seen:
                        raise ValueError(
                            f"node {node.task_id!r} references {src.task_id!r} before it is "
                            "produced; nodes must be topologically ordered"
                        )
            seen.add(node.task_id)
        violations = audit_request_agnostic(self)
        if violations:
            raise ValueError(
                "LogicalWorkflow violates the request-agnostic requirement "
                f"(Section 3.2, p.573): {violations}"
            )

    def node(self, task_id: str) -> LogicalNode:
        for n in self.nodes:
            if n.task_id == task_id:
                return n
        raise KeyError(task_id)

    def to_dict(self) -> dict[str, Any]:
        """Serializable form. Section 3.2 (p.573): "A feedback loop allows developers to inspect
        and refine the generated specification"; this is the inspect half."""
        return dataclasses.asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), default=str, **kwargs)


# ---------------------------------------------------------------------------------------------
# Request-agnostic audit
# ---------------------------------------------------------------------------------------------

FORBIDDEN_FIELD_NAMES: frozenset[str] = frozenset(
    {
        # per-request details, named by Section 3.2 (p.573)
        "query",
        "query_text",
        "payload",
        "input_payload",
        "inputs_payload",
        "slo",
        "slo_tier",
        "deadline",
        # execution specifics, "deferred to later stages" (Section 3.2, p.573)
        "model",
        "model_name",
        "hardware",
        "gpu",
        "gpu_type",
        "accelerator",
        "instances",
        "tensor_parallelism",
        "batch_size",
    }
)

_DAG_TYPES = (LogicalWorkflow, LogicalNode, LogicalEdge, InputBinding, Port, ParameterSpec)


def audit_request_agnostic(
    workflow: LogicalWorkflow, forbidden_literals: tuple[str, ...] = ()
) -> tuple[str, ...]:
    """Return a tuple of violations of Section 3.2's request-agnostic rule (p.573).

    Two checks:
      1. Structural -- no dataclass in the DAG may declare a field that could hold a query,
         payload, SLO, model or hardware binding, and no `ParameterSpec` may carry a value.
      2. Literal -- no string anywhere in the DAG may contain any of `forbidden_literals`
         (used by tests with the discarded execution-section literals).
    """
    violations: list[str] = []

    for dag_type in _DAG_TYPES:
        for f in dataclasses.fields(dag_type):
            if f.name in FORBIDDEN_FIELD_NAMES:
                violations.append(f"{dag_type.__name__}.{f.name} is a forbidden field")
    if any(f.name == "value" for f in dataclasses.fields(ParameterSpec)):
        violations.append(
            "ParameterSpec.value exists; parameters must stay unbound in the development phase"
        )

    if forbidden_literals:
        blob = workflow.to_json()
        for literal in forbidden_literals:
            if literal and literal in blob:
                violations.append(f"request literal {literal!r} leaked into the LogicalWorkflow")

    return tuple(violations)


def open_parameter_map(workflow: LogicalWorkflow) -> Mapping[str, tuple[str, ...]]:
    """task_id -> names of the knobs the optimizer still has to set (Section 3.3)."""
    return {n.task_id: tuple(p.name for p in n.open_parameters) for n in workflow.nodes}
