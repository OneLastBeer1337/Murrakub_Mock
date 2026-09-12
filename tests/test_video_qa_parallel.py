"""
The parallel branch: the reason Video Q/A was un-deferred.

Covers Murakkab (OSDI '26), Section 3.2, "Logical Workflow" (p.573) -- "It is represented as a
directed acyclic graph (DAG), where nodes are executors and edges denote data flow" -- and
Section 4.6, "Workflow/DAG-Aware Scheduling" (p.578), which co-schedules exactly this branch:

    Figure 12a: "The two sub-tasks run in near-perfect parallel, with full overlap in execution."
    Figure 12b: Whisper and OmDet on CPUs, "reducing GPU usage ... utilizing idle CPU resources".
    Figure 12c: "Both sub-tasks complete nearly simultaneously, and Whisper's added CPU latency
                 has minimal impact on end-to-end time."

Appendix A.5 (p.586-587) has no precedence constraint, no makespan term, and no CPU resource type.
Code Generation is a total order, so neither gap could be demonstrated on it (PROGRESS.md, M1).
These tests pin the structure on which they can be.
"""

from __future__ import annotations

import pytest

from development.executor_lib import video_qa_library
from development.orchestrator import WorkflowOrchestrator
from shared.executor import ExecutorKind
from shared.llm_client import MockLLMClient
from shared.workflow import LogicalEdge

SPEC_PATH = "development/specs/video_qa.py"

EXPECTED = {
    "scene_detect": "opencv_scene_detector",
    "frame_extract": "omdet_frame_annotator",  # Section 4.6's OmDet branch
    "stt": "whisper_stt",  # Section 4.6's Whisper branch
    "q_a": "multimodal_llm_qa",
}


@pytest.fixture()
def workflow():
    llm = MockLLMClient(mode="fixture", fixture=EXPECTED)
    return WorkflowOrchestrator(video_qa_library(), llm).orchestrate_file(SPEC_PATH).workflow


def test_the_dag_has_a_genuine_fan_out_and_fan_in(workflow):
    edges = set(workflow.edges)
    assert LogicalEdge("scene_detect", "frame_extract", 0, "Scenes") in edges
    assert LogicalEdge("scene_detect", "stt", 0, "Scenes") in edges
    assert LogicalEdge("frame_extract", "q_a", 1, "AnnotatedFrames") in edges
    assert LogicalEdge("stt", "q_a", 1, "Transcript") in edges
    assert sum(1 for e in edges if e.src_task == "scene_detect") == 2  # fan-out
    assert sum(1 for e in edges if e.dst_task == "q_a") == 2  # fan-in, one argument position


def test_the_two_branches_are_independent(workflow):
    """No path between `frame_extract` and `stt` in either direction -- this is what Code
    Generation's chain DAG could never provide."""
    successors: dict[str, set[str]] = {n.task_id: set() for n in workflow.nodes}
    for edge in workflow.edges:
        successors[edge.src_task].add(edge.dst_task)

    def reaches(src: str, dst: str) -> bool:
        seen, stack = set(), [src]
        while stack:
            current = stack.pop()
            for nxt in successors[current]:
                if nxt == dst:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    assert not reaches("frame_extract", "stt")
    assert not reaches("stt", "frame_extract")
    # both are nonetheless on a path from the source to the sink
    assert reaches("scene_detect", "frame_extract") and reaches("frame_extract", "q_a")
    assert reaches("scene_detect", "stt") and reaches("stt", "q_a")


def test_code_generation_has_no_such_branch():
    """The contrast, asserted rather than claimed (PROGRESS.md's M1 scoping gap)."""
    from development.executor_lib import code_generation_library

    code_gen = {
        "propose_solutions": "llm_debate_coders",
        "write_tests": "llm_unit_test_writer",
        "execute_tests": "python_interpreter",
        "rank_solutions": "llm_ranker",
    }
    dag = (
        WorkflowOrchestrator(code_generation_library(), MockLLMClient("fixture", fixture=code_gen))
        .orchestrate_file("development/specs/code_generation.py")
        .workflow
    )
    order = [n.task_id for n in dag.nodes]
    # every node except the last feeds the next: a total order, so no two tasks are concurrent
    consecutive = {(a, b) for a, b in zip(order, order[1:])}
    assert consecutive <= {(e.src_task, e.dst_task) for e in dag.edges}


def test_the_parallel_branch_generates_no_llm_tokens(workflow):
    """Why Appendix A.5's latency filter cannot see this branch at all.

    Filter eq. (5)/(9) is `l^TTFT_m + t_c * l^TPOT_m > tau_{w,s}` -- one model's TTFT plus that
    model's per-output-token time, times the whole configuration's token count. Both branch nodes
    here are TOOLs (OmDet, Whisper), which have no model profile `m` and generate no tokens, so
    the sub-tasks Section 4.6 spends a subsection co-scheduling contribute nothing to the only
    latency expression the optimizer has.
    """
    library = video_qa_library()
    for task_id in ("frame_extract", "stt"):
        executor = library.get(workflow.node(task_id).executor)
        assert executor.kind is ExecutorKind.TOOL
        assert "model" not in executor.parameter_names


def test_edges_carry_the_precedence_information_the_milp_will_not_use(workflow):
    """M1's standing rule, now on a DAG where it bites.

    The information needed for a critical path -- which tasks may overlap -- is present and typed.
    Appendix A.5 never consumes it: there is no precedence constraint in (1)-(10) and no makespan
    term in objectives (11)-(13), so a serialized execution and a fully overlapped one yield
    identical objective values and identical feasibility.
    """
    assert workflow.edges and all(e.type for e in workflow.edges)
    doc = LogicalEdge.__doc__ or ""
    assert "must NOT read these edges for scheduling" in doc
    assert "no precedence constraint" in doc and "makespan term" in doc


def test_both_branch_executors_expose_a_cores_knob_that_cannot_reach_the_milp(workflow):
    """Gap A30 / A13 made concrete on the exact executors Section 4.6 offloads to CPU.

    Appendix A.5's resource set `G` is GPU types with budget `B_g` and per-instance cost `c_g`;
    `n_m` counts instances of a model profile; constraint (7) is GPU-only. There is no variable
    into which a CPU core count or a CPU/GPU placement could be substituted, so Figure 12b/12c's
    GPU savings can be measured and reported -- the paper does -- but never CHOSEN.
    """
    library = video_qa_library()
    for task_id in ("frame_extract", "stt"):
        assert "cores" in library.get(workflow.node(task_id).executor).parameter_names
