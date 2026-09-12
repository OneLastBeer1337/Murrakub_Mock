"""
Adversarial Challenge Test Suite: Empirical stress-testing of executor libraries,
parallel DAG execution, and optimizer boundary.

Investigator: challenger_arch_1 (EMPIRICAL CHALLENGER)
Focus Areas:
1. Parallel branch independence in Video Q/A (`frame_extract` || `stt`) and MILP eq. (5) latency blindness.
2. Tool invisibility: zero token generation, absence from MILP capacity (eq. 3) and cost (eq. 12).
3. Existence knob pruning (`prune_stt`): graph topology deformation and variadic port adaptation.
4. Mock LLM selector length-normalized keyword scoring bias and score inversion.
"""

from __future__ import annotations

import math
import pytest
from typing import Mapping

from development.executor_lib import code_generation_library, default_library, video_qa_library
from development.orchestrator import WorkflowOrchestrator
from development.prompting import to_tool_spec, to_tool_specs
from development.spec_parser import parse_spec_file
from shared.executor import ExecutorKind, Port
from shared.llm_client import MockLLMClient, TaskDescription, ToolSpec, _tokens
from shared.types import (
    ANNOTATED_FRAMES,
    CODE_CANDIDATES,
    EXECUTION_RESULTS,
    FRAMES,
    QUERY,
    SCENES,
    TEST_SUITE,
    TRANSCRIPT,
    VIDEOS,
)
from shared.workflow import (
    BoundaryRef,
    InputBinding,
    LogicalEdge,
    LogicalNode,
    LogicalWorkflow,
    TaskRef,
)

VIDEO_QA_SPEC = "development/specs/video_qa.py"
CODE_GEN_SPEC = "development/specs/code_generation.py"

VQA_FIXTURE = {
    "scene_detect": "opencv_scene_detector",
    "frame_extract": "omdet_frame_annotator",
    "stt": "whisper_stt",
    "q_a": "multimodal_llm_qa",
}


# =================================================================================================
# 1. Parallel Branch Independence & MILP Latency Eq. (5) Blindness
# =================================================================================================


def test_parallel_branch_independence_and_dag_topology():
    """Verify Video Q/A DAG has fan-out, fan-in, and genuine independence between branches."""
    llm = MockLLMClient(mode="fixture", fixture=VQA_FIXTURE)
    result = WorkflowOrchestrator(video_qa_library(), llm).orchestrate_file(VIDEO_QA_SPEC)
    dag = result.workflow

    # Nodes
    node_ids = [n.task_id for n in dag.nodes]
    assert node_ids == ["scene_detect", "frame_extract", "stt", "q_a"]

    # Edges
    edges = set(dag.edges)
    assert LogicalEdge("scene_detect", "frame_extract", 0, SCENES) in edges
    assert LogicalEdge("scene_detect", "stt", 0, SCENES) in edges
    assert LogicalEdge("frame_extract", "q_a", 1, ANNOTATED_FRAMES) in edges
    assert LogicalEdge("stt", "q_a", 1, TRANSCRIPT) in edges

    # Reachability: frame_extract and stt must be independent
    adj: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for e in dag.edges:
        adj[e.src_task].add(e.dst_task)

    def is_reachable(src: str, dst: str) -> bool:
        stack, seen = [src], set()
        while stack:
            curr = stack.pop()
            if curr == dst:
                return True
            for nxt in adj[curr]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False

    assert not is_reachable("frame_extract", "stt")
    assert not is_reachable("stt", "frame_extract")
    assert is_reachable("scene_detect", "q_a")


def test_parallel_tool_executors_generate_zero_tokens():
    """Verify tool executors on parallel branches produce 0 tokens and declare no model."""
    library = video_qa_library()
    for task_id, exec_name in [("frame_extract", "omdet_frame_annotator"), ("stt", "whisper_stt")]:
        executor = library.get(exec_name)
        assert executor.kind is ExecutorKind.TOOL
        assert "model" not in executor.parameter_names
        # Tools expose cores (for CPU offloading), but cores cannot reach optimizer
        assert "cores" in executor.parameter_names


def test_milp_latency_equation_5_yields_identical_sequential_and_concurrent_numbers():
    """Verify Murakkab Appendix A.5 Eq. (5) is blind to parallel overlap.

    Equation (5) / (9):
        L_milp = l^TTFT_m + t_c * l^TPOT_m
    Because t_c is an aggregate scalar of the entire workflow and tools produce 0 tokens,
    the MILP latency is identical whether tasks run in sequence or in parallel.
    """
    # Profile values for Llava-OneVision-7B on H100 (from Table 5 & Figure 7b)
    l_TTFT = 0.220  # seconds
    l_TPOT = 0.0044  # seconds / token

    # Sub-task execution parameters
    t_scene = 0  # tool (OpenCV)
    t_frame = 0  # tool (OmDet)
    t_stt = 0  # tool (Whisper)
    t_qa = 250  # LLM completion tokens

    t_c = t_scene + t_frame + t_stt + t_qa  # total configuration tokens = 250

    # Murakkab Eq. (5) calculation
    l_milp_sequential = l_TTFT + t_c * l_TPOT
    l_milp_concurrent = l_TTFT + t_c * l_TPOT

    # Mathematically identical
    assert l_milp_sequential == l_milp_concurrent
    assert abs(l_milp_sequential - 1.320) < 1e-6

    # Physical makespan comparison
    d_scene = 0.500  # s
    d_frame = 1.800  # s (OmDet 10 frames)
    d_stt = 2.400  # s (Whisper on CPU)
    d_qa = 1.320  # s (LLM generation)

    makespan_sequential = d_scene + d_frame + d_stt + d_qa  # 6.02s
    makespan_concurrent = d_scene + max(d_frame, d_stt) + d_qa  # 4.22s

    assert abs(makespan_sequential - 6.020) < 1e-6
    assert abs(makespan_concurrent - 4.220) < 1e-6
    actual_parallel_saving = makespan_sequential - makespan_concurrent
    assert abs(actual_parallel_saving - 1.800) < 1e-6  # 1.8s overlap benefit

    # Murakkab MILP latency error
    milp_discrepancy_sequential = makespan_sequential - l_milp_sequential  # 4.70s under-count
    milp_discrepancy_concurrent = makespan_concurrent - l_milp_concurrent  # 2.90s under-count

    assert abs(milp_discrepancy_sequential - 4.700) < 1e-6
    assert abs(milp_discrepancy_concurrent - 2.900) < 1e-6

    # SLO violation demonstration:
    # If SLO tau = 3.0s, MILP filter predicts 1.32s <= 3.0s (FEASIBLE PASS),
    # but actual concurrent makespan is 4.22s > 3.0s (VIOLATES SLO).
    tau_slo = 3.000
    assert l_milp_concurrent <= tau_slo  # False positive certification!
    assert makespan_concurrent > tau_slo


# =================================================================================================
# 2. Tool Invisibility in MILP Capacity and Cost
# =================================================================================================


def test_tool_invisibility_in_milp_capacity_and_cost():
    """Verify substituting an LLM executor with a Tool executor drops token consumption to zero

    and removes the task completely from MILP capacity (eq. 3) and cost (eq. 12).
    """
    # Parameters for cluster and workflow
    peak_request_rate = 10.0  # requests / sec (lambda_w^peak)
    mu_m = 1.25  # multiplexing coefficient
    theta_m = 2500.0  # token throughput of model m (tokens / sec)
    gpu_cost = 4.0  # c_g ($ / GPU-hour)
    tp_degree = 2  # g_m (GPUs per instance)

    # Subtask token demands under Option A (All-LLM in Code Gen):
    # propose (debate LLM) = 800, write_tests (LLM) = 400, execute_tests (LLM sim) = 300, rank (LLM) = 100
    t_propose = 800
    t_write_tests = 400
    t_exec_llm = 300
    t_rank = 100
    t_c_all_llm = t_propose + t_write_tests + t_exec_llm + t_rank  # 1600 tokens

    # Subtask token demands under Option B (Tool substitution for execute_tests):
    # execute_tests -> python_interpreter (kind = TOOL) -> 0 tokens
    t_exec_tool = 0
    t_c_tool_sub = t_propose + t_write_tests + t_exec_tool + t_rank  # 1300 tokens

    assert t_c_all_llm == 1600
    assert t_c_tool_sub == 1300
    assert t_c_all_llm - t_c_tool_sub == 300

    # Appendix A.5 Eq. (3): mu_m * sum(x^peak * t_c) <= n_m * theta_m
    # Minimum instances n_m = ceil(mu_m * lambda_peak * t_c / theta_m)
    n_instances_llm = math.ceil(mu_m * peak_request_rate * t_c_all_llm / theta_m)
    n_instances_tool = math.ceil(mu_m * peak_request_rate * t_c_tool_sub / theta_m)

    # With 1600 tokens: 1.25 * 10 * 1600 / 2500 = 8.0 -> n_m = 8 instances
    # With 1300 tokens: 1.25 * 10 * 1300 / 2500 = 6.5 -> n_m = 7 instances
    assert n_instances_llm == 8
    assert n_instances_tool == 7

    # Appendix A.5 Eq. (12): Cost = sum(n_m * g_m * c_g)
    cost_llm = n_instances_llm * tp_degree * gpu_cost  # 8 * 2 * 4 = $64/hr
    cost_tool = n_instances_tool * tp_degree * gpu_cost  # 7 * 2 * 4 = $56/hr

    assert cost_llm == 64.0
    assert cost_tool == 56.0
    assert cost_llm - cost_tool == 8.0

    # Check that python_interpreter is indeed a TOOL
    cg_lib = code_generation_library()
    tool_exec = cg_lib.get("python_interpreter")
    assert tool_exec.kind is ExecutorKind.TOOL
    assert "model" not in tool_exec.parameter_names

    # But python_interpreter requires CPU cores and memory in reality
    assert "cores" in tool_exec.parameter_names
    assert "timeout_s" in tool_exec.parameter_names
    # Crucially, Appendix A.5 has zero variables or constraints for CPU or RAM!


# =================================================================================================
# 3. Existence Knob Pruning (`prune_stt`) & Variadic Port Adaptation
# =================================================================================================


def _prune_stt(workflow: LogicalWorkflow) -> LogicalWorkflow:
    """Implement Option 5 DAG surgery pruning the `stt` task from Video Q/A.

    Mandates removing the stt node, incoming edge scene_detect -> stt,
    outgoing edge stt -> q_a, and updating q_a's input binding to drop TaskRef("stt").
    """
    assert any(n.task_id == "stt" for n in workflow.nodes), "stt node must exist"

    new_nodes = []
    for n in workflow.nodes:
        if n.task_id == "stt":
            continue
        if n.task_id == "q_a":
            new_inputs = []
            for b in n.inputs:
                new_sources = tuple(s for s in b.sources if not (isinstance(s, TaskRef) and s.task_id == "stt"))
                new_inputs.append(InputBinding(b.arg_index, b.port_name, b.port_type, new_sources))
            new_nodes.append(
                LogicalNode(
                    task_id=n.task_id,
                    task_description=n.task_description,
                    executor=n.executor,
                    inputs=tuple(new_inputs),
                    output_type=n.output_type,
                    open_parameters=n.open_parameters,
                )
            )
        else:
            new_nodes.append(n)

    new_edges = tuple(e for e in workflow.edges if e.src_task != "stt" and e.dst_task != "stt")

    return LogicalWorkflow(
        workflow_id=f"{workflow.workflow_id}_no_stt",
        inputs=workflow.inputs,
        nodes=tuple(new_nodes),
        edges=new_edges,
        outputs=workflow.outputs,
    )


def test_existence_knob_pruning_modifies_graph_topology_and_validates_variadic_port():
    """Verify that removing STT modifies graph topology and that q_a's variadic port adapts."""
    llm = MockLLMClient(mode="fixture", fixture=VQA_FIXTURE)
    orig_workflow = WorkflowOrchestrator(video_qa_library(), llm).orchestrate_file(VIDEO_QA_SPEC).workflow

    assert len(orig_workflow.nodes) == 4
    assert len(orig_workflow.edges) == 4

    # Edges entering q_a in original DAG
    qa_in_orig = [e for e in orig_workflow.edges if e.dst_task == "q_a"]
    assert len(qa_in_orig) == 2
    assert {e.type for e in qa_in_orig} == {ANNOTATED_FRAMES, TRANSCRIPT}

    # Apply pruning
    pruned_workflow = _prune_stt(orig_workflow)

    # Topological deformation
    assert len(pruned_workflow.nodes) == 3
    assert len(pruned_workflow.edges) == 2
    assert [n.task_id for n in pruned_workflow.nodes] == ["scene_detect", "frame_extract", "q_a"]

    # Edges entering q_a in pruned DAG
    qa_in_pruned = [e for e in pruned_workflow.edges if e.dst_task == "q_a"]
    assert len(qa_in_pruned) == 1
    assert qa_in_pruned[0].type == ANNOTATED_FRAMES
    assert qa_in_pruned[0].src_task == "frame_extract"

    # Verify downstream executor port contract:
    q_a_executor = video_qa_library().get(pruned_workflow.node("q_a").executor)
    context_port = q_a_executor.inputs[1]
    assert context_port.name == "context"
    assert context_port.variadic is True
    assert set(context_port.accepted_types) == {FRAMES, ANNOTATED_FRAMES, TRANSCRIPT}

    # The pruned edge feeds AnnotatedFrames, which is in accepted_types
    assert qa_in_pruned[0].type in context_port.accepted_types


def test_adversarial_counter_example_inflexible_port_fails_under_pruning():
    """Adversarial stress test: If a downstream node does not have a variadic port,

    pruning an existence knob breaks the graph contract.
    """
    # Suppose a consumer requires both frames and transcript as rigid positional ports:
    # Port 0: frames (AnnotatedFrames), Port 1: transcript (Transcript) - non-variadic!
    rigid_edges = [
        LogicalEdge("scene_detect", "frame_extract", 0, SCENES),
        LogicalEdge("frame_extract", "q_a", 0, ANNOTATED_FRAMES),
        LogicalEdge("stt", "q_a", 1, TRANSCRIPT),
    ]

    # If STT is pruned:
    pruned_edges = [e for e in rigid_edges if e.src_task != "stt"]
    assert len(pruned_edges) == 2

    # Port 1 of q_a is now completely dangling / unsatisfied!
    dst_ports_satisfied = {e.dst_arg_index for e in pruned_edges if e.dst_task == "q_a"}
    assert 0 in dst_ports_satisfied
    assert 1 not in dst_ports_satisfied  # Port 1 is missing, violating arity!


# =================================================================================================
# 4. Mock LLM Selector Length-Normalized Keyword Scoring Bias
# =================================================================================================


def test_mock_llm_selector_score_inversion_reproduction():
    """Reproduce the score inversion in MockLLMClient keyword mode:

    Candidate description length penalizes comprehensive descriptions.
    """
    library = default_library()
    candidates = to_tool_specs(library.all())
    task = TaskDescription(
        task_id="scene_detect",
        description="Given a list of videos, identify scenes in each.",
    )

    client = MockLLMClient(mode="keyword")
    task_tokens = _tokens(task.description)
    assert task_tokens == {"a", "each", "given", "identify", "in", "list", "of", "scenes", "videos"}

    # Compute scores for all candidates
    scores: list[tuple[str, float, int, int]] = []
    for cand in candidates:
        cand_tokens = _tokens(f"{cand.name} {cand.description}")
        overlap_count = len(task_tokens & cand_tokens)
        denom = len(cand_tokens)
        overlap = overlap_count / denom if denom else 0.0
        cue_hits = sum(1 for cue in ("execute", "run", "interpreter", "report", "results") if cue in task_tokens)
        score = overlap + 0.15 * cue_hits
        scores.append((cand.name, score, overlap_count, denom))

    # Sort descending by score
    scores.sort(key=lambda x: x[1], reverse=True)

    # 1st place is fixed_interval_segmenter
    rank_1_name, rank_1_score, rank_1_ov, rank_1_len = scores[0]
    assert rank_1_name == "fixed_interval_segmenter"
    assert rank_1_ov == 4  # matches stopwords/tokens: 'a', 'each', 'in', 'of'
    assert rank_1_len == 30
    assert abs(rank_1_score - (4 / 30)) < 1e-4  # ~0.1333

    # opencv_scene_detector (the canonical paper tool) is ranked 7th!
    names = [s[0] for s in scores]
    opencv_rank = names.index("opencv_scene_detector") + 1
    assert opencv_rank == 7

    _, opencv_score, opencv_ov, opencv_len = scores[opencv_rank - 1]
    assert opencv_ov == 3  # matches: 'of', 'scenes', 'each' (including key domain token 'scenes')
    assert opencv_len == 33  # longer description (33 tokens) penalizes the score
    assert abs(opencv_score - (3 / 33)) < 1e-4  # ~0.0909

    # Score inversion: 0.1333 > 0.0909 purely because denom is smaller
    assert rank_1_score > opencv_score


def test_adversarial_synthetic_terse_vs_detailed_description():
    """Adversarial stress test proving score inversion on controlled synthetic candidates."""
    task = TaskDescription(task_id="extract", description="Extract video frames")
    task_tokens = _tokens(task.description)  # {'extract', 'frames', 'video'}

    cand_terse = ToolSpec(
        name="terse_extractor",
        kind="tool",
        description="Extract frames",
        interface={},
        parameters={},
    )
    cand_detailed = ToolSpec(
        name="production_extractor",
        kind="tool",
        description=(
            "Extract high-quality video frames using adaptive scene-based sampling, "
            "color histogram difference filtering, duplicate removal, and GPU-accelerated decoders."
        ),
        interface={},
        parameters={},
    )

    # Score terse
    tokens_terse = _tokens(f"{cand_terse.name} {cand_terse.description}")
    score_terse = len(task_tokens & tokens_terse) / len(tokens_terse)

    # Score detailed
    tokens_detailed = _tokens(f"{cand_detailed.name} {cand_detailed.description}")
    score_detailed = len(task_tokens & tokens_detailed) / len(tokens_detailed)

    # Terse matches 2 of 3 tokens with denominator 3 -> 2/3 = 0.6667
    # Detailed matches 3 of 3 tokens with denominator 18 -> 3/18 = 0.1667
    assert len(task_tokens & tokens_detailed) > len(task_tokens & tokens_terse)
    assert score_terse > score_detailed * 3.5  # Terse gets >3.5x higher score!
