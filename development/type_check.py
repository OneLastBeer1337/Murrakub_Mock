"""
Positional port binding and DAG type-checking.

Implements Murakkab (OSDI '26), Section 3.2, "Logical Workflow" (p.573):
  "The orchestrator performs type-checking on the DAG to ensure output types from source nodes
   match input types of destination nodes."

Binding is positional (DESIGN.md Section 4.3): the i-th call argument of a sub-task binds to the
i-th input port of the executor chosen for it, because Listing 2 (p.572) expresses data flow as
positional Python call composition. There is no channel-name matching and no type-driven
inference; the DSL already carries the order.

Checks (DESIGN.md Section 4.4):
  1. edge type equality      -- nominal, no coercion, no adapter insertion
  2. arity                   -- call arity == executor input-port count
  3. variadic consistency    -- list-literal argument requires a variadic port, and each element
                                type must be in that port's accepted set
  4. boundary types          -- a workflow parameter must feed ports of a consistent type
  5. acyclicity              -- guaranteed by the parser, re-asserted by LogicalWorkflow

[DESIGN CHOICE] The type VOCABULARY is ours (shared/types.py); the paper mandates the check but
specifies no types (gap A6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from development.errors import TypeMismatch, UnknownExecutorError
from shared.executor import ExecutorLibrary, ExecutorSpec, Port
from shared.types import types_match
from shared.workflow import (
    Argument,
    BoundaryRef,
    InputBinding,
    LogicalEdge,
    LogicalNode,
    LogicalWorkflow,
    SourceRef,
    TaskGraph,
    TaskRef,
)


@dataclass(frozen=True)
class BindingResult:
    """Either a Logical Workflow, or the mismatches that stopped one being built."""

    workflow: LogicalWorkflow | None
    mismatches: tuple[TypeMismatch, ...]

    @property
    def ok(self) -> bool:
        return self.workflow is not None and not self.mismatches


def bind_and_type_check(
    graph: TaskGraph,
    library: ExecutorLibrary,
    assignments: Mapping[str, str],
) -> BindingResult:
    """Bind the chosen executors to the parsed data flow and type-check the resulting DAG."""
    mismatches: list[TypeMismatch] = []
    nodes: list[LogicalNode] = []
    edges: list[LogicalEdge] = []
    produced_type: dict[str, str] = {}  # task_id -> its executor's output type
    boundary_type: dict[str, str] = {}  # workflow parameter -> inferred type

    for task in graph.nodes:
        executor_name = assignments.get(task.task_id)
        if executor_name is None:
            mismatches.append(
                TypeMismatch(task.task_id, "<unassigned>", "no executor was assigned")
            )
            continue
        try:
            executor = library.get(executor_name)
        except UnknownExecutorError as exc:
            mismatches.append(TypeMismatch(task.task_id, executor_name, str(exc)))
            continue

        node_mismatches, bindings, node_edges = _bind_node_inputs(
            task_id=task.task_id,
            args=task.args,
            executor=executor,
            produced_type=produced_type,
            boundary_type=boundary_type,
        )
        mismatches.extend(node_mismatches)
        edges.extend(node_edges)

        produced_type[task.task_id] = executor.output.type
        nodes.append(
            LogicalNode(
                task_id=task.task_id,
                task_description=task.description,
                executor=executor.name,
                inputs=tuple(bindings),
                output_type=executor.output.type,
                # Section 3.2 (p.572): parameter configuration is deferred to the optimizer.
                open_parameters=executor.parameters,
            )
        )

    if mismatches:
        return BindingResult(workflow=None, mismatches=tuple(mismatches))

    inputs = tuple(
        Port(name=param, type=boundary_type[param])
        for param in graph.parameters
        if param in boundary_type
    )
    # NOTE: a workflow parameter that no sub-task consumes is simply absent from `inputs`. The
    # paper says nothing about unused parameters, so this is not treated as a type error.
    output_type = produced_type[graph.output.task_id]
    outputs = (Port(name="result", type=output_type),)

    workflow = LogicalWorkflow(
        workflow_id=graph.workflow_id,
        nodes=tuple(nodes),
        edges=tuple(edges),
        inputs=inputs,
        outputs=outputs,
    )
    return BindingResult(workflow=workflow, mismatches=())


def _bind_node_inputs(
    task_id: str,
    args: Sequence[Argument],
    executor: ExecutorSpec,
    produced_type: dict[str, str],
    boundary_type: dict[str, str],
) -> tuple[list[TypeMismatch], list[InputBinding], list[LogicalEdge]]:
    mismatches: list[TypeMismatch] = []
    bindings: list[InputBinding] = []
    edges: list[LogicalEdge] = []

    # -- check 2: arity ------------------------------------------------------------------------
    if len(args) != len(executor.inputs):
        mismatches.append(
            TypeMismatch(
                task_id,
                executor.name,
                f"the sub-task is called with {len(args)} input(s) but executor "
                f"{executor.name!r} declares {len(executor.inputs)} input port(s) "
                f"({[p.name for p in executor.inputs]})",
            )
        )
        return mismatches, bindings, edges

    for index, (arg, port) in enumerate(zip(args, executor.inputs)):
        sources: tuple[SourceRef, ...] = arg if isinstance(arg, tuple) else (arg,)

        # -- check 3: variadic consistency ------------------------------------------------------
        if isinstance(arg, tuple) and not port.variadic:
            mismatches.append(
                TypeMismatch(
                    task_id,
                    executor.name,
                    f"argument {index} is a list of {len(arg)} results, but input port "
                    f"{port.name!r} of {executor.name!r} is not variadic",
                )
            )
            continue

        ok = True
        for source in sources:
            source_type = _source_type(source, produced_type, boundary_type, port)
            if source_type is None:
                mismatches.append(
                    TypeMismatch(
                        task_id,
                        executor.name,
                        f"argument {index} references {source} whose type is not yet known",
                    )
                )
                ok = False
                continue

            # -- checks 1 and 4: type equality / boundary consistency ---------------------------
            if not _accepts(port, source_type):
                mismatches.append(
                    TypeMismatch(
                        task_id,
                        executor.name,
                        f"input port {port.name!r} (argument {index}) accepts "
                        f"{list(port.accepted_types)}, but {_describe(source)} produces "
                        f"{source_type!r}",
                    )
                )
                ok = False

        if not ok:
            continue

        bindings.append(
            InputBinding(
                arg_index=index,
                port_name=port.name,
                port_type=port.type,
                sources=sources,
            )
        )
        for source in sources:
            if isinstance(source, TaskRef):
                edges.append(
                    LogicalEdge(
                        src_task=source.task_id,
                        dst_task=task_id,
                        dst_arg_index=index,
                        type=produced_type[source.task_id],
                    )
                )

    return mismatches, bindings, edges


def _source_type(
    source: SourceRef,
    produced_type: dict[str, str],
    boundary_type: dict[str, str],
    port: Port,
) -> str | None:
    """The type flowing out of `source`.

    A workflow parameter has no declared type -- Listing 2's `def workflow(query, videos)` names
    parameters only. Its type is therefore inferred from the first port it feeds, and check 4
    fires if a later port disagrees.
    """
    if isinstance(source, TaskRef):
        return produced_type.get(source.task_id)
    if source.name in boundary_type:
        return boundary_type[source.name]
    boundary_type[source.name] = port.type
    return port.type


def _accepts(port: Port, source_type: str) -> bool:
    return any(types_match(source_type, accepted) for accepted in port.accepted_types)


def _describe(source: SourceRef) -> str:
    if isinstance(source, TaskRef):
        return f"upstream sub-task {source.task_id!r}"
    return f"workflow input {source.name!r}"


def viable_executors(
    graph: TaskGraph,
    library: ExecutorLibrary,
    assignments: Mapping[str, str],
    task_id: str,
) -> tuple[str, ...]:
    """Executors that WOULD type-check for `task_id`, holding all other assignments fixed.

    Used only to build the developer-facing escalation report (Section 3.2, p.573: "Persistent
    errors prompt the developer to revise the specification"). The orchestrator never applies
    this result -- silently substituting a type-correct but semantically wrong executor is the
    failure mode the escalation path exists to prevent.
    """
    viable: list[str] = []
    for candidate in library.all():
        trial = dict(assignments)
        trial[task_id] = candidate.name
        result = bind_and_type_check(graph, library, trial)
        if not any(m.task_id == task_id for m in result.mismatches):
            viable.append(candidate.name)
    return tuple(viable)
