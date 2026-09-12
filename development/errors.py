"""
Error types for the development phase.

Implements the failure paths Murakkab (OSDI '26) specifies in Section 3.2:

  * "If none is found, Murakkab prompts the developer to onboard a suitable one." (p.572)
        -> `ExecutorOnboardingRequired`
  * "In case of mismatches, the workflow is regenerated with error feedback to the LLM.
     Persistent errors prompt the developer to revise the specification." (p.573)
        -> `TypeCheckError` feeds the regeneration loop; `OrchestrationFailure` is the
           escalation raised once regeneration is exhausted.

Both escalations surface to the developer. The orchestrator never falls back to a mechanical
type-correct pick, which would defeat them (DESIGN.md Section 4.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


class MurakkabDevelopmentError(Exception):
    """Base class for all development-phase errors."""


class SpecValidationError(MurakkabDevelopmentError):
    """The declarative specification is not a well-formed Listing-2-form workflow.

    Raised by `development/spec_parser.py`, e.g. for a loop or conditional in the workflow body
    (which would break the DAG requirement of Section 3.2, p.573) or for an `slo=` inside the
    workflow definition (which would break request-agnosticism).
    """

    def __init__(self, message: str, lineno: int | None = None) -> None:
        self.lineno = lineno
        super().__init__(f"line {lineno}: {message}" if lineno is not None else message)


class UnknownExecutorError(MurakkabDevelopmentError):
    """The orchestrator LLM named an executor that is not in the finite, known library.

    Section 3.2 (p.572): executors come from "a finite, known set of models and tools in the
    library"; a name outside it is a hallucination, not a selection.
    """


@dataclass(frozen=True)
class TypeMismatch:
    """One violation of Section 3.2's rule that "output types from source nodes match input
    types of destination nodes" (p.573)."""

    task_id: str
    executor: str
    message: str

    def __str__(self) -> str:
        return f"[{self.task_id} -> {self.executor}] {self.message}"


class TypeCheckError(MurakkabDevelopmentError):
    """One or more type mismatches on the DAG. Caught by the orchestrator and turned into error
    feedback for the regeneration attempt; only raised out of `type_check` used standalone."""

    def __init__(self, mismatches: Sequence[TypeMismatch]) -> None:
        self.mismatches = tuple(mismatches)
        super().__init__("; ".join(str(m) for m in self.mismatches))


class ExecutorOnboardingRequired(MurakkabDevelopmentError):
    """No executor in the library covers some sub-task.

    Section 3.2 (p.572): "If none is found, Murakkab prompts the developer to onboard a suitable
    one." Raised immediately, without consuming regeneration attempts: regenerating cannot
    conjure a capability the finite library does not have.
    """

    def __init__(self, tasks: Sequence[str], rationale: Mapping[str, str] | None = None) -> None:
        self.tasks = tuple(tasks)
        self.rationale = dict(rationale or {})
        detail = ", ".join(
            f"{t!r} ({self.rationale.get(t, 'no rationale given')})" for t in self.tasks
        )
        super().__init__(
            "no suitable executor in the library for: "
            f"{detail}. Onboard a suitable model or tool (Section 3.2, p.572)."
        )


@dataclass(frozen=True)
class AttemptRecord:
    """One orchestration attempt, retained for the developer-facing escalation report."""

    attempt: int
    assignments: Mapping[str, str]
    errors: tuple[str, ...]


class OrchestrationFailure(MurakkabDevelopmentError):
    """Type errors persisted across every allowed regeneration attempt.

    Section 3.2 (p.573): "Persistent errors prompt the developer to revise the specification."

    The payload deliberately includes `viable_executors` -- the executors that WOULD have
    type-checked for each failing task, computed mechanically from the library. That tells the
    developer whether the library is missing a capability or the LLM simply kept choosing badly.
    It is a report, not a fallback: the orchestrator does not apply it.
    """

    def __init__(
        self,
        workflow_id: str,
        attempts: Sequence[AttemptRecord],
        viable_executors: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self.workflow_id = workflow_id
        self.attempts = tuple(attempts)
        self.viable_executors: dict[str, tuple[str, ...]] = {
            k: tuple(v) for k, v in (viable_executors or {}).items()
        }
        last = self.attempts[-1] if self.attempts else None
        super().__init__(
            f"workflow {workflow_id!r}: type-checking still failed after {len(self.attempts)} "
            f"attempt(s); revise the specification (Section 3.2, p.573). "
            f"Last errors: {list(last.errors) if last else []}. "
            f"Type-compatible alternatives: {self.viable_executors}"
        )

    def report(self) -> dict[str, Any]:
        """Structured escalation payload for a developer-facing UI or log."""
        return {
            "workflow": self.workflow_id,
            "attempts": [
                {
                    "attempt": a.attempt,
                    "assignments": dict(a.assignments),
                    "errors": list(a.errors),
                }
                for a in self.attempts
            ],
            "viable_executors": {k: list(v) for k, v in self.viable_executors.items()},
        }
