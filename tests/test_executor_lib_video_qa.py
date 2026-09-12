"""
Contract and coverage for the Video Q/A catalogue (Milestone 2b).

Covers Murakkab (OSDI '26), Section 3.2, "Executor Library" and "Attributes" (p.572) for the
workflow of Figure 1a (p.568) / Listing 2 (p.572), with knob domains from Table 5 (p.585) and
Figures 2a / 4a (p.570-571).

Mirrors the two Code Generation test modules (`test_executor_lib_contract.py`,
`test_executor_lib_coverage.py`) so that the same properties are enforced per catalogue.
"""

from __future__ import annotations

import pytest

from development.executor_lib import (
    HARDWARE_LEVEL_KNOBS,
    KNOB_LEVELS,
    VIDEO_QA_EXECUTORS,
    VIDEO_QA_GROUNDING,
    VIDEO_QA_NOT_NAMED_BY_THE_PAPER,
    video_qa_library,
)
from development.spec_parser import parse_spec_file
from shared.executor import ExecutorKind, ExecutorSpec
from shared.model_ids import VIDEO_QA_MODELS
from shared.types import ANNOTATED_FRAMES, ANSWER, FRAMES, QUERY, SCENES, TRANSCRIPT, VIDEOS

SPEC_PATH = "development/specs/video_qa.py"

# Listing 2's four call sites, as (per-argument-position source types, produced type).
SIGNATURES: dict[str, tuple[tuple[tuple[str, ...], ...], str]] = {
    "scene_detect": (((VIDEOS,),), SCENES),
    "frame_extract": (((SCENES,),), FRAMES),
    "stt": (((SCENES,),), TRANSCRIPT),
    "q_a": (((QUERY,), (FRAMES, TRANSCRIPT)), ANSWER),
}


def _viable(executor: ExecutorSpec, signature) -> bool:
    """Mirrors M1 DESIGN.md Section 4.4: positional arity, nominal equality, variadic membership.

    `frame_extract` is special: an executor may produce `Frames` OR `AnnotatedFrames` (gap A22 --
    object detection has no sub-task of its own under Listing 2), and both are accepted downstream
    by `q_a`'s variadic context port.
    """
    argument_types, output_type = signature
    if len(executor.inputs) != len(argument_types):
        return False
    accepted_outputs = (
        {FRAMES, ANNOTATED_FRAMES} if output_type == FRAMES else {output_type}
    )
    if executor.output.type not in accepted_outputs:
        return False
    for port, sources in zip(executor.inputs, argument_types):
        if len(sources) > 1:
            if not port.variadic or not set(sources) <= set(port.accepted_types):
                return False
        elif sources[0] != port.type:
            return False
    return True


def _candidates(task_id: str) -> tuple[ExecutorSpec, ...]:
    return tuple(e for e in VIDEO_QA_EXECUTORS if _viable(e, SIGNATURES[task_id]))


@pytest.fixture()
def library():
    return video_qa_library()


# --- contract ---------------------------------------------------------------------------------


def test_every_entry_exposes_the_three_attributes():
    for executor in VIDEO_QA_EXECUTORS:
        assert executor.description.strip()  # (1)
        assert executor.inputs and len(executor.outputs) == 1  # (2)
        assert isinstance(executor.parameters, tuple)  # (3)
        assert isinstance(executor.kind, ExecutorKind)


def test_names_are_unique_and_the_library_is_flat(library):
    names = [e.name for e in VIDEO_QA_EXECUTORS]
    assert len(names) == len(set(names)) == 13
    assert library.all() == VIDEO_QA_EXECUTORS


def test_no_parameter_carries_a_value():
    for executor in VIDEO_QA_EXECUTORS:
        for parameter in executor.parameters:
            assert not hasattr(parameter, "value")


def test_no_executor_declares_a_hardware_knob():
    """Section 3.3.1 Decision 3 (p.574): GPU type and parallelism follow from the model profile."""
    for executor in VIDEO_QA_EXECUTORS:
        for parameter in executor.parameters:
            assert parameter.name.lower() not in HARDWARE_LEVEL_KNOBS
            for value in parameter.domain or ():
                assert not (isinstance(value, str) and value.upper() in {"A100", "H100"})


def test_grounding_covers_every_entry_and_nothing_else():
    assert set(VIDEO_QA_GROUNDING) == {e.name for e in VIDEO_QA_EXECUTORS}
    assert set(VIDEO_QA_GROUNDING.values()) <= {"PAPER", "PAPER-FORM", "INVENTED"}
    # the entries the paper names for THIS workflow, by figure/listing/section
    assert {n for n, g in VIDEO_QA_GROUNDING.items() if g == "PAPER"} == {
        "opencv_scene_detector",  # Listing 1 p.569; Section 2.3 p.569
        "opencv_frame_extractor",  # Section 3.2 p.572 (the F + cores example); Listing 1
        "clip_frame_annotator",  # Listing 1 p.569
        "whisper_stt",  # Listing 1 p.569; Section 4.1 p.575; Section 4.6 p.578
        "multimodal_llm_qa",  # Figure 1a p.568; Section 2.2 item 5 p.568
    }
    assert len(VIDEO_QA_NOT_NAMED_BY_THE_PAPER) == 8


def test_grounding_markers_never_leak_into_prompt_facing_text():
    for executor in VIDEO_QA_EXECUTORS:
        assert "INVENTED" not in executor.description
        assert "PAPER" not in executor.description


def test_catalogue_contains_no_performance_data():
    banned = ("accuracy", "pass@1", "tpot", "ttft", "tokens/", "watt", "wh ", "$", "latency of")
    for executor in VIDEO_QA_EXECUTORS:
        text = executor.description.lower()
        for token in banned:
            assert token not in text


# --- knobs ------------------------------------------------------------------------------------


def test_frame_extractor_exposes_the_papers_own_example_knobs(library):
    """Section 3.2 (p.572), verbatim: "the frame extraction tool exposes the knobs: F (number of
    frames to extract) and cores (number of CPU cores to run on)"."""
    extractor = library.get("opencv_frame_extractor")
    assert extractor.parameter_names == ("F", "cores")


def test_frames_domain_is_the_literal_set_from_table_5():
    """Table 5's `Frames` column (p.585), Figure 2a's x-axis (p.570) and Figure 4a's size legend
    (p.571) all use {1, 5, 10}. Listing 1's `num_frames: 15` is outside it -- gap A29."""
    for executor in VIDEO_QA_EXECUTORS:
        for parameter in executor.parameters:
            if parameter.name == "F":
                assert parameter.domain == (1, 5, 10)


def test_video_model_domain_is_table_5_plus_figure_4a():
    assert VIDEO_QA_MODELS == (
        "Llava-OneVision-7B",
        "Gemma-3-27B",  # shared with Code Generation -- one id, not duplicated
        "NVLM-D-72B",  # shared with Code Generation
        "Llama-3.2-90B",
    )
    for executor in VIDEO_QA_EXECUTORS:
        for parameter in executor.parameters:
            if parameter.name == "model":
                assert parameter.domain == VIDEO_QA_MODELS


def test_debate_knob_domains_are_inherited_from_code_generation(library):
    """Gap A26, pinned deliberately. `D`/`R` = {2,4} comes from Table 6 (p.586), which is CODE
    GENERATION. The paper never measures debaters or rounds for Video Q/A, so these domains are
    inherited, not evidenced. Decision Q8 (2026-09-11) accepted that and asked for the flag."""
    debate = library.get("multimodal_debate_qa")
    assert debate.parameter_names == ("D", "R", "model")
    assert {p.domain for p in debate.parameters if p.name in {"D", "R"}} == {(2, 4)}


def test_tool_executors_expose_no_model_knob(library):
    """Decision Q9/Q10: Whisper, OmDet and CLIP are TOOLs (Section 3.2, p.572: "Traditional ML
    models are also included as tools"), and a Tool IS its backend -- there is no `model` knob and
    no `backend` knob, so the choice of STT engine is executor identity, fixed at onboarding.

    Consequence (gap A31): Section 3.3.1 Decision 2 (p.574) promises "the chosen model **or tool**
    for each executor" per epoch, and the tool half of that promise has no knob to ride on.
    """
    for name in ("whisper_stt", "omdet_frame_annotator", "clip_frame_annotator"):
        executor = library.get(name)
        assert executor.kind is ExecutorKind.TOOL
        assert "model" not in executor.parameter_names
        assert "backend" not in executor.parameter_names


def test_cores_sits_on_exactly_the_executors_section_4_6_offloads(library):
    """Gap A30. Section 4.6 (p.578) runs Whisper and OmDet on CPUs (Figures 12b/12c) and reports
    meeting the latency SLO while cutting GPU usage. Appendix A.5 has no CPU resource type, no
    placement variable, and a GPU-only budget constraint (7), so this knob is declared, shown to
    the orchestrator, and consumed by nobody."""
    for name in ("whisper_stt", "omdet_frame_annotator"):
        assert "cores" in library.get(name).parameter_names
    assert KNOB_LEVELS["cores"] == "hardware-exposed-as-executor"


def test_no_stt_enabled_knob_is_declared_anywhere():
    """Decision Q6 / gap A18: the library declares no existence knob, on any executor."""
    declared = {p.name for e in VIDEO_QA_EXECUTORS for p in e.parameters}
    assert declared == {"cores", "segment_s", "model", "F", "R", "D"}
    assert "stt_enabled" not in declared


# --- coverage ---------------------------------------------------------------------------------


def test_the_spec_really_has_these_four_subtasks():
    graph, _ = parse_spec_file(SPEC_PATH)
    assert {n.task_id for n in graph.nodes} == set(SIGNATURES)


def test_every_subtask_has_at_least_three_viable_candidates():
    for task_id in SIGNATURES:
        assert len(_candidates(task_id)) >= 3, task_id


def test_every_subtask_spans_at_least_two_executor_kinds():
    for task_id in SIGNATURES:
        assert len({e.kind for e in _candidates(task_id)}) >= 2, task_id


def test_no_dead_entries():
    reachable = {e.name for task in SIGNATURES for e in _candidates(task)}
    assert reachable == {e.name for e in VIDEO_QA_EXECUTORS}


def test_the_q_a_stage_has_no_tool_option():
    """Decision Q11 (2026-09-11): deliberately not offered.

    A tool-servable answer node would permit a Video Q/A DAG in which every stage is a Tool -- a
    whole workflow Appendix A.5 prices at zero across all four objectives. Three of four stages
    already expose that gap; a fourth would be gratuitous invention.
    """
    assert not any(e.kind is ExecutorKind.TOOL for e in _candidates("q_a"))
    for task in ("scene_detect", "frame_extract", "stt"):
        assert any(e.kind is ExecutorKind.TOOL for e in _candidates(task))


def test_object_detection_has_no_node_of_its_own():
    """Gap A22, pinned. Figure 1a (p.568) and Section 2.2 (p.568) describe an Object Detector
    agent; Listing 2 (p.572) declares no such sub-task. Reproducing Listing 2 folds detection into
    `frame_extract`, so annotation surfaces as an alternative OUTPUT TYPE."""
    graph, _ = parse_spec_file(SPEC_PATH)
    assert not any("detect" in n.task_id and n.task_id != "scene_detect" for n in graph.nodes)
    outputs = {e.name: e.output.type for e in _candidates("frame_extract")}
    assert outputs["opencv_frame_extractor"] == FRAMES
    assert outputs["omdet_frame_annotator"] == ANNOTATED_FRAMES
    assert outputs["clip_frame_annotator"] == ANNOTATED_FRAMES
