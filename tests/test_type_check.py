"""
Tests for positional binding and DAG type-checking.

Covers Murakkab (OSDI '26), Section 3.2, "Logical Workflow" (p.573): "The orchestrator performs
type-checking on the DAG to ensure output types from source nodes match input types of
destination nodes."

Each of the five checks in DESIGN.md Section 4.4 must fail for its own reason.
"""

from __future__ import annotations

import pytest

from development.executor_library import InMemoryExecutorLibrary, code_generation_library
from development.spec_parser import parse_spec_file, parse_spec_source
from development.type_check import bind_and_type_check, viable_executors
from shared.executor import ExecutorKind, ExecutorSpec, ParameterSpec, Port
from shared.types import (
    ANSWER,
    CODE_CANDIDATES,
    EXECUTION_RESULTS,
    QUERY,
    TEST_SUITE,
    UnknownTypeError,
)

SPEC_PATH = "development/specs/code_generation.py"

GOOD = {
    "propose_solutions": "llm_debate_coders",
    "write_tests": "llm_unit_test_writer",
    "execute_tests": "python_interpreter",
    "rank_solutions": "llm_ranker",
}


@pytest.fixture()
def graph():
    parsed, _ = parse_spec_file(SPEC_PATH)
    return parsed


@pytest.fixture()
def library():
    return code_generation_library()


def test_correct_assignment_type_checks(graph, library):
    result = bind_and_type_check(graph, library, GOOD)
    assert result.ok
    assert result.mismatches == ()
    assert result.workflow is not None


def test_check_1_edge_type_equality(graph, library):
    """A ranker takes a Query first; feeding it CodeCandidates must be caught."""
    bad = dict(GOOD, execute_tests="llm_ranker")
    result = bind_and_type_check(graph, library, bad)
    assert not result.ok
    messages = [m.message for m in result.mismatches if m.task_id == "execute_tests"]
    assert messages
    assert "accepts ['Query']" in messages[0]
    assert "CodeCandidates" in messages[0]


def test_check_2_arity(graph, library):
    """`write_tests` is called with two inputs; a one-port executor cannot serve it."""
    bad = dict(GOOD, write_tests="llm_single_shot_coder")
    result = bind_and_type_check(graph, library, bad)
    assert not result.ok
    assert any("declares 1 input port" in m.message for m in result.mismatches)


def test_check_3_variadic_required_for_list_argument(graph, library):
    """`rank_solutions(query, [candidates, results])` needs a variadic second port."""
    non_variadic_ranker = ExecutorSpec(
        name="llm_ranker",  # same name, non-variadic context port
        kind=ExecutorKind.LLM,
        description="ranker with a single-valued context port",
        inputs=(Port("problem", QUERY), Port("context", CODE_CANDIDATES)),
        outputs=(Port("answer", ANSWER),),
        parameters=(ParameterSpec("model", "str"),),
    )
    patched = InMemoryExecutorLibrary(
        tuple(e for e in library.all() if e.name != "llm_ranker") + (non_variadic_ranker,)
    )
    result = bind_and_type_check(graph, patched, GOOD)
    assert not result.ok
    assert any("is not variadic" in m.message for m in result.mismatches)


def test_check_3_variadic_accepts_heterogeneous_elements(graph, library):
    """Listing 2's `q_a(query, [frames, transcript])` mixes types in one argument, so a variadic
    port must accept a SET of types. (Design-doc correction, DESIGN.md Section 4.3.)"""
    ranker = library.get("llm_ranker")
    context = ranker.inputs[1]
    assert context.variadic
    assert set(context.accepted_types) == {CODE_CANDIDATES, EXECUTION_RESULTS, TEST_SUITE}

    result = bind_and_type_check(graph, library, GOOD)
    binding = result.workflow.node("rank_solutions").inputs[1]
    source_types = {
        result.workflow.node(s.task_id).output_type for s in binding.sources
    }
    assert source_types == {CODE_CANDIDATES, EXECUTION_RESULTS}  # genuinely heterogeneous


def test_check_4_boundary_parameter_must_have_a_consistent_type():
    """`x` feeds a Query port and a TestSuite port; the workflow input cannot be both."""
    source = (
        'first  = "consume the request."\n'
        'second = "consume the request differently."\n'
        "def workflow(x):\n"
        "    a = first(x)\n"
        "    b = second(x, a)\n"
        "    return b\n"
    )
    graph, _ = parse_spec_source(source, "boundary")
    library = InMemoryExecutorLibrary(
        (
            ExecutorSpec(
                name="takes_query",
                kind=ExecutorKind.LLM,
                description="takes a query",
                inputs=(Port("q", QUERY),),
                outputs=(Port("out", CODE_CANDIDATES),),
            ),
            ExecutorSpec(
                name="takes_tests",
                kind=ExecutorKind.LLM,
                description="takes a test suite",
                inputs=(Port("t", TEST_SUITE), Port("c", CODE_CANDIDATES)),
                outputs=(Port("out", ANSWER),),
            ),
        )
    )
    result = bind_and_type_check(
        graph, library, {"first": "takes_query", "second": "takes_tests"}
    )
    assert not result.ok
    assert any("workflow input 'x'" in m.message for m in result.mismatches)


def test_check_5_nodes_are_topologically_ordered(graph, library):
    """Acyclicity is guaranteed by the parser and re-asserted by LogicalWorkflow."""
    workflow = bind_and_type_check(graph, library, GOOD).workflow
    position = {n.task_id: i for i, n in enumerate(workflow.nodes)}
    for edge in workflow.edges:
        assert position[edge.src_task] < position[edge.dst_task]


def test_unassigned_task_is_reported(graph, library):
    result = bind_and_type_check(graph, library, {k: v for k, v in GOOD.items() if k != "write_tests"})
    assert any(m.executor == "<unassigned>" for m in result.mismatches)


def test_unknown_executor_is_reported_not_raised(graph, library):
    """A hallucinated executor name is a mismatch to feed back, not a crash."""
    result = bind_and_type_check(graph, library, dict(GOOD, write_tests="gpt-9-omni"))
    assert not result.ok
    assert any("not in the executor library" in m.message for m in result.mismatches)


def test_no_adapter_is_inserted_on_mismatch(graph, library):
    """DESIGN.md D8: on mismatch the workflow is rejected, never silently coerced."""
    result = bind_and_type_check(graph, library, dict(GOOD, execute_tests="llm_ranker"))
    assert result.workflow is None


def test_viable_executors_reports_alternatives(graph, library):
    """The escalation payload is computed mechanically and is a report, not a fallback.

    UPDATED IN MILESTONE 2. Under M1's five-entry stub `python_interpreter` was the ONLY
    type-compatible executor for `execute_tests`, so this assertion read `== ("python_interpreter",)`
    and could not distinguish "the report is correct" from "there was nothing to report". The M2
    catalogue gives the sub-task three candidates (executor_lib/DESIGN.md Section 4.3), so the
    assertion still pins an EXACT tuple in library declaration order -- it is not loosened, it now
    has something to be exact about.
    """
    bad = dict(GOOD, execute_tests="llm_ranker")
    assert viable_executors(graph, library, bad, "execute_tests") == (
        "python_interpreter",
        "sandboxed_container_runner",
        "llm_execution_simulator",
    )


def test_port_type_must_be_in_the_registry():
    with pytest.raises(UnknownTypeError):
        Port("p", "NotARegisteredType")


def test_also_accepts_requires_a_variadic_port():
    with pytest.raises(ValueError, match="variadic"):
        Port("p", QUERY, variadic=False, also_accepts=(ANSWER,))
