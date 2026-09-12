"""
Projection of library executors and parsed tasks into what the orchestrator LLM is shown.

Implements Murakkab (OSDI '26), Section 3.2, "Workflow Orchestrator" (p.573):
  "At the core is an LLM with tool-calling capabilities [71], which receives a list of available
   executors and their interfaces, along with task descriptions, and selects the best executor
   for each sub-task."

and Section 3.2, "Attributes" (p.572):
  "The orchestrator uses these descriptions and interfaces to rank and assign executors (models
   or tools) for workflow tasks, deferring parameter configuration to a later optimization phase
   (Section 3.3)."

That last clause drives one rule here: parameters are shown with their NAMES and DOMAINS but
never their values, and the prompt states that any values the model emits are discarded. The
model needs to know an LLM Debate executor has a `D` knob in order to judge fit; it must not set
`D`. Setting it is the optimizer's decision (Table 1, p.572; Appendix A.5, p.586-587).
"""

from __future__ import annotations

from typing import Sequence

from shared.executor import ExecutorSpec
from shared.llm_client import AssignmentFeedback, TaskDescription, ToolSpec
from shared.workflow import TaskGraph, TaskRef


def to_tool_spec(executor: ExecutorSpec) -> ToolSpec:
    """Project one library entry onto its prompt-facing form (the paper's three attributes).

    Kept separate from `ExecutorSpec` so the library may hold fields (profiling hints, internal
    ids) that never reach the prompt.
    """
    return ToolSpec(
        name=executor.name,
        kind=executor.kind.value,
        description=executor.description,
        interface={
            "inputs": [
                {
                    "position": i,
                    "name": port.name,
                    "accepts": list(port.accepted_types),
                    "variadic": port.variadic,
                }
                for i, port in enumerate(executor.inputs)
            ],
            "output": {"name": executor.output.name, "type": executor.output.type},
        },
        parameters={
            p.name: {"kind": p.kind, "domain": p.domain, "description": p.description}
            for p in executor.parameters
        },
    )


def to_tool_specs(executors: Sequence[ExecutorSpec]) -> tuple[ToolSpec, ...]:
    return tuple(to_tool_spec(e) for e in executors)


def to_task_descriptions(graph: TaskGraph) -> tuple[TaskDescription, ...]:
    """Project the parsed spec onto the task list handed to the LLM.

    Each task carries its natural-language description ("We allow tasks to be expressed in
    natural language", Section 3.2, p.572) plus its position in the data flow, so the model can
    reason about wireability across the whole graph rather than one node at a time.
    """
    descriptions = []
    for task in graph.nodes:
        upstream: list[tuple[str, ...]] = []
        for arg in task.args:
            sources = arg if isinstance(arg, tuple) else (arg,)
            upstream.append(tuple(s.task_id for s in sources if isinstance(s, TaskRef)))
        descriptions.append(
            TaskDescription(
                task_id=task.task_id,
                description=task.description,
                upstream=tuple(upstream),
            )
        )
    return tuple(descriptions)


PARAMETER_NOTICE = (
    "Do not choose parameter values. Parameter configuration is deferred to the optimization "
    "phase; any values you emit will be discarded."
)


def render_prompt(
    workflow_id: str,
    tasks: Sequence[TaskDescription],
    candidates: Sequence[ToolSpec],
    feedback: AssignmentFeedback | None = None,
) -> str:
    """Render the single workflow-level prompt.

    Note the granularity: ONE call carrying ALL task descriptions, per the plural in Section 3.2
    ("along with task descriptions ... for each sub-task"). A real `LLMClient` may ignore this
    text and use native tool-calling instead; it exists so the mock path and a real provider see
    the same information, and so the prompt is inspectable in tests and logs.
    """
    lines: list[str] = [
        f"Workflow: {workflow_id}",
        "",
        "Select the best executor for each sub-task below, choosing only from the executor "
        "library. If no executor in the library suits a sub-task, report it as unmatched rather "
        "than choosing an approximation.",
        PARAMETER_NOTICE,
        "",
        "== Sub-tasks ==",
    ]
    for task in tasks:
        lines.append(f"- {task.task_id}: {task.description}")
        for position, upstream in enumerate(task.upstream):
            origin = ", ".join(upstream) if upstream else "workflow input"
            lines.append(f"    argument {position} <- {origin}")

    lines += ["", "== Executor library (finite and known) =="]
    for candidate in candidates:
        lines.append(f"- {candidate.name} [{candidate.kind}]: {candidate.description}")
        for port in candidate.interface["inputs"]:
            variadic = " (variadic)" if port["variadic"] else ""
            lines.append(
                f"    input {port['position']} {port['name']}: "
                f"{'|'.join(port['accepts'])}{variadic}"
            )
        out = candidate.interface["output"]
        lines.append(f"    output {out['name']}: {out['type']}")
        if candidate.parameters:
            lines.append(f"    knobs (set later by the optimizer): {list(candidate.parameters)}")

    if feedback is not None:
        lines += ["", "== Previous attempt failed type-checking =="]
        lines.append(f"previous assignment: {dict(feedback.previous)}")
        for error in feedback.errors:
            lines.append(f"- {error}")
        if feedback.rejected:
            lines.append(
                "already tried (not necessarily invalid once neighbours change): "
                f"{[list(pair) for pair in feedback.rejected]}"
            )

    return "\n".join(lines)
