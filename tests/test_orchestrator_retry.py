"""
Regeneration-with-error-feedback loop.

Covers Murakkab (OSDI '26), Section 3.2, "Logical Workflow" (p.573): "In case of mismatches, the
workflow is regenerated with error feedback to the LLM."
"""

from __future__ import annotations

import pytest

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
# `llm_ranker` takes a Query first, so assigning it to `execute_tests` is a type error.
FAULT = {"execute_tests": "llm_ranker"}


@pytest.fixture()
def library():
    return code_generation_library()


@pytest.fixture()
def llm():
    return MockLLMClient(mode="faulty", fixture=CORRECT, faults=FAULT)


@pytest.fixture()
def result(library, llm):
    return WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)


def test_recovers_on_the_second_attempt(result, llm):
    assert result.attempts == 2
    assert llm.calls == 2
    assert {n.task_id: n.executor for n in result.workflow.nodes} == CORRECT


def test_feedback_is_sent_to_the_llm(llm, result):
    assert len(llm.received_feedback) == 1
    feedback = llm.received_feedback[0]
    assert feedback.previous["execute_tests"] == "llm_ranker"
    assert feedback.errors


def test_feedback_names_task_executor_port_and_both_types(llm, result):
    message = next(e for e in llm.received_feedback[0].errors if "execute_tests" in e)
    assert "'execute_tests'" in message  # the task
    assert "'llm_ranker'" in message  # the chosen executor
    assert "'problem'" in message  # the offending port
    assert "['Query']" in message  # what the port accepts
    assert "'CodeCandidates'" in message  # what the upstream produces
    assert "propose_solutions" in message  # the upstream sub-task


def test_rejected_pairs_are_reported_not_hard_banned(llm, result):
    """A pair can become valid once a neighbouring assignment changes, so rejections are
    reported as already-tried rather than forbidden (DESIGN.md Section 4.5).

    This run proves it: the cascading failure also rejects the CORRECT choice
    ('rank_solutions', 'llm_ranker'), which attempt 2 then uses successfully.
    """
    rejected = set(llm.received_feedback[0].rejected)
    assert ("execute_tests", "llm_ranker") in rejected
    assert ("rank_solutions", "llm_ranker") in rejected
    assert result.workflow.node("rank_solutions").executor == "llm_ranker"


def test_second_prompt_carries_the_error_feedback(result):
    assert len(result.prompts) == 2
    assert "Previous attempt failed type-checking" not in result.prompts[0]
    assert "Previous attempt failed type-checking" in result.prompts[1]
    assert "already tried" in result.prompts[1]


def test_no_regeneration_when_the_first_attempt_type_checks(library):
    llm = MockLLMClient(mode="fixture", fixture=CORRECT)
    result = WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert result.attempts == 1
    assert llm.calls == 1
    assert llm.received_feedback == []
