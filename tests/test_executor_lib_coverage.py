"""
Selection must be a real choice: every Code Generation sub-task needs genuine alternatives.

Covers Murakkab (OSDI '26), Section 3.2 (p.572-573): the orchestrator "receives a list of
available executors and their interfaces, along with task descriptions, and selects the best
executor for each sub-task", drawing from "a finite, known set of models and tools in the library.
If none is found, Murakkab prompts the developer to onboard a suitable one."

Milestone 1's stub offered exactly ONE type-compatible executor for three of the four sub-tasks,
so "selection" was a forced move and neither a wrong choice nor the onboarding escalation could
occur for those tasks. These tests pin the property that fixed it (executor_lib/DESIGN.md
Sections 1.3 and 4.5).
"""

from __future__ import annotations

from development.executor_lib import CODE_GENERATION_EXECUTORS, code_generation_library
from development.spec_parser import parse_spec_file
from shared.executor import ExecutorKind, ExecutorSpec
from shared.types import ANSWER, CODE_CANDIDATES, EXECUTION_RESULTS, QUERY, TEST_SUITE

SPEC_PATH = "development/specs/code_generation.py"

# The four sub-task signatures of the declarative spec (M1 DESIGN.md Section 2.4), written as
# (per-argument-position tuples of source types, produced type). Position 1 of `rank_solutions`
# is a list literal -- `rank_solutions(query, [candidates, results])` -- so it carries two types.
SIGNATURES: dict[str, tuple[tuple[tuple[str, ...], ...], str]] = {
    "propose_solutions": (((QUERY,),), CODE_CANDIDATES),
    "write_tests": (((QUERY,), (CODE_CANDIDATES,)), TEST_SUITE),
    "execute_tests": (((CODE_CANDIDATES,), (TEST_SUITE,)), EXECUTION_RESULTS),
    "rank_solutions": (((QUERY,), (CODE_CANDIDATES, EXECUTION_RESULTS)), ANSWER),
}


def _viable(executor: ExecutorSpec, signature) -> bool:
    """Would this executor survive M1's binding + type-check at this call site?

    Mirrors M1 DESIGN.md Section 4.4: positional arity, nominal type equality, and a variadic port
    for any list-literal argument.
    """
    argument_types, output_type = signature
    if len(executor.inputs) != len(argument_types):
        return False
    if executor.output.type != output_type:
        return False
    for port, sources in zip(executor.inputs, argument_types):
        if len(sources) > 1:
            if not port.variadic or not set(sources) <= set(port.accepted_types):
                return False
        elif sources[0] != port.type:
            return False
    return True


def _candidates(task_id: str) -> tuple[ExecutorSpec, ...]:
    return tuple(e for e in CODE_GENERATION_EXECUTORS if _viable(e, SIGNATURES[task_id]))


def test_the_spec_really_has_these_four_subtasks():
    """Guard against the signature table drifting from the declarative spec it describes."""
    graph, _ = parse_spec_file(SPEC_PATH)
    assert {n.task_id for n in graph.nodes} == set(SIGNATURES)


def test_every_subtask_has_at_least_three_viable_candidates():
    for task_id in SIGNATURES:
        assert len(_candidates(task_id)) >= 3, task_id


def test_every_subtask_spans_at_least_two_executor_kinds():
    """A choice between three LLMs is a weaker test than a choice between an LLM, a composition
    and a tool -- the three forms of Section 3.2 (p.572)."""
    for task_id in SIGNATURES:
        assert len({e.kind for e in _candidates(task_id)}) >= 2, task_id


def test_all_three_executor_forms_appear_in_the_catalogue():
    kinds = {e.kind for e in CODE_GENERATION_EXECUTORS}
    assert kinds == {ExecutorKind.LLM, ExecutorKind.COMPOSITION, ExecutorKind.TOOL}


def test_no_dead_entries():
    """Every entry must be reachable by at least one Code Gen sub-task. An unreachable executor is
    dead weight in the prompt and, worse, a profile M3 would collect and nobody would use."""
    reachable = {e.name for task in SIGNATURES for e in _candidates(task)}
    assert reachable == {e.name for e in CODE_GENERATION_EXECUTORS}


def test_type_checking_cannot_do_the_orchestrators_job():
    """At least one sub-task must have candidates that are type-INDISTINGUISHABLE.

    If every wrong choice were catchable by the type-check (Section 3.2, p.573), the LLM's reading
    of the descriptions would never matter and the selection step would be decorative.
    """
    ambiguous = {t for t in SIGNATURES if len(_candidates(t)) >= 2}
    assert ambiguous == set(SIGNATURES)
    # concretely: the debate composition and the few-shot LLM are interchangeable to the checker
    names = {e.name for e in _candidates("propose_solutions")}
    assert {"llm_debate_coders", "llm_fewshot_coder"} <= names


def test_a_tool_only_stage_is_selectable_for_three_of_four_subtasks():
    """Records the Tool-invisibility exposure of DESIGN.md Section 6.1.

    A TOOL contributes zero tokens, zero energy, zero cost and zero capacity to Appendix A.5
    (p.586-587), so any sub-task that can be served by a Tool can be made free. This asserts the
    exposure exists and is reachable -- it is a property of Murakkab's formulation being
    reproduced, not a bug to fix here.
    """
    tool_servable = {
        task for task in SIGNATURES if any(e.kind is ExecutorKind.TOOL for e in _candidates(task))
    }
    assert tool_servable == {"write_tests", "execute_tests", "rank_solutions"}


def test_library_and_catalogue_agree():
    assert code_generation_library().all() == CODE_GENERATION_EXECUTORS
