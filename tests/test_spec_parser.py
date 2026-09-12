"""
Tests for the declarative specification parser.

Covers Murakkab (OSDI '26), Section 3.2, "Declarative Specification" (p.573) and Listing 2's
format (p.572), including the structural guarantee that the "Execution with example request"
section cannot reach the graph.
"""

from __future__ import annotations

import pytest

from development.errors import SpecValidationError
from development.spec_parser import parse_spec_file, parse_spec_source
from shared.workflow import BoundaryRef, TaskRef

SPEC_PATH = "development/specs/code_generation.py"

# The paper's own Listing 2 (p.572), used to prove the parser handles the format verbatim --
# including the heterogeneous list argument `[frames, transcript]` on line 11.
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


def test_parses_the_papers_own_listing_2():
    graph, execution = parse_spec_source(LISTING_2, workflow_id="video_qa")

    assert graph.parameters == ("query", "videos")
    assert graph.task_ids == ("scene_detect", "frame_extract", "stt", "q_a")
    assert graph.output == TaskRef("q_a")
    # data flow is positional Python call composition
    assert graph.node("scene_detect").args == (BoundaryRef("videos"),)
    assert graph.node("q_a").args == (
        BoundaryRef("query"),
        (TaskRef("frame_extract"), TaskRef("stt")),  # the list literal, line 11
    )
    # the request section is recognized and kept out of the graph
    assert execution.slo == "LOW_LATENCY"
    assert "What is the name of the person wearing the red dress?" in execution.literals


def test_parses_the_code_generation_spec():
    graph, execution = parse_spec_file(SPEC_PATH)

    assert graph.workflow_id == "code_generation"
    assert graph.parameters == ("query",)
    assert graph.task_ids == (
        "propose_solutions",
        "write_tests",
        "execute_tests",
        "rank_solutions",
    )
    assert graph.output == TaskRef("rank_solutions")
    assert graph.node("rank_solutions").args == (
        BoundaryRef("query"),
        (TaskRef("propose_solutions"), TaskRef("execute_tests")),
    )
    assert execution.slo == "HIGH_ACCURACY"


def test_subtask_descriptions_are_natural_language_only():
    """Section 3.2 (p.572): "We allow tasks to be expressed in natural language"."""
    graph, _ = parse_spec_file(SPEC_PATH)
    for node in graph.nodes:
        assert node.description
        assert node.description[0].isupper()
        # no configuration smuggled into the description
        for banned in ("model=", "gpu", "batch", "slo="):
            assert banned not in node.description.lower()


def _spec(body: str, header: str = 'a = "do a thing."\nb = "do another thing."\n') -> str:
    return header + body


def test_rejects_loop_in_workflow_body():
    """Section 3.2 (p.573) requires a DAG, so iteration cannot appear as control flow."""
    source = _spec(
        "def workflow(x):\n"
        "    for i in range(3):\n"
        "        y = a(x)\n"
        "    return y\n"
    )
    with pytest.raises(SpecValidationError, match="directed acyclic graph"):
        parse_spec_source(source, "bad")


def test_rejects_conditional_in_workflow_body():
    source = _spec(
        "def workflow(x):\n"
        "    if x:\n"
        "        y = a(x)\n"
        "    return y\n"
    )
    with pytest.raises(SpecValidationError):
        parse_spec_source(source, "bad")


def test_rejects_slo_inside_the_workflow_definition():
    """The SLO is a per-request detail and enters at `run(...)` (Section 3.2, p.573)."""
    source = _spec("def workflow(x, slo):\n    y = a(x)\n    return y\n")
    with pytest.raises(SpecValidationError, match="per-request detail"):
        parse_spec_source(source, "bad")


def test_rejects_literal_payload_as_subtask_argument():
    source = _spec('def workflow(x):\n    y = a("a hardcoded request")\n    return y\n')
    with pytest.raises(SpecValidationError, match="per-request input payload"):
        parse_spec_source(source, "bad")


def test_rejects_configuration_keyword_in_subtask_call():
    """"Configuration details ... are omitted from the specification" (Section 3.2, p.573)."""
    source = _spec('def workflow(x):\n    y = a(x, model="llama-3.2")\n    return y\n')
    with pytest.raises(SpecValidationError, match="keyword argument"):
        parse_spec_source(source, "bad")


def test_rejects_undeclared_subtask():
    source = _spec("def workflow(x):\n    y = undeclared(x)\n    return y\n")
    with pytest.raises(SpecValidationError, match="not a declared sub-task"):
        parse_spec_source(source, "bad")


def test_rejects_use_before_production():
    """A name must be produced before use -- this is what keeps the graph acyclic."""
    source = _spec("def workflow(x):\n    y = a(z)\n    z = b(x)\n    return y\n")
    with pytest.raises(SpecValidationError, match="acyclic"):
        parse_spec_source(source, "bad")


def test_rejects_reassignment():
    source = _spec("def workflow(x):\n    y = a(x)\n    y = b(y)\n    return y\n")
    with pytest.raises(SpecValidationError, match="re-assigned"):
        parse_spec_source(source, "bad")


def test_rejects_missing_return():
    source = _spec("def workflow(x):\n    y = a(x)\n")
    with pytest.raises(SpecValidationError, match="return"):
        parse_spec_source(source, "bad")


def test_parser_never_executes_developer_code():
    """The parser must not run the spec: `run(...)` and `HIGH_ACCURACY` are undefined names, and
    a string is not callable, yet parsing succeeds."""
    source = _spec(
        "def workflow(x):\n"
        "    y = a(x)\n"
        "    return y\n"
        "boom = 1 / 0\n"
        "result = run(workflow('payload'), slo=UNDEFINED_NAME)\n"
    )
    graph, execution = parse_spec_source(source, "inert")
    assert graph.task_ids == ("a",)
    assert execution.slo == "UNDEFINED_NAME"


def test_execution_section_is_structurally_outside_the_graph():
    """Nothing from the request section appears in the parsed data flow."""
    graph, execution = parse_spec_file(SPEC_PATH)
    flow_text = repr(graph)
    for literal in execution.literals:
        assert literal not in flow_text
    assert execution.slo is not None
    assert execution.slo not in flow_text
