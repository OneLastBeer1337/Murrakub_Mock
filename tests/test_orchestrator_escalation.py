"""
The two developer-facing escalation paths.

Covers Murakkab (OSDI '26), Section 3.2:
  * p.572: "If none is found, Murakkab prompts the developer to onboard a suitable one."
  * p.573: "Persistent errors prompt the developer to revise the specification."

Neither path may be replaced by a silent mechanical fallback.
"""

from __future__ import annotations

import pytest

from development.errors import ExecutorOnboardingRequired, OrchestrationFailure
from development.executor_library import code_generation_library
from development.orchestrator import WorkflowOrchestrator
from shared.llm_client import MockLLMClient

SPEC_PATH = "development/specs/code_generation.py"

CORRECT = {
    "propose_solutions": "llm_debate_coders",
    "write_tests": "llm_unit_test_writer",
    "execute_tests": "python_interpreter",
    "rank_solutions": "llm_ranker",
}
FAULT = {"execute_tests": "llm_ranker"}


@pytest.fixture()
def library():
    return code_generation_library()


# -- persistent type errors ---------------------------------------------------------------------


def test_persistent_errors_raise_after_the_retry_bound(library):
    llm = MockLLMClient(mode="faulty_forever", faults=FAULT)
    orchestrator = WorkflowOrchestrator(library, llm)
    with pytest.raises(OrchestrationFailure) as excinfo:
        orchestrator.orchestrate_file(SPEC_PATH)

    failure = excinfo.value
    assert llm.calls == 3  # the documented bound: 1 initial + 2 regenerations
    assert len(failure.attempts) == 3
    assert "revise the specification" in str(failure)


def test_custom_retry_bound_is_honoured(library):
    llm = MockLLMClient(mode="faulty_forever", faults=FAULT)
    with pytest.raises(OrchestrationFailure):
        WorkflowOrchestrator(library, llm, max_attempts=1).orchestrate_file(SPEC_PATH)
    assert llm.calls == 1


def test_failure_report_lists_type_compatible_alternatives(library):
    """The escalation payload tells the developer whether the library lacks a capability or the
    LLM simply kept choosing badly. It is a report, never applied."""
    llm = MockLLMClient(mode="faulty_forever", faults=FAULT)
    with pytest.raises(OrchestrationFailure) as excinfo:
        WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)

    report = excinfo.value.report()
    assert report["workflow"] == "code_generation"
    assert len(report["attempts"]) == 3
    assert report["attempts"][0]["assignments"]["execute_tests"] == "llm_ranker"
    assert report["attempts"][0]["errors"]
    # UPDATED IN MILESTONE 2: `execute_tests` now has three type-compatible candidates rather
    # than the single one M1's stub offered (executor_lib/DESIGN.md Section 4.3). The report must
    # list all of them -- that is precisely what makes it useful to a developer deciding whether
    # the library lacks a capability or the LLM kept choosing badly. Still an exact assertion.
    assert report["viable_executors"]["execute_tests"] == [
        "python_interpreter",
        "sandboxed_container_runner",
        "llm_execution_simulator",
    ]


def test_no_silent_fallback_to_a_type_correct_executor(library):
    """`python_interpreter` would have type-checked, and the orchestrator still refuses."""
    llm = MockLLMClient(mode="faulty_forever", faults=FAULT)
    with pytest.raises(OrchestrationFailure) as excinfo:
        WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert "python_interpreter" in excinfo.value.viable_executors["execute_tests"]
    for attempt in excinfo.value.attempts:
        assert attempt.assignments["execute_tests"] == "llm_ranker"


# -- no suitable executor -----------------------------------------------------------------------


def test_unmatched_subtask_requests_library_onboarding(library):
    llm = MockLLMClient(mode="fixture", fixture=CORRECT, no_match=["write_tests"])
    with pytest.raises(ExecutorOnboardingRequired) as excinfo:
        WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)

    error = excinfo.value
    assert error.tasks == ("write_tests",)
    assert "onboard" in str(error).lower()


def test_onboarding_escalation_does_not_consume_retry_attempts(library):
    """Regenerating cannot conjure a capability the finite library does not contain, so this
    escalation is raised on the first attempt."""
    llm = MockLLMClient(mode="fixture", fixture=CORRECT, no_match=["write_tests"])
    with pytest.raises(ExecutorOnboardingRequired):
        WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert llm.calls == 1


def test_missing_assignment_is_treated_as_unmatched(library):
    """An LLM that simply omits a sub-task must not yield a partial workflow."""
    partial = {k: v for k, v in CORRECT.items() if k != "rank_solutions"}
    llm = MockLLMClient(mode="fixture", fixture=partial)
    with pytest.raises(ExecutorOnboardingRequired) as excinfo:
        WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert "rank_solutions" in excinfo.value.tasks
