"""
Workflow Orchestrator: declarative specification -> Logical Workflow.

Implements Murakkab (OSDI '26), Section 3.2, "Workflow Orchestrator" (p.573), verbatim:
  "The workflow orchestrator transforms a declarative workflow specification into a logical
   workflow. It interprets the specification, parses tasks and sub-tasks, and maps each to an
   appropriate executor from Murakkab's library. At the core is an LLM with tool-calling
   capabilities [71], which receives a list of available executors and their interfaces, along
   with task descriptions, and selects the best executor for each sub-task."

and Section 3.2, "Logical Workflow" (p.573), verbatim:
  "The orchestrator performs type-checking on the DAG to ensure output types from source nodes
   match input types of destination nodes. In case of mismatches, the workflow is regenerated
   with error feedback to the LLM. Persistent errors prompt the developer to revise the
   specification."

Corresponds to Table 1 (p.572), Phase 1 "Workflow Development (Orchestrator)": the two decisions
"Workflow DAG structure" and "Executor assignment per DAG node", both "Once at onboarding" with
scope "Workflow". The DAG structure comes from the AST parse; the executor assignment comes from
the LLM.

Pipeline:
    spec (Listing-2 form)
      -> AST parse            -> TaskGraph                     [development/spec_parser.py]
      -> ONE LLM call         -> executor assignment           [shared/llm_client.py]
      -> positional binding + DAG type-check                   [development/type_check.py]
      -> ok?  yes -> LogicalWorkflow -> /optimization/
              no  -> regenerate with error feedback (bounded)
                     -> exhausted -> OrchestrationFailure (escalate to the developer)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from development.errors import (
    AttemptRecord,
    ExecutorOnboardingRequired,
    OrchestrationFailure,
    TypeMismatch,
)
from development.prompting import render_prompt, to_task_descriptions, to_tool_specs
from development.spec_parser import parse_spec_file, parse_spec_source
from development.type_check import bind_and_type_check, viable_executors
from shared.executor import ExecutionPreferences, ExecutorLibrary
from shared.llm_client import AssignmentFeedback, LLMClient
from shared.workflow import LogicalWorkflow, TaskGraph

MAX_ORCHESTRATION_ATTEMPTS = 3
"""[DESIGN CHOICE] 1 initial attempt + at most 2 regenerations.

The paper specifies the BEHAVIOUR -- regenerate with error feedback, and on "persistent errors"
prompt the developer -- but never quantifies "persistent" (DESIGN.md gap A5). A bound must exist
for the loop to terminate; the value 3 is an implementation decision, not a reproduced constant.
"""


@dataclass(frozen=True)
class OrchestrationResult:
    """What the development phase hands to `/optimization/`."""

    workflow: LogicalWorkflow
    attempts: int
    prompts: tuple[str, ...]
    preferences: ExecutionPreferences
    """Travels BESIDE the DAG, never inside it (Section 3.2, p.573; DESIGN.md Section 2.3)."""


class WorkflowOrchestrator:
    """Maps a declarative specification onto executors from the finite, known library."""

    def __init__(
        self,
        library: ExecutorLibrary,
        llm: LLMClient,
        max_attempts: int = MAX_ORCHESTRATION_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.library = library
        self.llm = llm
        self.max_attempts = max_attempts

    # -- entry points ---------------------------------------------------------------------------

    def orchestrate_file(
        self, path: str | Path, preferences: ExecutionPreferences | None = None
    ) -> OrchestrationResult:
        graph, _execution_section = parse_spec_file(path)
        return self.orchestrate(graph, preferences)

    def orchestrate_source(
        self,
        source: str,
        workflow_id: str,
        preferences: ExecutionPreferences | None = None,
    ) -> OrchestrationResult:
        graph, _execution_section = parse_spec_source(source, workflow_id)
        return self.orchestrate(graph, preferences)

    def orchestrate(
        self, graph: TaskGraph, preferences: ExecutionPreferences | None = None
    ) -> OrchestrationResult:
        """Run selection, binding, type-checking and (if needed) bounded regeneration."""
        tasks = to_task_descriptions(graph)
        candidates = to_tool_specs(self.library.all())

        feedback: AssignmentFeedback | None = None
        rejected: list[tuple[str, str]] = []
        attempts: list[AttemptRecord] = []
        prompts: list[str] = []
        last_assignments: Mapping[str, str] = {}

        for attempt in range(1, self.max_attempts + 1):
            prompts.append(render_prompt(graph.workflow_id, tasks, candidates, feedback))
            assignment = self.llm.assign_executors(
                workflow_id=graph.workflow_id,
                tasks=tasks,
                candidates=candidates,
                feedback=feedback,
            )

            # Escalation 1 -- Section 3.2 (p.572): "If none is found, Murakkab prompts the
            # developer to onboard a suitable one." Raised immediately: regenerating cannot
            # conjure a capability that the finite library does not contain.
            missing = tuple(assignment.unmatched) + tuple(
                t.task_id for t in tasks if t.task_id not in assignment.assignments
            )
            if missing:
                raise ExecutorOnboardingRequired(
                    tasks=tuple(dict.fromkeys(missing)), rationale=assignment.rationale
                )

            last_assignments = dict(assignment.assignments)
            result = bind_and_type_check(graph, self.library, last_assignments)
            attempts.append(
                AttemptRecord(
                    attempt=attempt,
                    assignments=dict(last_assignments),
                    errors=tuple(str(m) for m in result.mismatches),
                )
            )

            if result.ok:
                assert result.workflow is not None
                return OrchestrationResult(
                    workflow=result.workflow,
                    attempts=attempt,
                    prompts=tuple(prompts),
                    preferences=preferences or ExecutionPreferences(),
                )

            # Section 3.2 (p.573): "the workflow is regenerated with error feedback to the LLM."
            rejected.extend(
                (m.task_id, last_assignments.get(m.task_id, m.executor))
                for m in result.mismatches
                if m.task_id in last_assignments
            )
            feedback = AssignmentFeedback(
                previous=dict(last_assignments),
                errors=tuple(_feedback_message(m) for m in result.mismatches),
                rejected=tuple(dict.fromkeys(rejected)),
            )

        # Escalation 2 -- Section 3.2 (p.573): "Persistent errors prompt the developer to revise
        # the specification." No mechanical fallback: substituting a type-correct but
        # semantically wrong executor is exactly what this path exists to prevent.
        raise OrchestrationFailure(
            workflow_id=graph.workflow_id,
            attempts=tuple(attempts),
            viable_executors={
                task_id: viable_executors(graph, self.library, last_assignments, task_id)
                for task_id in _failing_tasks(attempts)
            },
        )


def _failing_tasks(attempts: list[AttemptRecord]) -> tuple[str, ...]:
    if not attempts:
        return ()
    last = attempts[-1]
    failing = [
        task_id
        for task_id in last.assignments
        if any(error.startswith(f"[{task_id} ") for error in last.errors)
    ]
    return tuple(dict.fromkeys(failing))


def _feedback_message(mismatch: TypeMismatch) -> str:
    """Structured, specific error feedback naming the task, executor, port and both types."""
    return (
        f"Sub-task {mismatch.task_id!r} was assigned executor {mismatch.executor!r}: "
        f"{mismatch.message}. Choose an executor whose interface matches the data flow."
    )


__all__ = [
    "MAX_ORCHESTRATION_ATTEMPTS",
    "OrchestrationResult",
    "WorkflowOrchestrator",
]
