"""
The Milestone 1 orchestrator driven over the full Milestone 2 catalogue.

Covers Murakkab (OSDI '26), Section 3.2, "Workflow Orchestrator" and "Logical Workflow" (p.573),
now with a menu large enough for the selection to be wrong: 13 executors, >=3 viable per sub-task.
"""

from __future__ import annotations

import pytest

from development.executor_lib import code_generation_library
from development.orchestrator import WorkflowOrchestrator
from shared.executor import ExecutorKind
from shared.llm_client import MockLLMClient

SPEC_PATH = "development/specs/code_generation.py"

PAPER_ASSIGNMENT = {
    "propose_solutions": "llm_debate_coders",
    "write_tests": "llm_unit_test_writer",
    "execute_tests": "python_interpreter",
    "rank_solutions": "llm_ranker",
}

# Every node served by a DIFFERENT executor than Figure 1b's, all of them type-compatible.
ALTERNATIVE_ASSIGNMENT = {
    "propose_solutions": "llm_self_reflect_coder",
    "write_tests": "llm_debate_testers",
    "execute_tests": "sandboxed_container_runner",
    "rank_solutions": "llm_vote_ensemble_ranker",
}


@pytest.fixture()
def library():
    return code_generation_library()


def _orchestrate(library, fixture):
    llm = MockLLMClient(mode="fixture", fixture=fixture)
    return WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)


def test_paper_assignment_still_type_checks_over_the_larger_catalogue(library):
    result = _orchestrate(library, PAPER_ASSIGNMENT)
    assert {n.task_id: n.executor for n in result.workflow.nodes} == PAPER_ASSIGNMENT
    assert result.attempts == 1


def test_an_entirely_different_assignment_also_produces_a_valid_workflow(library):
    """The alternatives are real: a second, fully distinct executor assignment type-checks."""
    result = _orchestrate(library, ALTERNATIVE_ASSIGNMENT)
    assert {n.task_id: n.executor for n in result.workflow.nodes} == ALTERNATIVE_ASSIGNMENT
    assert result.attempts == 1


def test_the_alternative_workflow_carries_two_independent_debate_knob_pairs(library):
    """DESIGN.md A14, made concrete rather than argued.

    With `llm_debate_testers` selected, one Code Generation workflow declares TWO independent
    (D, R) pairs -- one for the coders, one for the testers -- plus a third `D` on the voting
    ranker. Table 6 (p.586) has exactly ONE `Agents` and ONE `Rounds` column per configuration
    row. Either the paper's testers do not debate (M1's A2) or Table 6 under-reports the
    configuration. Deferred to M3's C_w enumeration; asserted here so it cannot be overlooked.
    """
    workflow = _orchestrate(library, ALTERNATIVE_ASSIGNMENT).workflow
    knobs = {n.task_id: {p.name for p in n.open_parameters} for n in workflow.nodes}
    assert {"D", "R"} <= knobs["write_tests"]
    assert "R" in knobs["propose_solutions"]
    assert "D" in knobs["rank_solutions"]
    debate_pairs = sum(1 for names in knobs.values() if {"D", "R"} <= names)
    assert debate_pairs == 1  # only write_tests; the self-reflect coder has R but no D
    assert sum(1 for names in knobs.values() if "D" in names) == 2


def test_a_signature_sharing_wrong_pick_is_caught_and_recovered(library):
    """`llm_fewshot_coder` and `llm_debate_coders` share a signature, so choosing the wrong ONE is
    not a type error -- but choosing a coder for `write_tests` is (arity 1 vs 2). The regeneration
    loop of Section 3.2 (p.573) must recover."""
    llm = MockLLMClient(
        mode="faulty",
        fixture=PAPER_ASSIGNMENT,
        faults={"write_tests": "llm_fewshot_coder"},
    )
    result = WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert result.attempts == 2
    assert llm.received_feedback[0].errors
    assert {n.task_id: n.executor for n in result.workflow.nodes} == PAPER_ASSIGNMENT


def test_keyword_mock_still_reaches_the_paper_assignment(library):
    """The rule-based mock now scores 13 candidates instead of 5 and still lands on Figure 1b's
    assignment -- but on thinner margins, and its runners-up are exactly the near-duplicates the
    catalogue was designed to introduce (e.g. `llm_debate_testers` is second for
    `propose_solutions`). See the build report; this is a property of the mock's token-overlap
    scoring, not evidence about a real LLM.
    """
    llm = MockLLMClient(mode="keyword")
    result = WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert {n.task_id: n.executor for n in result.workflow.nodes} == PAPER_ASSIGNMENT


def test_a_maximally_tool_heavy_workflow_is_selectable(library):
    """Three of the four stages can be served by TOOLs, which Appendix A.5 prices at exactly zero
    (DESIGN.md Section 6.1). The orchestrator will happily produce that DAG, and nothing in the
    formulation would object -- the only thing preventing a degenerate all-tool optimum is that
    executor assignment is frozen in Phase 1 (Table 1, p.572), not any constraint."""
    tool_heavy = {
        "propose_solutions": "llm_single_shot_coder",  # no Tool can propose solutions
        "write_tests": "property_test_generator",
        "execute_tests": "python_interpreter",
        "rank_solutions": "test_pass_rate_ranker",
    }
    result = _orchestrate(library, tool_heavy)
    kinds = [library.get(n.executor).kind for n in result.workflow.nodes]
    assert kinds.count(ExecutorKind.TOOL) == 3
    # and the three tool stages declare no model knob, so they contribute no token load at all
    for task_id in ("write_tests", "execute_tests", "rank_solutions"):
        node = result.workflow.node(task_id)
        assert "model" not in {p.name for p in node.open_parameters}
