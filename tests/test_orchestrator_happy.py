"""
Happy-path orchestration: declarative spec -> Logical Workflow.

Covers Murakkab (OSDI '26), Section 3.2, "Workflow Orchestrator" and "Logical Workflow" (p.573),
and Table 1 (p.572), Phase 1: "Workflow DAG structure" and "Executor assignment per DAG node".
"""

from __future__ import annotations

import pytest

from development.executor_library import code_generation_library
from development.orchestrator import MAX_ORCHESTRATION_ATTEMPTS, WorkflowOrchestrator
from development.prompting import PARAMETER_NOTICE
from shared.executor import ExecutorKind
from shared.llm_client import MockLLMClient
from shared.workflow import LogicalEdge, TaskRef

SPEC_PATH = "development/specs/code_generation.py"

EXPECTED = {
    "propose_solutions": "llm_debate_coders",
    "write_tests": "llm_unit_test_writer",
    "execute_tests": "python_interpreter",
    "rank_solutions": "llm_ranker",
}


@pytest.fixture()
def library():
    return code_generation_library()


@pytest.fixture()
def result(library):
    llm = MockLLMClient(mode="fixture", fixture=EXPECTED)
    return WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)


def test_produces_the_expected_code_generation_dag(result):
    workflow = result.workflow
    assert result.attempts == 1
    assert workflow.workflow_id == "code_generation"
    assert {n.task_id: n.executor for n in workflow.nodes} == EXPECTED


def test_all_three_executor_forms_are_exercised(result, library):
    """Section 3.2 (p.572) defines exactly three forms: LLM, structured composition, tool."""
    kinds = {library.get(n.executor).kind for n in result.workflow.nodes}
    assert kinds == {ExecutorKind.LLM, ExecutorKind.COMPOSITION, ExecutorKind.TOOL}


def test_debate_composition_exposes_the_papers_knobs(result, library):
    """Section 3.2 (p.572): "The LLM Debate composition exposes the knobs: D (number of
    debaters), R (number of rounds), and model (which LLM to use)"."""
    node = result.workflow.node("propose_solutions")
    assert library.get(node.executor).kind is ExecutorKind.COMPOSITION
    assert {p.name for p in node.open_parameters} == {"D", "R", "model"}


def test_parameters_are_declared_but_unbound(result):
    """Section 3.2 (p.572) defers "parameter configuration to a later optimization phase"."""
    for node in result.workflow.nodes:
        for parameter in node.open_parameters:
            assert not hasattr(parameter, "value")


def test_debate_loop_is_a_knob_not_a_cycle(result):
    """Figure 1b's multi-round debate arc is internal to the composition; the logical workflow
    "is represented as a directed acyclic graph" (Section 3.2, p.573)."""
    node = result.workflow.node("propose_solutions")
    assert "R" in {p.name for p in node.open_parameters}
    assert not any(e.src_task == e.dst_task for e in result.workflow.edges)
    positions = {n.task_id: i for i, n in enumerate(result.workflow.nodes)}
    for edge in result.workflow.edges:
        assert positions[edge.src_task] < positions[edge.dst_task]


def test_boundary_and_output_ports_carry_types_but_no_values(result):
    workflow = result.workflow
    assert [p.name for p in workflow.inputs] == ["query"]
    assert workflow.inputs[0].type == "Query"
    assert workflow.outputs[0].type == "Answer"


def test_prompt_shows_all_task_descriptions_in_one_call(result):
    """Section 3.2 (p.573): the orchestrator "receives a list of available executors and their
    interfaces, along with task descriptions" -- plural, one interaction."""
    assert len(result.prompts) == 1
    prompt = result.prompts[0]
    for task_id in EXPECTED:
        assert task_id in prompt
    for executor in ("llm_debate_coders", "python_interpreter", "llm_ranker"):
        assert executor in prompt


def test_prompt_shows_knob_names_but_forbids_choosing_values(result):
    prompt = result.prompts[0]
    assert PARAMETER_NOTICE in prompt
    assert "knobs (set later by the optimizer): ['D', 'R', 'model']" in prompt


def test_keyword_mock_reaches_the_same_assignment(library):
    """The rule-based mock stands in for a plausible LLM choice, with no network call."""
    llm = MockLLMClient(mode="keyword")
    result = WorkflowOrchestrator(library, llm).orchestrate_file(SPEC_PATH)
    assert {n.task_id: n.executor for n in result.workflow.nodes} == EXPECTED


def test_default_retry_bound_is_the_documented_design_choice():
    assert MAX_ORCHESTRATION_ATTEMPTS == 3


# ---------------------------------------------------------------------------------------------
# Precedence edges (DESIGN.md Section 8.1)
# ---------------------------------------------------------------------------------------------


def test_edges_carry_full_precedence_information(result):
    """Section 3.2 (p.573): "edges denote data flow". We keep them, so that a later
    precedence-aware scheduler COULD use them -- even though Murakkab's own formulation
    (Appendix A.5, eqs 1-13) has no precedence constraint and no makespan term."""
    edges = set(result.workflow.edges)
    assert LogicalEdge("propose_solutions", "write_tests", 1, "CodeCandidates") in edges
    assert LogicalEdge("propose_solutions", "execute_tests", 0, "CodeCandidates") in edges
    assert LogicalEdge("write_tests", "execute_tests", 1, "TestSuite") in edges
    assert LogicalEdge("propose_solutions", "rank_solutions", 1, "CodeCandidates") in edges
    assert LogicalEdge("execute_tests", "rank_solutions", 1, "ExecutionResults") in edges
    # fan-out is preserved rather than linearized
    assert sum(1 for e in edges if e.src_task == "propose_solutions") == 3


def test_optimizer_must_not_consume_edges_for_scheduling(result):
    """The rule from DESIGN.md Section 8.1, pinned where a future milestone will see it.

    A test cannot enforce what Milestone 4 does; what it CAN do is pin the documented rule to
    the artifact, so that deleting the rule breaks the build rather than passing silently.
    """
    doc = LogicalEdge.__doc__ or ""
    assert "RULE FOR MILESTONES 4/5" in doc
    assert "must NOT read these edges for scheduling" in doc
    assert "no precedence constraint" in doc and "makespan term" in doc
    # The information is present and would be usable, which is the point of keeping it.
    assert result.workflow.edges
    assert all(e.type for e in result.workflow.edges)


def test_workflow_output_matches_the_specs_return(result):
    graph_output = TaskRef("rank_solutions")
    assert result.workflow.nodes[-1].task_id == graph_output.task_id
