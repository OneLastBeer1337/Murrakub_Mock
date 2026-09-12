"""
The Video Q/A declarative specification is Listing 2 (p.572), reproduced verbatim.

Covers Murakkab (OSDI '26), Section 3.2, "Declarative Specification" (p.572-573) and Listing 2,
whose caption reads: "Murakkab's declarative workflow specification of the video Q/A abstracts away
configuration details, letting developers focus on application logic."

This is the ONE workflow the paper writes down declaratively, so "reproduce literally" is
mechanically checkable here in a way it was not for Code Generation (M1 gap A1). The first test
below does exactly that: character-for-character.
"""

from __future__ import annotations

import pytest

from development.executor_lib import video_qa_library
from development.orchestrator import WorkflowOrchestrator
from development.spec_parser import parse_spec_file
from shared.llm_client import MockLLMClient
from shared.workflow import BoundaryRef, TaskRef, audit_request_agnostic

SPEC_PATH = "development/specs/video_qa.py"

# Listing 2 (p.572) verbatim -- identical to the LISTING_2 constant that
# tests/test_spec_parser.py has asserted against M1's parser since Milestone 1.
LISTING_2 = '''\
# == Sub-tasks in the workflow ==
scene_detect  = "Given a list of videos, identify scenes in each."
frame_extract = "Given a list of scenes, extract frames."
stt           = "Given a list of scenes, convert audio to text."
q_a           = "Answer the query given some context."
# == Workflow description (sub-tasks and data flow) ==
def workflow(query, videos):
    scenes     = scene_detect(videos)
    frames     = frame_extract(scenes)
    transcript = stt(scenes)
    answer     = q_a(query, [frames, transcript])
    return answer
# == Execution with example request ==
query  = "What is the name of the person wearing the red dress?"
videos = ["road_trip.mp4"]
result = run(workflow(query, videos), slo=LOW_LATENCY)
'''

# Figure 1a (p.568) maps onto these four sub-tasks; see DESIGN_VIDEO_QA.md A22 for the two
# places Figure 1a and Listing 1 disagree with Listing 2.
EXPECTED = {
    "scene_detect": "opencv_scene_detector",
    "frame_extract": "opencv_frame_extractor",
    "stt": "whisper_stt",
    "q_a": "multimodal_llm_qa",
}


@pytest.fixture()
def parsed():
    return parse_spec_file(SPEC_PATH)


def test_spec_file_reproduces_listing_2_character_for_character():
    """Everything above the listing is header comments; the listing itself is untouched."""
    source = open(SPEC_PATH, encoding="utf-8").read()
    assert source.endswith(LISTING_2)
    # and the part we added is comments only -- no code above the listing
    header = source[: -len(LISTING_2)]
    assert all(not line.strip() or line.startswith("#") for line in header.splitlines())


def test_parses_under_m1s_parser_with_no_changes(parsed):
    graph, _ = parsed
    assert graph.workflow_id == "video_qa"  # derived from the filename
    assert graph.parameters == ("query", "videos")
    assert graph.task_ids == ("scene_detect", "frame_extract", "stt", "q_a")
    assert graph.output == TaskRef("q_a")


def test_data_flow_is_positional_call_composition(parsed):
    graph, _ = parsed
    assert graph.node("scene_detect").args == (BoundaryRef("videos"),)
    assert graph.node("frame_extract").args == (TaskRef("scene_detect"),)
    assert graph.node("stt").args == (TaskRef("scene_detect"),)
    # the list literal of Listing 2 line 11: two upstream results into ONE argument position
    assert graph.node("q_a").args == (
        BoundaryRef("query"),
        (TaskRef("frame_extract"), TaskRef("stt")),
    )


def test_no_multi_output_call_is_needed(parsed):
    """Listing 1 (p.569) writes `scenes, audio = scene_detection(videos)`; Listing 2 does not.

    M1's parser rejects tuple unpacking by rule and `ExecutorSpec` enforces exactly one output
    port. Reproducing Listing 1's shape would mean reproducing the imperative paradigm the paper
    argues against (Section 2.3, p.569). Gap A23.
    """
    graph, _ = parsed
    assert graph.node("stt").args == (TaskRef("scene_detect"),)  # scenes, not a separate audio


def test_the_request_section_stays_out_of_the_graph(parsed):
    graph, execution = parsed
    assert execution.slo == "LOW_LATENCY"
    assert "What is the name of the person wearing the red dress?" in execution.literals
    assert "road_trip.mp4" in " ".join(execution.literals)
    assert {n.task_id for n in graph.nodes} == set(EXPECTED)  # no `result`/`run` node


def test_orchestrates_to_a_request_agnostic_logical_workflow():
    """Section 3.2 (p.573): the logical workflow is "request-agnostic, containing no per-request
    details such as query text, input payloads, or SLOs"."""
    _, execution = parse_spec_file(SPEC_PATH)
    llm = MockLLMClient(mode="fixture", fixture=EXPECTED)
    result = WorkflowOrchestrator(video_qa_library(), llm).orchestrate_file(SPEC_PATH)

    assert {n.task_id: n.executor for n in result.workflow.nodes} == EXPECTED
    assert audit_request_agnostic(result.workflow, execution.literals) == ()
    blob = result.workflow.to_json()
    assert "LOW_LATENCY" not in blob and "road_trip" not in blob


def test_no_stt_enabled_knob_anywhere_in_the_workflow():
    """Decision Q6 (2026-09-11), gap A18.

    Section 3.3.1 (p.574) names STT on/off as a workflow-level knob, but Section 3.2 (p.572)
    attaches knobs to "each model or tool", and no executor can own the knob that deletes it. The
    reproduction expresses the choice through `C_w` (a configuration IS a DAG variant), so no such
    knob exists on any node. M3 must prune the `stt` node when enumerating configurations, and
    must label that pruning as ours -- the paper never describes it.
    """
    llm = MockLLMClient(mode="fixture", fixture=EXPECTED)
    workflow = WorkflowOrchestrator(video_qa_library(), llm).orchestrate_file(SPEC_PATH).workflow
    declared = {p.name for n in workflow.nodes for p in n.open_parameters}
    assert "stt_enabled" not in declared
    assert not any(name.lower().endswith("_enabled") for name in declared)


def test_pruning_the_stt_branch_would_still_type_check():
    """The property that makes decision Q6's Option 5 mechanically valid.

    `q_a`'s context port is variadic, and a variadic port accepts a SUBSET of its declared element
    types, so a configuration with the `stt` node removed still satisfies M1's type-check. This is
    asserted here because M3's enumeration depends on it.
    """
    q_a_executor = video_qa_library().get("multimodal_llm_qa")
    context = q_a_executor.inputs[1]
    assert context.variadic
    assert {"Frames", "AnnotatedFrames", "Transcript"} == set(context.accepted_types)
    assert {"Frames"} <= set(context.accepted_types)  # STT off: frames only, still valid
