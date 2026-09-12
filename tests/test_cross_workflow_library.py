"""
Two catalogues, one library: what the union does to selection.

Covers Murakkab (OSDI '26), Section 3.2, "Executor Library" (p.572): "mapping a broad range of
unknown tasks to executors that are built from a finite, known set of models and tools in the
library". The paper describes ONE shared library -- executors are meant to be reusable across
workflows -- so `default_library()` is the flat union of every registered catalogue and the
orchestrator sees all 26 entries for every sub-task.

Also pins the registration mechanism itself: Milestone 2's `registry.py` holds zero executor
definitions precisely so that a second workflow is a registration, not a refactor
(DESIGN.md Section 8, point 1).
"""

from __future__ import annotations

from development.executor_lib import (
    CATALOGUES,
    CODE_GENERATION_EXECUTORS,
    VIDEO_QA_EXECUTORS,
    code_generation_library,
    default_library,
    library_for,
    video_qa_library,
)
from development.orchestrator import WorkflowOrchestrator
from development.spec_parser import parse_spec_file
from development.type_check import bind_and_type_check
from shared.llm_client import MockLLMClient

CODE_GEN_SPEC = "development/specs/code_generation.py"
VIDEO_QA_SPEC = "development/specs/video_qa.py"


def test_a_second_workflow_was_a_registration_not_a_refactor():
    """The design claim, asserted rather than trusted."""
    assert set(CATALOGUES) == {"code_generation", "video_qa"}
    assert CATALOGUES["video_qa"] == VIDEO_QA_EXECUTORS
    # registry.py defines no executors of its own
    import development.executor_lib.registry as registry
    from shared.executor import ExecutorSpec

    assert not [v for v in vars(registry).values() if isinstance(v, ExecutorSpec)]


def test_the_union_is_flat_finite_and_collision_free():
    union = default_library().all()
    assert union == CODE_GENERATION_EXECUTORS + VIDEO_QA_EXECUTORS
    assert len(union) == 26
    assert len({e.name for e in union}) == 26
    # the per-workflow views remain available for isolation
    assert library_for("code_generation").all() == code_generation_library().all()
    assert library_for("video_qa").all() == video_qa_library().all()


def test_shared_model_ids_are_not_duplicated_per_workflow():
    """`Gemma-3-27B` and `NVLM-D-72B` are in both domains and must be ONE id: Section 4.3's
    multiplexing (p.576) depends on two workflows landing on the SAME model instance, and M3 keys
    one profile per string."""
    from shared.model_ids import ALL_MODEL_IDS, CODE_GEN_MODELS, VIDEO_QA_MODELS

    shared = set(CODE_GEN_MODELS) & set(VIDEO_QA_MODELS)
    assert shared == {"Gemma-3-27B", "NVLM-D-72B"}
    assert ALL_MODEL_IDS == set(CODE_GEN_MODELS) | set(VIDEO_QA_MODELS)
    assert len(ALL_MODEL_IDS) == 7  # 5 + 4 - 2 shared


def test_no_code_gen_executor_type_checks_into_a_video_subtask():
    """The type-check (Section 3.2, p.573) is the backstop against cross-workflow confusion."""
    graph, _ = parse_spec_file(VIDEO_QA_SPEC)
    library = default_library()
    code_gen_names = {e.name for e in CODE_GENERATION_EXECUTORS}
    for task_id in ("scene_detect", "frame_extract", "stt", "q_a"):
        for name in code_gen_names:
            assignment = {
                "scene_detect": "opencv_scene_detector",
                "frame_extract": "opencv_frame_extractor",
                "stt": "whisper_stt",
                "q_a": "multimodal_llm_qa",
            }
            assignment[task_id] = name
            assert not bind_and_type_check(graph, library, assignment).ok, (task_id, name)


def test_no_video_executor_type_checks_into_a_code_gen_subtask():
    graph, _ = parse_spec_file(CODE_GEN_SPEC)
    library = default_library()
    for task_id in ("propose_solutions", "write_tests", "execute_tests", "rank_solutions"):
        for executor in VIDEO_QA_EXECUTORS:
            assignment = {
                "propose_solutions": "llm_debate_coders",
                "write_tests": "llm_unit_test_writer",
                "execute_tests": "python_interpreter",
                "rank_solutions": "llm_ranker",
            }
            assignment[task_id] = executor.name
            assert not bind_and_type_check(graph, library, assignment).ok, (task_id, executor.name)


def test_code_generation_selection_is_unchanged_by_the_bigger_menu():
    """Adding 13 Video Q/A entries displaces nothing on the Code Gen workflow: the keyword mock's
    scores and ranks are identical to Milestone 2's."""
    expected = {
        "propose_solutions": "llm_debate_coders",
        "write_tests": "llm_unit_test_writer",
        "execute_tests": "python_interpreter",
        "rank_solutions": "llm_ranker",
    }
    result = WorkflowOrchestrator(default_library(), MockLLMClient(mode="keyword")).orchestrate_file(
        CODE_GEN_SPEC
    )
    assert {n.task_id: n.executor for n in result.workflow.nodes} == expected
    assert result.attempts == 1


def test_keyword_mock_crosses_workflows_and_the_type_check_catches_it():
    """A FINDING about the mock, pinned rather than tuned away.

    Over the 26-executor union, `MockLLMClient`'s keyword mode picks the Code Generation
    `llm_ranker` (score 0.310) for the Video Q/A `q_a` sub-task, ahead of `multimodal_llm_qa`
    (0.283) -- Listing 2's `q_a` description, "Answer the query given some context", shares
    "answer"/"query"/"context" with the ranker and is shorter to match against.

    The orchestrator recovers: `llm_ranker`'s variadic port accepts CodeCandidates /
    ExecutionResults / TestSuite, not Frames / Transcript, so the type-check rejects it and the
    regeneration loop of Section 3.2 (p.573) reaches `multimodal_llm_qa` on attempt 2. That is the
    loop doing its job on a realistic mistake -- the first genuinely cross-workflow one in the
    repo.
    """
    result = WorkflowOrchestrator(default_library(), MockLLMClient(mode="keyword")).orchestrate_file(
        VIDEO_QA_SPEC
    )
    assert result.attempts == 2  # attempt 1 chose across workflows and was rejected
    assert result.workflow.node("q_a").executor == "multimodal_llm_qa"


def test_keyword_mock_prefers_terse_descriptions_over_correct_ones():
    """A second FINDING about the mock, also pinned rather than tuned away.

    For `scene_detect` ("Given a list of videos, identify scenes in each.") the keyword mock ranks
    `opencv_scene_detector` -- the executor the paper names (Listing 1 p.569, Section 2.3 p.569) --
    SEVENTH, at 0.091, behind the invented `fixed_interval_segmenter` at 0.133. The cause is
    structural: the score is token overlap divided by the CANDIDATE's token count, so a longer,
    more discriminating description is penalized. Milestone 2's own contract obliges descriptions
    to "discriminate on behaviour", which pushes them longer. The two pull against each other.

    Both candidates type-check identically, so nothing downstream catches this one. It is a
    property of length-normalized token overlap, NOT evidence about a real LLM, and the fix is a
    better client rather than shorter descriptions -- so the descriptions stay as written and the
    behaviour is asserted here, visibly, as the mock's limitation.
    """
    result = WorkflowOrchestrator(default_library(), MockLLMClient(mode="keyword")).orchestrate_file(
        VIDEO_QA_SPEC
    )
    assert result.workflow.node("scene_detect").executor == "fixed_interval_segmenter"
    # ...and the workflow is still type-correct, which is all the orchestrator guarantees
    assert result.workflow.node("stt").executor == "whisper_stt"
    assert result.workflow.node("frame_extract").executor == "opencv_frame_extractor"
