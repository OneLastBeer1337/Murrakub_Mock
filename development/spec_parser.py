"""
Parser for the declarative workflow specification.

Implements Murakkab (OSDI '26), Section 3.2, "Declarative Specification" (p.573) and the format
of Listing 2 (p.572):

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

Section 3.2 (p.573): "Developers can manually decompose tasks into sub-tasks and define data
flow between them... Configuration details (e.g., which LLM to use, number of frames to extract,
resource allocation) are omitted from the specification."

[DESIGN CHOICE -- AST parsing] Listing 2 is not executable as printed: a `str` is not callable,
so `scene_detect(videos)` would raise. The paper never specifies the surface machinery (gap A8).
This module parses the source with `ast` and NEVER executes developer code. Two consequences
that matter:
  * Listing 2's syntax is preserved character-for-character (a tracing implementation would have
    forced `SubTask("...")` on the developer);
  * the `run(..., slo=...)` line is inert by construction, so the request-agnostic requirement
    of Section 3.2 (p.573) is a structural guarantee rather than a promise.
"""

from __future__ import annotations

import ast
from pathlib import Path

from development.errors import SpecValidationError
from shared.workflow import (
    Argument,
    BoundaryRef,
    ExecutionSection,
    SourceRef,
    TaskGraph,
    TaskNode,
    TaskRef,
)

WORKFLOW_FUNCTION_NAME = "workflow"
RUN_FUNCTION_NAME = "run"

_REQUEST_KEYWORDS = frozenset({"slo"})
"""Keywords that must never appear inside `def workflow(...)`: Section 3.2 (p.573) forbids
per-request details in the logical workflow, and the SLO enters at `run(...)`, outside it."""


def parse_spec_file(path: str | Path) -> tuple[TaskGraph, ExecutionSection]:
    """Parse a Listing-2-form specification file."""
    path = Path(path)
    return parse_spec_source(path.read_text(encoding="utf-8"), workflow_id=path.stem)


def parse_spec_source(source: str, workflow_id: str) -> tuple[TaskGraph, ExecutionSection]:
    """Parse Listing-2-form source text into a `TaskGraph` plus the discarded request section.

    The returned `ExecutionSection` is NOT part of the workflow; it is captured only so tests can
    assert that none of its literals reach the `LogicalWorkflow`.
    """
    try:
        module = ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise SpecValidationError(f"specification is not valid Python: {exc}", exc.lineno) from exc

    descriptions: dict[str, str] = {}
    workflow_fn: ast.FunctionDef | None = None
    trailing: list[ast.stmt] = []

    for stmt in module.body:
        if workflow_fn is None:
            if isinstance(stmt, ast.FunctionDef) and stmt.name == WORKFLOW_FUNCTION_NAME:
                workflow_fn = stmt
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue  # module docstring; carries no data flow
            name, text = _read_subtask_declaration(stmt)
            if name is not None:
                if name in descriptions:
                    raise SpecValidationError(f"sub-task {name!r} declared twice", stmt.lineno)
                descriptions[name] = text  # type: ignore[assignment]
                continue
            raise SpecValidationError(
                "before `def workflow(...)`, only sub-task declarations of the form "
                "`name = \"natural language description\"` are allowed",
                stmt.lineno,
            )
        trailing.append(stmt)

    if workflow_fn is None:
        raise SpecValidationError(f"no `def {WORKFLOW_FUNCTION_NAME}(...)` found in specification")
    if not descriptions:
        raise SpecValidationError("specification declares no sub-tasks")

    graph = _parse_workflow_body(workflow_fn, descriptions, workflow_id)
    return graph, _read_execution_section(trailing)


# ---------------------------------------------------------------------------------------------
# Sub-task declarations
# ---------------------------------------------------------------------------------------------


def _read_subtask_declaration(stmt: ast.stmt) -> tuple[str | None, str | None]:
    """Recognize `name = "<string literal>"` (Listing 2, lines 2-5)."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None, None
    target = stmt.targets[0]
    if not isinstance(target, ast.Name):
        return None, None
    value = stmt.value
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return target.id, value.value
    return None, None


# ---------------------------------------------------------------------------------------------
# Workflow body (the data flow)
# ---------------------------------------------------------------------------------------------


def _parse_workflow_body(
    fn: ast.FunctionDef, descriptions: dict[str, str], workflow_id: str
) -> TaskGraph:
    _reject_unsupported_signature(fn)
    parameters = tuple(a.arg for a in fn.args.args)

    nodes: list[TaskNode] = []
    produced: dict[str, str] = {}  # result variable name -> producing task id
    output: TaskRef | None = None

    for stmt in fn.body:
        if output is not None:
            raise SpecValidationError("statements after `return` are not allowed", stmt.lineno)

        if isinstance(stmt, ast.Return):
            output = _parse_return(stmt, produced)
            continue

        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # a docstring is harmless

        if not isinstance(stmt, ast.Assign):
            raise SpecValidationError(
                f"unsupported statement `{type(stmt).__name__}` in the workflow body; only "
                "`result = sub_task(args...)` and a final `return` are allowed. Loops and "
                "conditionals are rejected because Section 3.2 (p.573) requires the logical "
                "workflow to be a directed acyclic graph",
                stmt.lineno,
            )

        node = _parse_call_assignment(stmt, descriptions, parameters, produced)
        if node.result_name in produced or node.result_name in parameters:
            raise SpecValidationError(
                f"name {node.result_name!r} is re-assigned; each result must be a fresh name so "
                "the data flow stays acyclic",
                stmt.lineno,
            )
        produced[node.result_name] = node.task_id
        nodes.append(node)

    if output is None:
        raise SpecValidationError("the workflow must end with `return <result>`", fn.lineno)
    if not nodes:
        raise SpecValidationError("the workflow body contains no sub-task calls", fn.lineno)

    return TaskGraph(
        workflow_id=workflow_id,
        parameters=parameters,
        nodes=tuple(nodes),
        output=output,
    )


def _reject_unsupported_signature(fn: ast.FunctionDef) -> None:
    a = fn.args
    if a.posonlyargs or a.kwonlyargs or a.vararg or a.kwarg or a.defaults or a.kw_defaults:
        raise SpecValidationError(
            "`def workflow(...)` must take plain positional parameters only, as in Listing 2 "
            "(`def workflow(query, videos)`)",
            fn.lineno,
        )
    if not a.args:
        raise SpecValidationError(
            "`def workflow(...)` must declare at least one boundary input parameter", fn.lineno
        )
    for arg in a.args:
        if arg.arg in _REQUEST_KEYWORDS:
            raise SpecValidationError(
                f"parameter {arg.arg!r} is a per-request detail; the SLO enters at "
                "`run(workflow(...), slo=...)`, outside the workflow (Section 3.2, p.573)",
                fn.lineno,
            )


def _parse_return(stmt: ast.Return, produced: dict[str, str]) -> TaskRef:
    if not isinstance(stmt.value, ast.Name):
        raise SpecValidationError(
            "`return` must name a single sub-task result, as in Listing 2 (`return answer`)",
            stmt.lineno,
        )
    if stmt.value.id not in produced:
        raise SpecValidationError(
            f"`return {stmt.value.id}` names something no sub-task produced", stmt.lineno
        )
    return TaskRef(produced[stmt.value.id])


def _parse_call_assignment(
    stmt: ast.Assign,
    descriptions: dict[str, str],
    parameters: tuple[str, ...],
    produced: dict[str, str],
) -> TaskNode:
    if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
        raise SpecValidationError(
            "each statement must bind exactly one result name, as in Listing 2 "
            "(`scenes = scene_detect(videos)`)",
            stmt.lineno,
        )
    result_name = stmt.targets[0].id

    call = stmt.value
    if not isinstance(call, ast.Call):
        raise SpecValidationError(
            "the right-hand side must be a sub-task call; configuration details are omitted from "
            "the specification (Section 3.2, p.573)",
            stmt.lineno,
        )
    if not isinstance(call.func, ast.Name):
        raise SpecValidationError("sub-tasks are called by plain name", stmt.lineno)

    task_id = call.func.id
    if task_id not in descriptions:
        raise SpecValidationError(
            f"{task_id!r} is not a declared sub-task; declare it as "
            f'`{task_id} = "<natural language description>"`',
            stmt.lineno,
        )
    if call.keywords:
        kw = call.keywords[0].arg
        raise SpecValidationError(
            f"keyword argument {kw!r} in a sub-task call: data flow is positional, and "
            "configuration is deferred to the optimizer (Section 3.2, p.572)",
            stmt.lineno,
        )
    if not call.args:
        raise SpecValidationError(f"sub-task {task_id!r} is called with no inputs", stmt.lineno)

    args = tuple(_parse_argument(a, parameters, produced, stmt.lineno) for a in call.args)
    return TaskNode(
        task_id=task_id,
        description=descriptions[task_id],
        result_name=result_name,
        args=args,
        lineno=stmt.lineno,
    )


def _parse_argument(
    node: ast.expr, parameters: tuple[str, ...], produced: dict[str, str], lineno: int
) -> Argument:
    """One argument position: a name, or a list literal of names (Listing 2 line 11)."""
    if isinstance(node, ast.Name):
        return _parse_reference(node, parameters, produced, lineno)
    if isinstance(node, ast.List):
        if not node.elts:
            raise SpecValidationError("empty list argument", lineno)
        refs: list[SourceRef] = []
        for element in node.elts:
            if not isinstance(element, ast.Name):
                raise SpecValidationError(
                    "list arguments may only contain sub-task results or workflow parameters, "
                    "as in Listing 2 (`[frames, transcript]`)",
                    lineno,
                )
            refs.append(_parse_reference(element, parameters, produced, lineno))
        return tuple(refs)
    if isinstance(node, ast.Constant):
        raise SpecValidationError(
            "literal values are not allowed as sub-task arguments: they would bake a per-request "
            "input payload into the workflow (Section 3.2, p.573)",
            lineno,
        )
    raise SpecValidationError(
        f"unsupported argument expression `{type(node).__name__}`; arguments must be names or "
        "list literals of names",
        lineno,
    )


def _parse_reference(
    node: ast.Name, parameters: tuple[str, ...], produced: dict[str, str], lineno: int
) -> SourceRef:
    if node.id in produced:
        return TaskRef(produced[node.id])
    if node.id in parameters:
        return BoundaryRef(node.id)
    raise SpecValidationError(
        f"{node.id!r} is neither a workflow parameter nor the result of an earlier sub-task; "
        "a name must be produced before it is used, which is what keeps the graph acyclic",
        lineno,
    )


# ---------------------------------------------------------------------------------------------
# Execution section -- recognized, then discarded
# ---------------------------------------------------------------------------------------------


def _read_execution_section(statements: list[ast.stmt]) -> ExecutionSection:
    """Collect the request literals and the SLO so tests can assert they never reach the DAG.

    Nothing in the orchestration path consumes the return value of this function.
    """
    literals: list[str] = []
    lines: list[int] = []
    slo: str | None = None

    for stmt in statements:
        lines.append(stmt.lineno)
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                literals.append(sub.value)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if sub.func.id == RUN_FUNCTION_NAME:
                    for kw in sub.keywords:
                        if kw.arg == "slo":
                            slo = ast.unparse(kw.value)

    return ExecutionSection(literals=tuple(literals), slo=slo, lines=tuple(lines))
