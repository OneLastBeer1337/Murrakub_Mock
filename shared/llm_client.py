"""
Abstract LLM-client interface used by the Workflow Orchestrator.

Implements Murakkab (OSDI '26), Section 3.2, "Workflow Orchestrator" (p.573):
  "At the core is an LLM with tool-calling capabilities [71], which receives a list of available
   executors and their interfaces, along with task descriptions, and selects the best executor
   for each sub-task."

Note the plural -- ALL task descriptions in one interaction. The interface below is therefore
workflow-level (`assign_executors`), not per-task. (The pre-Milestone-1 placeholder in this file
was per-task; DESIGN.md Section 5 revised it against the sentence above.)

Concrete provider is TBD (a Chinese model, per Arno) -- deliberately not referenced here.
Nothing else in the codebase may import a provider SDK directly.

[DESIGN CHOICE] The behaviour of `MockLLMClient` is not derived from the paper; it is the
stand-in that lets Milestone 1 exercise selection, the regeneration loop, and both escalation
paths without a network call. See DESIGN.md Section 5.1.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ToolSpec:
    """One executor as exposed to the orchestrator LLM: the paper's three attributes
    (Section 3.2, "Attributes", p.572).

    This is the prompt-facing PROJECTION of `shared.executor.ExecutorSpec`, kept separate so the
    library can hold fields (profiling hints, internal ids) that never reach the prompt.
    """

    name: str
    kind: str
    description: str  # attribute (1)
    interface: dict[str, Any]  # attribute (2): ordered typed input/output ports
    parameters: dict[str, Any]  # attribute (3): knob names + domains, VALUES NOT REQUESTED


@dataclass(frozen=True)
class TaskDescription:
    """One sub-task as presented to the LLM: its natural-language description plus its place in
    the data flow, so the model can reason about wireability across the whole graph."""

    task_id: str
    description: str
    upstream: tuple[tuple[str, ...], ...] = ()
    """Per argument position, the upstream task ids feeding it (empty tuple = workflow input)."""


@dataclass(frozen=True)
class AssignmentFeedback:
    """Error feedback for a regeneration attempt.

    Section 3.2 (p.573): "In case of mismatches, the workflow is regenerated with error feedback
    to the LLM."
    """

    previous: Mapping[str, str] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    """(task_id, executor) pairs already tried. Reported, not hard-banned: a pair can become
    valid once a neighbouring assignment changes (DESIGN.md Section 4.5)."""


@dataclass(frozen=True)
class ExecutorAssignment:
    """The LLM's answer: one executor per sub-task, plus any sub-task it could not match.

    `unmatched` exists because of Section 3.2 (p.572): "If none is found, Murakkab prompts the
    developer to onboard a suitable one." Without it the model would have to fabricate a choice.
    """

    assignments: Mapping[str, str] = field(default_factory=dict)
    unmatched: tuple[str, ...] = ()
    rationale: Mapping[str, str] = field(default_factory=dict)


class LLMClient(ABC):
    """Abstract tool-calling LLM client."""

    @abstractmethod
    def assign_executors(
        self,
        workflow_id: str,
        tasks: Sequence[TaskDescription],
        candidates: Sequence[ToolSpec],
        feedback: AssignmentFeedback | None = None,
    ) -> ExecutorAssignment:
        """Select the best executor for each sub-task from `candidates`.

        Implementations must NOT return parameter values: Section 3.2 (p.572) defers "parameter
        configuration to a later optimization phase (Section 3.3)".
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------------------------
# Mock implementation [DESIGN CHOICE -- not from the paper]
# ---------------------------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_KIND_CUES: dict[str, tuple[str, ...]] = {
    # verbs/nouns that hint at an executor form (DESIGN.md Section 5.1)
    "tool": ("execute", "run", "interpreter", "report", "results"),
    "composition": ("debate", "debating", "agents", "rounds", "revise", "reflect", "consensus"),
    "llm": ("write", "select", "answer", "summarize", "rank"),
}


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class MockLLMClient(LLMClient):
    """Deterministic stand-in for the orchestrator LLM.

    Modes (DESIGN.md Section 5.1):
      * "fixture"        -- explicit {task_id: executor} map; used for exact DAG assertions.
      * "keyword"        -- token-overlap scoring plus an executor-kind cue; models a plausible
                            but unverified choice.
      * "faulty"         -- returns a deliberately type-incompatible executor on attempt 1 and a
                            correct one afterwards, to exercise the regeneration loop.
      * "faulty_forever" -- never recovers, to exercise the persistent-failure escalation.

    `no_match` additionally forces `unmatched`, to exercise the onboarding escalation.
    """

    def __init__(
        self,
        mode: str = "keyword",
        fixture: Mapping[str, str] | None = None,
        faults: Mapping[str, str] | None = None,
        no_match: Sequence[str] = (),
    ) -> None:
        if mode not in {"fixture", "keyword", "faulty", "faulty_forever"}:
            raise ValueError(f"unknown MockLLMClient mode {mode!r}")
        if mode == "fixture" and not fixture:
            raise ValueError("mode='fixture' requires a fixture mapping")
        if mode in {"faulty", "faulty_forever"} and not faults:
            raise ValueError(f"mode={mode!r} requires a faults mapping {{task_id: executor}}")
        self.mode = mode
        self.fixture = dict(fixture or {})
        self.faults = dict(faults or {})
        self.no_match = tuple(no_match)
        self.calls = 0
        self.received_feedback: list[AssignmentFeedback] = []

    # -- public API ---------------------------------------------------------------------------

    def assign_executors(
        self,
        workflow_id: str,
        tasks: Sequence[TaskDescription],
        candidates: Sequence[ToolSpec],
        feedback: AssignmentFeedback | None = None,
    ) -> ExecutorAssignment:
        self.calls += 1
        if feedback is not None:
            self.received_feedback.append(feedback)

        rejected: set[tuple[str, str]] = set(feedback.rejected) if feedback else set()
        assignments: dict[str, str] = {}
        rationale: dict[str, str] = {}
        unmatched: list[str] = []

        for task in tasks:
            if task.task_id in self.no_match:
                unmatched.append(task.task_id)
                rationale[task.task_id] = "no executor in the library covers this sub-task"
                continue

            forced = self._forced_choice(task.task_id)
            if forced is not None:
                # Assigned verbatim even if the name is not in `candidates`, so tests can inject
                # a hallucinated executor name and watch the type-check reject it.
                assignments[task.task_id] = forced
                rationale[task.task_id] = f"mock mode {self.mode!r} forced this choice"
                continue
            if self.mode == "fixture":
                # A fixture is an EXPLICIT map: a task absent from it is deliberately unmatched,
                # never silently keyword-filled.
                unmatched.append(task.task_id)
                rationale[task.task_id] = "not present in the fixture mapping"
                continue

            choice = self._score_choice(task, candidates, rejected)
            if choice is None:
                unmatched.append(task.task_id)
                rationale[task.task_id] = "no candidate scored above zero"
            else:
                assignments[task.task_id] = choice
                rationale[task.task_id] = "highest keyword-overlap score"

        return ExecutorAssignment(
            assignments=assignments, unmatched=tuple(unmatched), rationale=rationale
        )

    # -- internals ----------------------------------------------------------------------------

    def _forced_choice(self, task_id: str) -> str | None:
        if self.mode == "fixture":
            return self.fixture.get(task_id)
        if self.mode == "faulty_forever":
            return self.faults.get(task_id)
        if self.mode == "faulty" and self.calls == 1:
            return self.faults.get(task_id)
        if self.mode == "faulty" and self.calls > 1:
            return self.fixture.get(task_id)
        return None

    def _score_choice(
        self,
        task: TaskDescription,
        candidates: Sequence[ToolSpec],
        rejected: set[tuple[str, str]],
    ) -> str | None:
        task_tokens = _tokens(task.description)
        best_name: str | None = None
        best_score = 0.0
        for index, candidate in enumerate(candidates):
            if (task.task_id, candidate.name) in rejected:
                continue
            cand_tokens = _tokens(f"{candidate.name} {candidate.description}")
            if not cand_tokens:
                continue
            overlap = len(task_tokens & cand_tokens) / len(cand_tokens)
            cue_hits = sum(1 for cue in _KIND_CUES.get(candidate.kind, ()) if cue in task_tokens)
            score = overlap + 0.15 * cue_hits
            # ties break on library declaration order (stable): strict '>' keeps the earlier one
            if score > best_score:
                best_score, best_name = score, candidate.name
            _ = index
        return best_name
